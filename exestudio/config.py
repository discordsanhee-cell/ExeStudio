import json
import os
import sys
from pathlib import Path

APP_NAME = "EXE Studio"
APP_VERSION = "1.2.0"
FROZEN = getattr(sys, "frozen", False)


def resource_dir() -> Path:
    """Read-only files shipped with the app (frameless.py source, assets)."""
    if FROZEN:
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def install_dir() -> Path:
    """Folder that holds ExeStudio.exe (or the project root in dev mode)."""
    if FROZEN:
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


DATA_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "ExeStudio"
DATA_DIR.mkdir(parents=True, exist_ok=True)
SETTINGS_FILE = DATA_DIR / "settings.json"
BUNDLED_PYTHON = install_dir() / "runtime" / "python.exe"
MANAGED_PYTHON_DIR = DATA_DIR / "python"
DOWNLOAD_DIR = DATA_DIR / "downloads"
AUTOSAVE_DIR = DATA_DIR / "autosave"
DEFAULT_PROJECTS_DIR = Path.home() / "Documents" / "ExeStudio Projects"

DEFAULTS = {
    "theme": "다크 (기본)",
    "accent": "",
    "font_size": 10,
    "python": "",
    "custom_pythons": [],
    "projects_dir": str(DEFAULT_PROJECTS_DIR),
    "recent_files": [],
    "app_titlebar_mode": "theme",
    "app_titlebar": {},
    "design_titlebar": {},
    "geometry": None,
    "auto_update": True,
    "update_source": "",
    "skip_version": "",
    "clean_exit": True,
}


class Settings(dict):
    def __init__(self):
        super().__init__(json.loads(json.dumps(DEFAULTS)))
        try:
            self.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8-sig")))
        except Exception:
            pass

    def save(self):
        try:
            SETTINGS_FILE.write_text(json.dumps(self, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def add_recent(self, path):
        path = os.path.normpath(str(path))
        recent = [p for p in self.get("recent_files", [])
                  if os.path.normcase(os.path.normpath(p)) != os.path.normcase(path)]
        recent.insert(0, path)
        self["recent_files"] = recent[:15]
        self.save()
