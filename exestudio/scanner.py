"""Download safety scan: ClamAV (1st pass) then YARA (2nd pass).

Rules come from assets/yara (signature-base, DRL 1.1). Rules are not deleted; matches whose rule name matches
EXCLUDE_RULE_PATTERNS are ignored, so false-positive families can be turned off without touching the rule files.
"""
import os
import re
import shutil
import subprocess
import sys

from .config import DATA_DIR, resource_dir

RULE_DIR = resource_dir() / "assets" / "yara"
CLAMAV_DB = DATA_DIR / "clamav"  # signature database, kept up to date by freshclam
CLAMAV_BIN = DATA_DIR / "clamav-bin"  # unpacked from the bundled msi (no admin rights needed)

# Generic webshell heuristics: many false positives on ordinary PHP/ASP code. (2026 decision: keep them off)
EXCLUDE_RULE_PATTERNS = [
    r"(?i)(webshell|chopper).*generic",
    r"(?i)generic.*(webshell|chopper)",
    r"(?i)^WEBSHELL_.*Generic",
]

EXTERNALS = {k: "" for k in ("filename", "filepath", "extension", "filetype", "md5", "owner")}
CREATE_NO_WINDOW = 0x08000000


class ScanBlocked(Exception):
    """Raised when a file fails a scan. The caller must delete the file."""


_rules = None
_excluded = [re.compile(p) for p in EXCLUDE_RULE_PATTERNS]


def _load_rules():
    global _rules
    if _rules is not None:
        return _rules
    import yara
    files = {}
    for name in sorted(os.listdir(RULE_DIR)):
        if name.lower().endswith((".yar", ".yara")):
            files[os.path.splitext(name)[0]] = str(RULE_DIR / name)
    _rules = yara.compile(filepaths=files, externals=EXTERNALS)
    return _rules


def yara_hits(path):
    """Names of YARA rules that match the file, after the exclusion list is applied."""
    matches = _load_rules().match(str(path), externals=EXTERNALS)
    hits = [m.rule for m in matches]
    return [h for h in hits if not any(p.search(h) for p in _excluded)]


def clamav_dir():
    """Where the built-in ClamAV is unpacked (from the msi shipped inside the app)."""
    return CLAMAV_BIN / "ClamAV"


def clamav_exe():
    own = clamav_dir() / "clamscan.exe"
    if own.exists():
        return str(own)
    found = shutil.which("clamscan")
    if found:
        return found
    for p in (r"C:\Program Files\ClamAV\clamscan.exe", r"C:\Program Files (x86)\ClamAV\clamscan.exe"):
        if os.path.exists(p):
            return p
    return None


def clamav_update():
    """Refreshes the signature database with the official freshclam tool (run it at most a few times a day)."""
    fresh = shutil.which("freshclam") or r"C:\Program Files\ClamAV\freshclam.exe"
    if not os.path.exists(fresh):
        raise RuntimeError("ClamAV(freshclam)가 설치되어 있지 않아요.")
    CLAMAV_DB.mkdir(parents=True, exist_ok=True)
    conf = CLAMAV_DB / "freshclam.conf"
    lines = [f"DatabaseDirectory {CLAMAV_DB}", "DatabaseMirror database.clamav.net",
             f"UpdateLogFile {CLAMAV_DB / 'freshclam.log'}"]
    conf.write_text(chr(10).join(lines) + chr(10), encoding="ascii")
    proc = subprocess.run([fresh, f"--config-file={conf}"], capture_output=True, text=True,
                          creationflags=CREATE_NO_WINDOW, timeout=1800)
    if proc.returncode not in (0, 1):
        raise RuntimeError(f"DB 업데이트 실패 (코드 {proc.returncode})")



def clamav_install_bundled(log=print):
    """Unpacks the msi that ships inside the app (administrative install, no admin rights, no internet)."""
    if clamav_dir().joinpath("clamscan.exe").exists():
        return True
    msi = RULE_DIR.parent / "clamav" / "clamav-1.5.4.win.x64.msi"
    if not msi.exists():
        log("내장 ClamAV 설치 파일이 없어요.")
        return False
    CLAMAV_BIN.mkdir(parents=True, exist_ok=True)
    log("ClamAV를 준비하는 중 (처음 한 번만)…")
    proc = subprocess.run(["msiexec", "/a", str(msi), "/qn", f"TARGETDIR={CLAMAV_BIN}"],
                          creationflags=CREATE_NO_WINDOW, timeout=900)
    return proc.returncode == 0 and clamav_dir().joinpath("clamscan.exe").exists()


def clamav_scan(path):
    """Returns the virus name, or None if clean. Raises RuntimeError when ClamAV is not installed."""
    exe = clamav_exe()
    if not exe:
        raise RuntimeError("ClamAV가 설치되어 있지 않아요. 설치 후 다시 시도하세요.")
    if not any(CLAMAV_DB.glob("*.cvd")) and not any(CLAMAV_DB.glob("*.cld")):
        raise RuntimeError("ClamAV 시그니처가 없어요. 설정에서 '바이러스 DB 업데이트'를 먼저 해 주세요.")
    proc = subprocess.run([exe, "--no-summary", f"--database={CLAMAV_DB}", str(path)], capture_output=True,
                          text=True, creationflags=CREATE_NO_WINDOW, timeout=600)
    if proc.returncode == 0:
        return None
    if proc.returncode == 1:
        line = proc.stdout.strip().splitlines()[0] if proc.stdout.strip() else "알 수 없는 위협"
        return line.rsplit(":", 1)[-1].strip()
    raise RuntimeError(f"ClamAV 검사 오류 (코드 {proc.returncode}): {proc.stderr.strip()[:200]}")


def scan_file(path):
    """Two-stage check. Raises ScanBlocked on the first finding, returns None when the file passes."""
    virus = clamav_scan(path)
    if virus:
        raise ScanBlocked(f"ClamAV 탐지: {virus}")
    hits = yara_hits(path)
    if hits:
        raise ScanBlocked("YARA 탐지: " + ", ".join(hits[:5]))


if __name__ == "__main__":
    # quick CLI for testing:  python -m exestudio.scanner <file> [--yara-only]
    target = sys.argv[1]
    if "--yara-only" in sys.argv:
        print("YARA:", yara_hits(target) or "깨끗함")
    else:
        try:
            scan_file(target)
            print("통과")
        except ScanBlocked as e:
            print("차단:", e)
