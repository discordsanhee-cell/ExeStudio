import json
import os
import sys
import traceback

from PySide6.QtCore import QObject, QRect, Qt, Signal
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (QApplication, QButtonGroup, QFrame, QHBoxLayout, QMessageBox, QPushButton,
                               QStackedWidget, QVBoxLayout, QWidget)

from . import theme as theme_mod
from . import toolchain
from .config import APP_NAME, APP_VERSION, AUTOSAVE_DIR, DATA_DIR, Settings, resource_dir
from .frameless import FramelessWindow, merge_config
from .pages.blocks import BlocksPage
from .pages.build import BuildPage
from .pages.designer import DesignerPage
from .pages.editor import EditorPage
from .pages.home import HomePage
from .pages.icon import IconPage
from .pages.installer import InstallerPage
from .pages.new_project import NewProjectPage
from .pages.packages import PackagesPage
from .pages.settings_page import SettingsPage
from .pages.titlebar_page import TitleBarPage
from .pages.tools import ToolsPage
from .update_ui import UpdateBanner, check_for_updates
from .widgets import InterpreterCombo, Toast, label, run_async

PAGES = [
    ("home", "🏠", "홈", HomePage),
    ("templates", "✨", "새 프로젝트", NewProjectPage),
    ("blocks", "🧩", "블록 코딩", BlocksPage),
    ("designer", "🎨", "GUI 디자이너", DesignerPage),
    ("titlebar", "🪟", "타이틀바 꾸미기", TitleBarPage),
    ("editor", "📝", "코드 에디터", EditorPage),
    ("packages", "📦", "패키지 관리", PackagesPage),
    ("build", "🔨", "EXE 빌드", BuildPage),
    ("installer", "💿", "설치파일 만들기", InstallerPage),
    ("icon", "🖼", "아이콘 만들기", IconPage),
    ("tools", "🧰", "도구 설치", ToolsPage),
    ("settings", "⚙", "설정", SettingsPage),
]


class AppContext(QObject):
    interpreters_changed = Signal()
    python_changed = Signal(str)
    titlebar_changed = Signal(dict)

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.interpreters = []
        self.interpreters_loaded = False
        self.main = None
        self.theme = theme_mod.resolve(settings["theme"], settings.get("accent", ""))

    # ---- python --------------------------------------------------------
    def python(self):
        sel = self.settings.get("python")
        paths = [i["path"] for i in self.interpreters]
        if sel and (sel in paths or (not self.interpreters_loaded and os.path.exists(sel))):
            return sel
        return paths[0] if paths else ""

    def set_python(self, path):
        self.settings["python"] = path
        self.settings.save()
        self.python_changed.emit(path)

    def refresh_interpreters(self, callback=None):
        custom = list(self.settings.get("custom_pythons", []))

        def done(found):
            self.interpreters = found
            self.interpreters_loaded = True
            self.interpreters_changed.emit()
            self.python_changed.emit(self.python())
            if callback:
                callback()

        run_async(lambda: toolchain.discover_pythons(custom), done)

    # ---- title bars ----------------------------------------------------
    def design_titlebar(self):
        return merge_config(self.settings.get("design_titlebar") or {})

    def set_design_titlebar(self, cfg):
        self.settings["design_titlebar"] = merge_config(cfg)
        self.settings.save()
        self.titlebar_changed.emit(self.design_titlebar())

    def app_titlebar(self):
        if self.settings.get("app_titlebar_mode") == "custom" and self.settings.get("app_titlebar"):
            return merge_config(self.settings["app_titlebar"])
        return merge_config(theme_mod.titlebar_from_theme(self.theme))

    def set_app_titlebar(self, cfg):
        if cfg is None:
            self.settings["app_titlebar_mode"] = "theme"
        else:
            self.settings["app_titlebar_mode"] = "custom"
            self.settings["app_titlebar"] = merge_config(cfg)
        self.settings.save()
        if self.main:
            self.main.set_titlebar_config(self.app_titlebar())

    # ---- theme ---------------------------------------------------------
    def apply_theme(self):
        s = self.settings
        self.theme = theme_mod.resolve(s["theme"], s.get("accent", ""))
        app = QApplication.instance()
        app.setFont(QFont(["Segoe UI", "Malgun Gothic"], int(s.get("font_size", 10))))
        app.setStyleSheet(theme_mod.build_qss(self.theme))
        s.save()
        if self.main:
            self.main.set_titlebar_config(self.app_titlebar())

    def toast(self, text):
        if self.main:
            self.main.toast.show_text(text)


