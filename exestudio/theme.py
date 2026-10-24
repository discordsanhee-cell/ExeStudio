from PySide6.QtGui import QColor

DEFAULT_THEME = "다크 (기본)"

_COMMON = {"danger": "#e5484d", "success": "#30a46c", "warning": "#f5a524"}

THEMES = {
    "다크 (기본)": dict(bg="#14151c", surface="#1c1d27", surface2="#252635", input="#191a23", border="#2e3044",
                      text="#e7e8f0", sub="#8f92ab", accent="#7c6cff", console="#101117"),
    "미드나잇 블루": dict(bg="#0b1220", surface="#111a2e", surface2="#18233b", input="#0e1626", border="#22304d",
                     text="#e3ebff", sub="#8597bd", accent="#3b82f6", console="#080e1a"),
    "네온 사이버": dict(bg="#0a0612", surface="#130b22", surface2="#1d1133", input="#100920", border="#3a1f5c",
                    text="#f2e9ff", sub="#a48cc8", accent="#ff2a6d", console="#07040d"),
    "포레스트": dict(bg="#0f1512", surface="#16201b", surface2="#1e2b24", input="#121a16", border="#2a3b32",
                 text="#e4f1e9", sub="#8daa99", accent="#34c47c", console="#0b100d"),
    "선셋": dict(bg="#1a1214", surface="#24191c", surface2="#2f2125", input="#1f1618", border="#422d32",
               text="#fbe9e4", sub="#c49a92", accent="#ff7e5f", console="#140e10"),
    "라이트": dict(bg="#f3f4f8", surface="#ffffff", surface2="#eef0f6", input="#ffffff", border="#dcdfe8",
                text="#1b1d29", sub="#6a6f85", accent="#5b5bf6", console="#f7f8fb"),
    "벚꽃 라이트": dict(bg="#fff6f8", surface="#ffffff", surface2="#ffeef2", input="#ffffff", border="#f6d3dc",
                   text="#3d2a31", sub="#9a7882", accent="#ff6b9a", console="#fffafb"),
}


def _rgba(color, alpha):
    c = QColor(color)
    return f"rgba({c.red()},{c.green()},{c.blue()},{alpha})"


def resolve(name, accent=""):
    t = dict(_COMMON)
    t.update(THEMES.get(name) or THEMES[DEFAULT_THEME])
    if accent:
        t["accent"] = accent
    t["accent_hover"] = QColor(t["accent"]).lighter(112).name()
    t["accent_soft"] = _rgba(t["accent"], 60)
    t["dark"] = QColor(t["bg"]).lightness() < 128
    return t


def titlebar_from_theme(t, title="EXE Studio"):
    btn = {"fg": t["sub"], "bg": "transparent", "hover_bg": t["surface2"], "hover_fg": t["text"]}
    return {
        "title": title, "bg": t["surface"], "bg2": "", "fg": t["text"], "border": t["border"],
        "icon_text": "◆", "icon_color": t["accent"], "bold": True,
        "colors": {"pin": dict(btn), "min": dict(btn), "max": dict(btn),
                   "close": {"fg": t["sub"], "bg": "transparent", "hover_bg": "#e81123", "hover_fg": "#ffffff"}},
    }


