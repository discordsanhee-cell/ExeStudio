"""Finding/installing Python, pip packages, winget programs and build tools."""
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
import urllib.request
from pathlib import Path

from .config import BUNDLED_PYTHON, DOWNLOAD_DIR, FROZEN, MANAGED_PYTHON_DIR

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
PYTHON_URL = "https://www.python.org/ftp/python/{v}/python-{v}-amd64.exe"
DEFAULT_PYTHON_VERSION = "3.13.7"

# Variables PyInstaller / Qt set for *this* process that must not leak into child Pythons.
_LEAKY_ENV = ("QT_PLUGIN_PATH", "QML2_IMPORT_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "TCL_LIBRARY",
              "TK_LIBRARY", "PYTHONHOME", "PYTHONPATH", "_MEIPASS2", "_PYI_APPLICATION_HOME_DIR",
              "_PYI_ARCHIVE_FILE", "_PYI_PARENT_PROCESS_LEVEL", "_PYI_SPLASH_IPC")


def is_bundled(exe):
    try:
        return Path(exe).resolve() == BUNDLED_PYTHON.resolve()
    except Exception:
        return False


def clean_env(python=None):
    env = {k: v for k, v in os.environ.items() if k not in _LEAKY_ENV}
    if FROZEN:
        mei = str(getattr(sys, "_MEIPASS", "")).lower()
        if mei:
            env["PATH"] = os.pathsep.join(p for p in env.get("PATH", "").split(os.pathsep)
                                          if not p.lower().startswith(mei))
    env.update(PYTHONIOENCODING="utf-8", PYTHONUTF8="1", PYTHONUNBUFFERED="1", PIP_DISABLE_PIP_VERSION_CHECK="1")
    if python and is_bundled(python):
        env["PYTHONNOUSERSITE"] = "1"
    return env


