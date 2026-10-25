"""Startup check: makes sure the built-in Python has the packages the blocks need, and refreshes the virus database.

Runs in the background when the app starts. With no internet it does nothing and the app keeps using what it has.
"""

import socket
import subprocess
import time

from .config import BUNDLED_PYTHON, DATA_DIR

REQUIRED = {"yara": "yara-python", "serial": "pyserial", "psutil": "psutil", "PySide6": "PySide6",
            "PIL": "pillow"}
DB_MAX_AGE = 24 * 3600  # refresh the virus database at most once a day
STAMP = DATA_DIR / "clamav" / "last_update.txt"
CREATE_NO_WINDOW = 0x08000000


def online(timeout=3):
    try:
        socket.create_connection(("pypi.org", 443), timeout=timeout).close()
        return True
    except OSError:
        return False


def missing_packages():
    """Checked inside the built-in Python, because the running EXE does not contain these packages."""
    if not BUNDLED_PYTHON.exists():
        return []
    probe = "import importlib.util,sys\nfor m in sys.argv[1:]:\n    print(m) if importlib.util.find_spec(m) is None else None"
    mods = list(REQUIRED)
    out = subprocess.run([str(BUNDLED_PYTHON), "-c", probe, *mods], capture_output=True, text=True,
                         creationflags=CREATE_NO_WINDOW, timeout=60).stdout.split()
    return [REQUIRED[m] for m in out if m in REQUIRED]


def install_missing(log=print):
    """Installs missing packages into the built-in Python. Returns the list it installed."""
    missing = missing_packages()
    if not missing or not BUNDLED_PYTHON.exists():
        return []
    if not online():
        log("인터넷이 없어서 패키지 자동 설치를 건너뛰어요: " + ", ".join(missing))
        return []
    log("필요한 패키지를 설치하는 중: " + ", ".join(missing))
    subprocess.run([str(BUNDLED_PYTHON), "-m", "pip", "install", "-q", *missing], creationflags=CREATE_NO_WINDOW,
                   timeout=900, check=False)
    return missing


def update_virus_db(log=print):
    """Refreshes ClamAV signatures once a day, only if ClamAV is installed and there is internet."""
    from . import scanner
    if scanner.clamav_exe() is None:
        log("ClamAV가 설치되어 있지 않아서 바이러스 DB 업데이트를 건너뛰어요.")
        return False
    if STAMP.exists() and time.time() - STAMP.stat().st_mtime < DB_MAX_AGE:
        return False
    if not online():
        log("인터넷이 없어서 바이러스 DB는 이전 버전을 그대로 써요.")
        return False
    scanner.clamav_update()
    STAMP.parent.mkdir(parents=True, exist_ok=True)
    STAMP.write_text(str(time.time()), encoding="utf-8")
    log("바이러스 DB를 업데이트했어요.")
    return True


def copy_scan_rules():
    """Copies the YARA rules next to the app data, so programs built with the download block can find them."""
    import shutil
    from .config import resource_dir
    src = resource_dir() / "assets" / "yara"
    dst = DATA_DIR / "yara"
    if not src.exists():
        return
    dst.mkdir(parents=True, exist_ok=True)
    for f in src.iterdir():
        target = dst / f.name
        if not target.exists() or target.stat().st_size != f.stat().st_size:
            shutil.copyfile(f, target)


def run_all(log=print):
    install_missing(log)
    copy_scan_rules()
    from . import scanner
    scanner.clamav_install_bundled(log)  # unpacks the msi inside the app, offline
    update_virus_db(log)