QSS = """
QWidget { color: %(text)s; }
#FramelessContent, #Page, QStackedWidget { background: %(bg)s; }
#Sidebar { background: %(surface)s; border-right: 1px solid %(border)s; }
#Logo { font-size: 15pt; font-weight: 800; color: %(text)s; }
#LogoSub { color: %(sub)s; font-size: 8pt; }
#NavButton { text-align: left; padding: 9px 14px; border: none; border-radius: 9px; background: transparent; color: %(sub)s; }
#NavButton:hover { background: %(surface2)s; color: %(text)s; }
#NavButton:checked { background: %(accent_soft)s; color: %(text)s; font-weight: 600; }
#Card { background: %(surface)s; border: 1px solid %(border)s; border-radius: 14px; }
#Card[selected="true"] { border: 2px solid %(accent)s; }
#Tile { background: %(surface)s; border: 1px solid %(border)s; border-radius: 14px; padding: 14px; text-align: left; }
#Tile:hover { border-color: %(accent)s; background: %(surface2)s; }
#Tile:checked { border: 2px solid %(accent)s; background: %(accent_soft)s; }
QLabel { background: transparent; }
QLabel#H1 { font-size: 20pt; font-weight: 800; }
QLabel#H2 { font-size: 13pt; font-weight: 700; }
QLabel#Sub { color: %(sub)s; }
QLabel#Big { font-size: 26pt; }
QLabel#Ok { color: %(success)s; font-weight: 600; }
QLabel#Bad { color: %(danger)s; font-weight: 600; }
QPushButton { background: %(surface2)s; border: 1px solid %(border)s; border-radius: 8px; padding: 7px 14px; }
QPushButton:hover { border-color: %(accent)s; }
QPushButton:pressed { background: %(border)s; }
QPushButton:disabled { color: %(sub)s; background: %(surface)s; border-color: %(surface2)s; }
QPushButton:checked { background: %(accent_soft)s; border-color: %(accent)s; }
QPushButton[accent="true"] { background: %(accent)s; color: #ffffff; border: none; font-weight: 700; }
QPushButton[accent="true"]:hover { background: %(accent_hover)s; }
QPushButton[accent="true"]:disabled { background: %(border)s; color: %(sub)s; }
QPushButton[danger="true"] { background: %(danger)s; color: #ffffff; border: none; }
QPushButton[flat="true"] { background: transparent; border: none; padding: 4px 8px; }
QPushButton[flat="true"]:hover { background: %(surface2)s; }
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: %(input)s; border: 1px solid %(border)s; border-radius: 7px; padding: 5px 8px;
    selection-background-color: %(accent)s; selection-color: #ffffff; }
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QComboBox:focus { border-color: %(accent)s; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: %(surface)s; border: 1px solid %(border)s; selection-background-color: %(accent)s; outline: 0; }
QSpinBox::up-button, QSpinBox::down-button { width: 16px; border: none; background: transparent; }
QListWidget, QTreeWidget, QTableWidget { background: %(surface)s; border: 1px solid %(border)s; border-radius: 9px; outline: 0; alternate-background-color: %(surface2)s; }
QListWidget::item, QTreeWidget::item { padding: 6px; border-radius: 6px; }
QListWidget::item:selected, QTreeWidget::item:selected, QTableWidget::item:selected { background: %(accent_soft)s; color: %(text)s; }
QListWidget::item:hover { background: %(surface2)s; }
QHeaderView::section { background: %(surface2)s; border: none; padding: 6px; color: %(sub)s; font-weight: 600; }
QTableWidget { gridline-color: %(border)s; }
QTableCornerButton::section { background: %(surface2)s; border: none; }
QTabWidget::pane { border: 1px solid %(border)s; border-radius: 9px; top: -1px; background: %(surface)s; }
QTabBar::tab { background: transparent; padding: 7px 14px; color: %(sub)s; border: none; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: %(text)s; border-bottom: 2px solid %(accent)s; }
QTabBar::tab:hover { color: %(text)s; }
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget#ScrollBody { background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: %(border)s; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: %(sub)s; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 0; }
QScrollBar::handle:horizontal { background: %(border)s; border-radius: 5px; min-width: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }
QCheckBox, QRadioButton { spacing: 8px; background: transparent; }
QCheckBox::indicator { width: 16px; height: 16px; border-radius: 4px; border: 1px solid %(sub)s; background: %(input)s; }
QCheckBox::indicator:checked { background: %(accent)s; border-color: %(accent)s; }
QRadioButton::indicator { width: 16px; height: 16px; border-radius: 8px; border: 1px solid %(sub)s; background: %(input)s; }
QRadioButton::indicator:checked { background: %(accent)s; border-color: %(accent)s; }
QGroupBox { border: 1px solid %(border)s; border-radius: 12px; margin-top: 14px; padding: 14px 10px 10px 10px; background: %(surface)s; font-weight: 700; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: %(sub)s; }
QProgressBar { background: %(input)s; border: 1px solid %(border)s; border-radius: 6px; text-align: center; color: %(text)s; }
QProgressBar::chunk { background: %(accent)s; border-radius: 5px; }
QSlider::groove:horizontal { height: 6px; background: %(border)s; border-radius: 3px; }
QSlider::sub-page:horizontal { background: %(accent)s; border-radius: 3px; }
QSlider::handle:horizontal { width: 16px; margin: -5px 0; border-radius: 8px; background: %(accent)s; }
QToolTip { background: %(surface2)s; color: %(text)s; border: 1px solid %(border)s; padding: 5px; border-radius: 6px; }
QMenu { background: %(surface)s; border: 1px solid %(border)s; padding: 4px; }
QMenu::item { padding: 6px 18px; border-radius: 5px; }
QMenu::item:selected { background: %(accent_soft)s; }
QSplitter::handle { background: %(border)s; }
QSplitter::handle:horizontal { width: 1px; }
QSplitter::handle:vertical { height: 1px; }
QPlainTextEdit#Console { font-family: Consolas, "D2Coding", monospace; font-size: 9pt; background: %(console)s; border-radius: 9px; }
#Toast { background: %(surface2)s; border: 1px solid %(accent)s; border-radius: 10px; padding: 10px 16px; color: %(text)s; font-weight: 600; }
#UpdateBanner { background: %(surface)s; border-top: 2px solid %(accent)s; }
#UpdateBanner QTextBrowser { background: %(input)s; border: 1px solid %(border)s; border-radius: 8px; padding: 6px; }
#Divider { background: %(border)s; max-height: 1px; min-height: 1px; }
#CanvasHolder { background: %(input)s; border: 1px dashed %(border)s; border-radius: 10px; }
QDialog, QMessageBox, QColorDialog, QFileDialog, QInputDialog { background: %(bg)s; }
"""


def build_qss(t):
    return QSS % t