def _decode(b):
    for enc in ("utf-8", "cp949"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            pass
    return b.decode("utf-8", "replace")


def run_capture(args, timeout=30, python=None, cwd=None):
    try:
        r = subprocess.run([str(a) for a in args], capture_output=True, timeout=timeout, cwd=cwd,
                           creationflags=CREATE_NO_WINDOW, env=clean_env(python), stdin=subprocess.DEVNULL)
        return r.returncode, _decode(r.stdout) + _decode(r.stderr)
    except Exception as e:
        return -1, str(e)


# ---------------------------------------------------------------- Python discovery
def python_version(exe):
    code, out = run_capture([exe, "-c", "import sys;print(sys.version.split()[0])"], 15, python=exe)
    out = out.strip().splitlines()
    return out[-1] if code == 0 and out else None


def discover_pythons(custom=()):
    cands = []
    if BUNDLED_PYTHON.exists():
        cands.append((BUNDLED_PYTHON, "내장"))
    managed = MANAGED_PYTHON_DIR / "python.exe"
    if managed.exists():
        cands.append((managed, "자동설치"))
    for c in custom:
        cands.append((Path(c), "직접 추가"))
    if shutil.which("py"):
        _, out = run_capture(["py", "-0p"], 15)
        for line in out.splitlines():
            m = re.search(r"([A-Za-z]:\\.*?python[w]?\.exe)", line, re.I)
            if m:
                cands.append((Path(m.group(1).strip()), "시스템"))
    if sys.platform == "win32":
        _, out = run_capture(["where", "python"], 10)
        for line in out.splitlines():
            line = line.strip()
            if line.lower().endswith("python.exe") and "windowsapps" not in line.lower():
                cands.append((Path(line), "PATH"))
    seen, result = set(), []
    for path, source in cands:
        key = str(path).lower()
        if key in seen or not path.exists():
            continue
        seen.add(key)
        ver = python_version(path)
        if ver:
            result.append({"path": str(path), "version": ver, "source": source})
    return result


def module_versions(python, dists):
    script = ("import json,sys\nimport importlib.metadata as m\nout={}\n"
              "for n in json.loads(sys.argv[1]):\n"
              "    try: out[n]=m.version(n)\n"
              "    except Exception: out[n]=None\n"
              "print(json.dumps(out))")
    code, out = run_capture([python, "-c", script, json.dumps(list(dists))], 30, python=python)
    try:
        return json.loads(out.strip().splitlines()[-1])
    except Exception:
        return {d: None for d in dists}


def pip_list(python):
    code, out = run_capture([python, "-m", "pip", "list", "--format=json", "--disable-pip-version-check"], 60,
                            python=python)
    for line in reversed(out.strip().splitlines()):
        if line.startswith("["):
            try:
                return json.loads(line)
            except Exception:
                break
    raise RuntimeError(out.strip() or "pip list 실패")


# ---------------------------------------------------------------- import scanning
IMPORT_TO_PIP = {
    "cv2": "opencv-python", "PIL": "pillow", "yaml": "pyyaml", "sklearn": "scikit-learn",
    "skimage": "scikit-image", "bs4": "beautifulsoup4", "win32api": "pywin32", "win32con": "pywin32",
    "win32gui": "pywin32", "win32com": "pywin32", "pythoncom": "pywin32", "pywintypes": "pywin32",
    "win32clipboard": "pywin32", "dateutil": "python-dateutil", "webview": "pywebview", "serial": "pyserial",
    "usb": "pyusb", "Crypto": "pycryptodome", "OpenSSL": "pyopenssl", "dotenv": "python-dotenv",
    "docx": "python-docx", "pptx": "python-pptx", "fitz": "pymupdf", "attr": "attrs", "jwt": "pyjwt",
    "magic": "python-magic", "telegram": "python-telegram-bot", "discord": "discord.py", "wx": "wxPython",
    "gi": "pygobject", "speech_recognition": "SpeechRecognition", "Levenshtein": "python-Levenshtein",
    "pkg_resources": "setuptools", "google.generativeai": "google-generativeai", "openai": "openai",
    "anthropic": "anthropic", "pygame": "pygame", "pystray": "pystray", "PySide6": "PySide6",
    "PyQt5": "PyQt5", "PyQt6": "PyQt6", "customtkinter": "customtkinter", "ttkbootstrap": "ttkbootstrap",
}


def scan_imports(script):
    """Top-level third-party-or-stdlib module names imported by script and its local modules."""
    script = Path(script)
    base = script.parent
    local = {p.stem for p in base.glob("*.py")} | {p.parent.name for p in base.glob("*/__init__.py")}
    todo, done, found = [script], set(), set()
    while todo:
        f = todo.pop()
        if f in done or not f.exists():
            continue
        done.add(f)
        try:
            tree = ast.parse(f.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            for n in names:
                top = n.split(".")[0]
                if top in local:
                    todo.append(base / f"{top}.py")
                    todo.append(base / top / "__init__.py")
                else:
                    found.add(top)
    return sorted(found)


def missing_modules(python, modules):
    script = ("import sys,json,importlib.util\n"
              "std=set(getattr(sys,'stdlib_module_names',()))|set(sys.builtin_module_names)\n"
              "miss=[]\n"
              "for n in json.loads(sys.argv[1]):\n"
              "    if n in std: continue\n"
              "    try:\n"
              "        if importlib.util.find_spec(n) is None: miss.append(n)\n"
              "    except Exception: miss.append(n)\n"
              "print(json.dumps(miss))")
    code, out = run_capture([python, "-c", script, json.dumps(list(modules))], 60, python=python)
    try:
        return json.loads(out.strip().splitlines()[-1])
    except Exception:
        return []


def pip_names(modules):
    return sorted({IMPORT_TO_PIP.get(m, m) for m in modules})


# ---------------------------------------------------------------- downloads / installers
def download(url, dest, progress=None):
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "ExeStudio/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if progress:
                progress((done, total))
    tmp.replace(dest)
    return str(dest)


def python_installer_path(version):
    return DOWNLOAD_DIR / f"python-{version}-amd64.exe"


def python_install_args(installer, target):
    return [str(installer), "/quiet", "InstallAllUsers=0", f"TargetDir={target}", "Include_launcher=0",
            "InstallLauncherAllUsers=0", "PrependPath=0", "Shortcuts=0", "AssociateFiles=0",
            "Include_test=0", "Include_doc=0"]


def has_winget():
    return shutil.which("winget") is not None


def winget_install_args(pkg_id, scope_user=False):
    args = ["winget", "install", "-e", "--id", pkg_id, "--silent",
            "--accept-package-agreements", "--accept-source-agreements", "--disable-interactivity"]
    if scope_user:
        args += ["--scope", "user"]
    return args


def _disp_width(s):
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in s)


def _slice_by_width(s, start, end):
    out, pos = [], 0
    for ch in s:
        w = 2 if unicodedata.east_asian_width(ch) in "WF" else 1
        if pos >= start and (end is None or pos < end):
            out.append(ch)
        pos += w
    return "".join(out).strip()


def parse_winget_table(text):
    """Parse `winget search/list` console tables (handles localized headers and wide chars)."""
    lines = [ln.rstrip() for ln in text.replace("\r", "\n").splitlines()]
    for i, ln in enumerate(lines):
        if re.fullmatch(r"-{10,}", ln.strip()) and i > 0:
            header = lines[i - 1]
            starts, pos, prev_space = [], 0, True
            for ch in header:
                if not ch.isspace() and prev_space:
                    starts.append(pos)
                prev_space = ch.isspace()
                pos += 2 if unicodedata.east_asian_width(ch) in "WF" else 1
            if len(starts) < 3:
                return []
            rows = []
            for row in lines[i + 1:]:
                if not row.strip() or _disp_width(row) < starts[1]:
                    continue
                cells = [_slice_by_width(row, starts[k], starts[k + 1] if k + 1 < len(starts) else None)
                         for k in range(len(starts))]
                if cells[1]:
                    rows.append({"name": cells[0], "id": cells[1], "version": cells[2],
                                 "source": cells[-1] if len(cells) > 3 else ""})
            return rows
    return []


WINGET_CATALOG = [
    ("Python 3.12", "Python.Python.3.12", "PyInstaller와 호환성이 가장 좋은 파이썬"),
    ("Python 3.13", "Python.Python.3.13", "최신 안정판 파이썬"),
    ("Git", "Git.Git", "버전 관리 / 깃허브 연동"),
    ("Visual Studio Code", "Microsoft.VisualStudioCode", "강력한 코드 에디터"),
    ("Node.js LTS", "OpenJS.NodeJS.LTS", "자바스크립트 런타임 (Electron 앱 등)"),
    ("Inno Setup", "JRSoftware.InnoSetup", "Setup.exe 설치 프로그램 제작"),
    ("NSIS", "NSIS.NSIS", "설치 프로그램 제작 도구"),
    ("UPX", "UPX.UPX", "EXE 압축기 (용량 줄이기)"),
    ("7-Zip", "7zip.7zip", "압축 프로그램"),
    ("VS Build Tools 2022", "Microsoft.VisualStudio.2022.BuildTools", "C/C++ 컴파일러 (Nuitka, 네이티브 모듈)"),
    ("CMake", "Kitware.CMake", "C/C++ 빌드 시스템"),
    ("Rust", "Rustlang.Rustup", "러스트 툴체인"),
    ("Go", "GoLang.Go", "Go 언어"),
    ("Notepad++", "Notepad++.Notepad++", "가벼운 텍스트 에디터"),
    ("Everything", "voidtools.Everything", "초고속 파일 검색"),
    ("PowerToys", "Microsoft.PowerToys", "윈도우 유틸리티 모음"),
]

PIP_CATALOG = [
    ("pyinstaller", "EXE 빌드 (기본)"), ("nuitka", "C로 컴파일하는 EXE 빌드"), ("cx_Freeze", "또 다른 EXE 빌더"),
    ("auto-py-to-exe", "PyInstaller GUI"), ("PySide6", "Qt GUI (이 프로그램과 같은 것)"), ("PyQt6", "Qt GUI"),
    ("customtkinter", "모던한 tkinter"), ("ttkbootstrap", "테마 있는 tkinter"), ("pywebview", "HTML로 GUI 만들기"),
    ("pygame", "2D 게임"), ("pystray", "시스템 트레이 아이콘"), ("pillow", "이미지 처리"),
    ("requests", "HTTP 요청"), ("flask", "웹 서버"), ("fastapi", "API 서버"), ("numpy", "수치 계산"),
    ("pandas", "데이터 분석"), ("matplotlib", "그래프"), ("opencv-python", "컴퓨터 비전"),
    ("pyautogui", "마우스/키보드 자동화"), ("keyboard", "전역 단축키"), ("psutil", "시스템 정보"),
    ("selenium", "브라우저 자동화"), ("beautifulsoup4", "웹 크롤링"), ("openpyxl", "엑셀 파일"),
    ("python-docx", "워드 파일"), ("pywin32", "윈도우 API"), ("rich", "예쁜 콘솔 출력"),
]


def _first_existing(paths):
    for p in paths:
        if p and Path(p).exists():
            return str(p)
    return None


def find_iscc():
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    local = os.environ.get("LOCALAPPDATA", "")
    return _first_existing([shutil.which("iscc"), Path(pf86) / "Inno Setup 6" / "ISCC.exe",
                            Path(pf) / "Inno Setup 6" / "ISCC.exe",
                            Path(local) / "Programs" / "Inno Setup 6" / "ISCC.exe"])


def find_upx_dir():
    exe = shutil.which("upx")
    if not exe:
        pkgs = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
        hits = list(pkgs.glob("UPX.UPX*/**/upx.exe")) if pkgs.exists() else []
        exe = str(hits[0]) if hits else None
    return str(Path(exe).parent) if exe else None