class MainWindow(FramelessWindow):
    def __init__(self, ctx):
        super().__init__(ctx.app_titlebar())
        self.ctx = ctx
        self.setMinimumSize(1000, 640)
        row = QHBoxLayout(self.content)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(224)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(12, 16, 12, 12)
        sl.setSpacing(3)
        sl.addWidget(label("◆ EXE Studio", "Logo"))
        sl.addWidget(label(f"v{APP_VERSION} · 무엇이든 만드는 스튜디오", "LogoSub"))
        sl.addSpacing(12)
        self.nav = QButtonGroup(self)
        self.nav.setExclusive(True)
        self.stack = QStackedWidget()
        self.pages = {}
        self.keys = []
        for i, (key, emoji, name, cls) in enumerate(PAGES):
            b = QPushButton(f"  {emoji}    {name}")
            b.setObjectName("NavButton")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            self.nav.addButton(b, i)
            sl.addWidget(b)
            page = cls(ctx)
            self.pages[key] = page
            self.keys.append(key)
            self.stack.addWidget(page)
        self.nav.idClicked.connect(self._nav)
        sl.addStretch(1)
        sl.addWidget(label("사용할 파이썬", "LogoSub"))
        combo = InterpreterCombo(ctx)
        combo.setMinimumWidth(0)
        sl.addWidget(combo)
        row.addWidget(side)
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        right.addWidget(self.stack, 1)
        self.update_banner = UpdateBanner(ctx)
        right.addWidget(self.update_banner)
        row.addLayout(right, 1)
        self.skip_save_prompt = False
        self.toast = Toast(self)
        self._restore_geometry()
        self.goto("home")

    def _nav(self, i):
        self.stack.setCurrentIndex(i)
        self.stack.currentWidget().on_show()

    def page(self, key):
        return self.pages[key]

    def goto(self, key):
        i = self.keys.index(key)
        self.nav.button(i).setChecked(True)
        self._nav(i)

    def _restore_geometry(self):
        g = self.ctx.settings.get("geometry")
        screen = QApplication.primaryScreen().availableGeometry()
        if g and len(g) == 4:
            rect = QRect(*g)
            if any(s.availableGeometry().intersects(rect) for s in QApplication.screens()):
                self.setGeometry(rect)
                return
        w, h = min(1360, screen.width() - 80), min(860, screen.height() - 80)
        self.setGeometry(screen.x() + (screen.width() - w) // 2, screen.y() + (screen.height() - h) // 2, w, h)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.toast.isVisible():
            self.toast.move(self.width() - self.toast.width() - 24, self.height() - self.toast.height() - 24)

    def closeEvent(self, e):
        if not self.skip_save_prompt and not self.pages["editor"].maybe_save_all():
            e.ignore()
            return
        g = self.normal_geometry()
        self.ctx.settings["geometry"] = [g.x(), g.y(), g.width(), g.height()]
        self.ctx.settings["clean_exit"] = True
        self.ctx.settings.save()
        super().closeEvent(e)
        QApplication.instance().quit()

    def offer_recovery(self):
        """After a crash or forced shutdown, offer to bring back the autosaved design and blocks."""
        design_file, blocks_file = AUTOSAVE_DIR / "design.json", AUTOSAVE_DIR / "blocks.json"
        found = [f for f in (design_file, blocks_file) if f.exists()]
        if not found:
            return
        answer = QMessageBox.question(
            self, "작업 복구", "지난번에 EXE Studio가 제대로 꺼지지 않았어요.\n"
                            "작업하던 GUI 디자인과 블록을 복구할까요?")
        if answer != QMessageBox.StandardButton.Yes:
            for f in found:
                f.unlink(missing_ok=True)
            return
        try:
            if design_file.exists():
                designer = self.pages["designer"]
                designer.load_design(json.loads(design_file.read_text(encoding="utf-8")))
                designer.push_history()
            if blocks_file.exists():
                self.pages["blocks"].restore_autosave(json.loads(blocks_file.read_text(encoding="utf-8")))
            self.goto("blocks" if blocks_file.exists() else "designer")
            self.toast.show_text("지난 작업을 복구했어요")
        except (OSError, ValueError) as err:
            QMessageBox.warning(self, "복구 실패", str(err))


def _excepthook(etype, value, tb):
    text = "".join(traceback.format_exception(etype, value, tb))
    try:
        with open(DATA_DIR / "error.log", "a", encoding="utf-8") as f:
            f.write(text + "\n")
    except OSError:
        pass
    if QApplication.instance():
        QMessageBox.critical(None, "오류가 발생했어요", text[-3000:])


def main():
    sys.excepthook = _excepthook
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ExeStudio.App")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    icon = resource_dir() / "assets" / "icon.ico"
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))
    from PySide6.QtCore import QTimer
    settings = Settings()
    crashed_last_time = not settings.get("clean_exit", True)
    settings["clean_exit"] = False  # set back to True by a normal close
    settings.save()
    ctx = AppContext(settings)
    ctx.apply_theme()
    win = MainWindow(ctx)
    ctx.main = win
    win.show()
    ctx.refresh_interpreters()
    if crashed_last_time and not os.environ.get("EXESTUDIO_SELFTEST"):
        QTimer.singleShot(1200, win.offer_recovery)
    if settings.get("auto_update", True):
        QTimer.singleShot(2500, lambda: check_for_updates(ctx))
    shot = os.environ.get("EXESTUDIO_SELFTEST")
    if shot:  # opens the given page, saves a screenshot and quits (used to verify packaged builds)
        page = os.environ.get("EXESTUDIO_SELFTEST_PAGE", "blocks")
        QTimer.singleShot(1500, lambda: win.goto(page))
        QTimer.singleShot(9000, lambda: (win.grab().save(shot), settings.__setitem__("clean_exit", True),
                                         settings.save(), app.quit()))
    sys.exit(app.exec())
