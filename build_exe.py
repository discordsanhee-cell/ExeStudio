"""
Builds EXE Studio into dist/ExeStudio/ExeStudio.exe

    .venv\\Scripts\\python.exe build_exe.py              # full build (runtime + exe)
    .venv\\Scripts\\python.exe build_exe.py --skip-runtime  # reuse existing runtime/ folder

The bundled runtime/ is a complete Python 3.12 with PyInstaller, Nuitka, PySide6 and other popular
packages preinstalled, so the finished app works on PCs without Python and without internet.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / "runtime"
DIST = ROOT / "dist" / "ExeStudio"

RUNTIME_PACKAGES = [
    "pip", "setuptools", "wheel",
    "pyinstaller", "pyinstaller-hooks-contrib", "nuitka", "zstandard", "ordered-set", "cx_Freeze",
    "PySide6", "customtkinter", "ttkbootstrap", "pywebview", "pygame", "pystray", "pillow",
    "requests", "flask", "numpy", "pyautogui", "keyboard", "psutil", "pywin32", "rich", "colorama",
    "openpyxl", "beautifulsoup4",
]

SKIP_DIRS = {"__pycache__", "site-packages", "test", "Doc", "Scripts", "idlelib", "turtledemo"}


def run(cmd, **kw):
    print("\n$", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, **kw)


def make_icon():
    from PIL import Image, ImageDraw, ImageFont
    size = 512
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    grad = Image.new("RGBA", (size, size))
    a, b = (124, 108, 255), (90, 209, 255)
    px = grad.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * size)
            px[x, y] = tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3)) + (255,)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((16, 16, size - 16, size - 16), radius=112, fill=255)
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 230)
    except OSError:
        font = ImageFont.load_default()
    d.text((size / 2, size / 2 + 8), "EX", font=font, fill="white", anchor="mm")
    (ROOT / "assets").mkdir(exist_ok=True)
    img.save(ROOT / "assets" / "icon.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    img.save(ROOT / "assets" / "icon.png")
    print("icon ->", ROOT / "assets" / "icon.ico")


def find_base_python():
    out = subprocess.run(["py", "-3.12", "-c", "import sys;print(sys.base_prefix)"], capture_output=True,
                         text=True, check=True).stdout.strip()
    return Path(out)


def build_runtime():
    base = find_base_python()
    print("base python:", base)
    if RUNTIME.exists():
        shutil.rmtree(RUNTIME)

    def ignore(dirpath, names):
        rel = Path(dirpath).relative_to(base)
        skip = {n for n in names if n in SKIP_DIRS}
        if rel == Path("Lib") and "site-packages" in names:
            skip.discard("site-packages")
        if rel == Path("Lib/site-packages"):
            skip = set(names)  # start with an empty site-packages
        return skip

    shutil.copytree(base, RUNTIME, ignore=ignore)
    (RUNTIME / "Lib" / "site-packages").mkdir(exist_ok=True)
    py = RUNTIME / "python.exe"
    env = dict(os.environ, PYTHONNOUSERSITE="1", PIP_DISABLE_PIP_VERSION_CHECK="1")
    run([py, "-m", "ensurepip", "--upgrade", "--default-pip"], env=env)
    run([py, "-m", "pip", "install", "--upgrade", "--no-warn-script-location", *RUNTIME_PACKAGES], env=env)
    run([py, "-c", "import PyInstaller, PySide6, nuitka; print('runtime OK', PyInstaller.__version__)"], env=env)


def build_exe():
    sep = os.pathsep
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--onedir",
         "--name", "ExeStudio", "--icon", ROOT / "assets" / "icon.ico",
         "--add-data", f"{ROOT / 'exestudio' / 'frameless.py'}{sep}exestudio",
         "--add-data", f"{ROOT / 'exestudio' / 'block_runtime.py'}{sep}exestudio",
         "--add-data", f"{ROOT / 'assets'}{sep}assets",
         "--distpath", ROOT / "dist", "--workpath", ROOT / "build", "--specpath", ROOT / "build",
         ROOT / "main.py"], cwd=ROOT)


def copy_runtime():
    dest = DIST / "runtime"
    if dest.exists():
        shutil.rmtree(dest)
    print("\ncopying runtime ->", dest, flush=True)
    r = subprocess.run(["robocopy", str(RUNTIME), str(dest), "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NP",
                        "/MT:16"])
    if r.returncode >= 8:
        raise SystemExit(f"robocopy failed ({r.returncode})")


def folder_size(p):
    return sum(f.stat().st_size for f in Path(p).rglob("*") if f.is_file())


# ---------------------------------------------------------------- release / update publishing
RELEASE = ROOT / "release"
UPDATE_SOURCE_FILE = ROOT / "assets" / "update_source.txt"


def app_version():
    sys.path.insert(0, str(ROOT))
    from exestudio.config import APP_VERSION
    return APP_VERSION


def release_notes(version):
    """Section '## <version>' of release_notes.md (or the whole file)."""
    path = ROOT / "release_notes.md"
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8")
    parts = re.split(r"(?m)^##\s+", text)
    for part in parts[1:]:
        head, _, body = part.partition("\n")
        if head.strip().lstrip("v") == version:
            return body.strip()
    return text.strip()


def make_zip(dest, include_runtime):
    import zipfile
    print(f"\nzipping -> {dest.name}", flush=True)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for f in DIST.rglob("*"):
            rel = f.relative_to(DIST.parent)
            if f.is_file() and (include_runtime or rel.parts[1] != "runtime"):
                z.write(f, rel)
    return dest


def publish(full):
    import datetime
    import hashlib
    ver = app_version()
    RELEASE.mkdir(exist_ok=True)
    for old in RELEASE.glob("*"):
        old.unlink()
    pkg = make_zip(RELEASE / f"ExeStudio-{ver}-update.zip", include_runtime=False)
    sha = hashlib.sha256(pkg.read_bytes()).hexdigest()
    manifest = {"version": ver, "date": datetime.date.today().isoformat(), "notes": release_notes(ver),
                "package": pkg.name, "size": pkg.stat().st_size, "sha256": sha}
    (RELEASE / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    if full:
        make_zip(RELEASE / f"ExeStudio-{ver}-full.zip", include_runtime=True)
    print(f"release files -> {RELEASE}")
    return ver, manifest


def github_token():
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not tok and shutil.which("gh"):
        tok = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True).stdout.strip()
    if not tok:
        raise SystemExit("GitHub 토큰이 없어요. 'gh auth login'으로 로그인하거나 GITHUB_TOKEN 환경변수를 설정하세요.")
    return tok


def upload(repo, ver, manifest):
    import urllib.parse
    import urllib.request
    tok = github_token()
    hdr = {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json", "User-Agent": "ExeStudio"}

    def api(method, url, data=None, ctype="application/json"):
        body = json.dumps(data).encode() if isinstance(data, dict) else data
        req = urllib.request.Request(url, data=body, method=method, headers=dict(hdr, **{"Content-Type": ctype}))
        with urllib.request.urlopen(req, timeout=3600) as r:
            return json.loads(r.read() or b"{}")

    rel = api("POST", f"https://api.github.com/repos/{repo}/releases",
              {"tag_name": f"v{ver}", "name": f"EXE Studio v{ver}", "body": manifest["notes"], "draft": False})
    upload_base = rel["upload_url"].split("{")[0]
    for f in sorted(RELEASE.glob("*")):
        print(f"uploading {f.name} ({f.stat().st_size / 1024 / 1024:.0f} MB)…", flush=True)
        ctype = "application/json" if f.suffix == ".json" else "application/zip"
        api("POST", f"{upload_base}?name={urllib.parse.quote(f.name)}", f.read_bytes(), ctype)
    print("published:", rel["html_url"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-runtime", action="store_true")
    ap.add_argument("--update-source", help="업데이트를 받을 곳 (예: 아이디/저장소). 앱 기본값으로 저장돼요")
    ap.add_argument("--publish", action="store_true", help="release/ 폴더에 업데이트 zip + manifest.json 만들기")
    ap.add_argument("--full", action="store_true", help="새 PC 설치용 전체 zip(내장 파이썬 포함)도 만들기")
    ap.add_argument("--upload", metavar="OWNER/REPO", help="GitHub Releases에 올리기")
    args = ap.parse_args()
    if args.update_source is not None:
        UPDATE_SOURCE_FILE.write_text(args.update_source.strip(), encoding="utf-8")
    elif args.upload and not UPDATE_SOURCE_FILE.exists():
        UPDATE_SOURCE_FILE.write_text(args.upload, encoding="utf-8")
    make_icon()
    if not args.skip_runtime or not (RUNTIME / "python.exe").exists():
        build_runtime()
    build_exe()
    copy_runtime()
    for doc in ("LICENSE", "LICENSE.ko.md", "THIRD_PARTY_NOTICES.md", "release_notes.md"):
        shutil.copy2(ROOT / doc, DIST / doc)
    print(f"\nDONE  {DIST / 'ExeStudio.exe'}  total {folder_size(DIST) / 1024 ** 3:.2f} GB")
    if args.publish or args.upload:
        ver, man = publish(args.full)
        if args.upload:
            upload(args.upload, ver, man)
