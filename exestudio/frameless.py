"""
Frameless window + fully customizable title bar (PySide6).

Self-contained (PySide6 + stdlib only): EXE Studio copies this file verbatim
into the apps it generates.
"""
import copy
import sys

from PySide6.QtCore import QEvent, QPoint, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QLinearGradient, QPainter, QPainterPath
from PySide6.QtWidgets import QAbstractButton, QApplication, QHBoxLayout, QLabel, QVBoxLayout, QWidget

BUTTON_KINDS = ("pin", "min", "max", "close")


def _btn(fg, hover_bg, hover_fg=None, bg="transparent"):
    return {"fg": fg, "bg": bg, "hover_bg": hover_bg, "hover_fg": hover_fg or fg}


DEFAULT_TITLEBAR = {
    "height": 38,
    "bg": "#1c1d27",
    "bg2": "",
    "fg": "#e7e8f0",
    "border": "#2e3044",
    "bottom_line": False,
    "title": "My App",
    "title_align": "left",
    "font_size": 10,
    "bold": False,
    "icon_text": "◆",
    "icon_color": "#7c6cff",
    "side": "right",
    "order": ["pin", "min", "max", "close"],
    "shape": "rect",
    "btn_w": 46,
    "btn_size": 26,
    "symbol_size": 10,
    "show_pin": False,
    "show_min": True,
    "show_max": True,
    "dbl_click_max": True,
    "symbols": {"pin": "📌", "min": "—", "max": "☐", "restore": "❐", "close": "✕"},
    "colors": {
        "pin": _btn("#8f92ab", "#2c2d40", "#ffffff"),
        "min": _btn("#8f92ab", "#2c2d40", "#ffffff"),
        "max": _btn("#8f92ab", "#2c2d40", "#ffffff"),
        "close": _btn("#8f92ab", "#e81123", "#ffffff"),
    },
}

PRESETS = {
    "Windows 11 다크": {},
    "Windows 11 라이트": {
        "bg": "#f3f3f3", "fg": "#1b1b1b", "border": "#d0d0d0", "icon_color": "#0067c0",
        "colors": {"pin": _btn("#1b1b1b", "#e5e5e5"), "min": _btn("#1b1b1b", "#e5e5e5"),
                   "max": _btn("#1b1b1b", "#e5e5e5"), "close": _btn("#1b1b1b", "#c42b1c", "#ffffff")},
    },
    "macOS": {
        "bg": "#2b2b2e", "fg": "#d8d8dc", "border": "#3d3d42", "side": "left",
        "order": ["close", "min", "max", "pin"], "shape": "mac", "btn_size": 13, "symbol_size": 7,
        "title_align": "center", "icon_text": "",
        "symbols": {"pin": "•", "min": "−", "max": "+", "restore": "+", "close": "×"},
        "colors": {"close": _btn("#4d0000", "#ff5f57", "#4d0000", "#ff5f57"),
                   "min": _btn("#5a3d00", "#febc2e", "#5a3d00", "#febc2e"),
                   "max": _btn("#0b4d0b", "#28c840", "#0b4d0b", "#28c840"),
                   "pin": _btn("#20304d", "#5aa0ff", "#20304d", "#5aa0ff")},
    },
    "네온": {
        "bg": "#0d0221", "bg2": "#261447", "fg": "#f6f6ff", "border": "#ff2a6d", "bold": True,
        "icon_text": "⚡", "icon_color": "#05d9e8", "shape": "rounded", "btn_size": 26,
        "colors": {"pin": _btn("#05d9e8", "#05d9e8", "#0d0221"), "min": _btn("#05d9e8", "#05d9e8", "#0d0221"),
                   "max": _btn("#05d9e8", "#05d9e8", "#0d0221"), "close": _btn("#ff2a6d", "#ff2a6d", "#ffffff")},
    },
    "파스텔": {
        "bg": "#ffe5ec", "bg2": "#e0f0ff", "fg": "#5c4b6b", "border": "#f5c6d6", "shape": "circle",
        "btn_size": 24, "icon_text": "✿", "icon_color": "#ff8fab",
        "symbols": {"pin": "♥", "min": "–", "max": "○", "restore": "◎", "close": "×"},
        "colors": {"pin": _btn("#7a6a8a", "#ffd6e0", "#5c4b6b"), "min": _btn("#7a6a8a", "#c8f0d8", "#5c4b6b"),
                   "max": _btn("#7a6a8a", "#fff1b8", "#5c4b6b"), "close": _btn("#7a6a8a", "#ffb3c1", "#5c4b6b")},
    },
    "해커": {
        "bg": "#000000", "fg": "#00ff66", "border": "#00aa44", "icon_text": "▌", "icon_color": "#00ff66",
        "btn_w": 50, "symbols": {"pin": "[^]", "min": "[_]", "max": "[ ]", "restore": "[=]", "close": "[X]"},
        "colors": {"pin": _btn("#00ff66", "#003b17"), "min": _btn("#00ff66", "#003b17"),
                   "max": _btn("#00ff66", "#003b17"), "close": _btn("#00ff66", "#00ff66", "#000000")},
    },
    "선셋 그라데이션": {
        "bg": "#ff7e5f", "bg2": "#feb47b", "fg": "#ffffff", "border": "#e06a50", "bold": True,
        "icon_text": "☀", "icon_color": "#fff3b0", "shape": "rounded",
        "colors": {"pin": _btn("#ffffff", "#40ffffff"), "min": _btn("#ffffff", "#40ffffff"),
                   "max": _btn("#ffffff", "#40ffffff"), "close": _btn("#ffffff", "#c0392b")},
    },
    "오션": {
        "bg": "#0f2027", "bg2": "#2c5364", "fg": "#e0f7ff", "border": "#1f4a5a", "icon_text": "≋",
        "icon_color": "#4fc3f7", "shape": "circle", "btn_size": 22,
        "colors": {"pin": _btn("#bfe9ff", "#4fc3f7", "#0f2027"), "min": _btn("#bfe9ff", "#4fc3f7", "#0f2027"),
                   "max": _btn("#bfe9ff", "#4fc3f7", "#0f2027"), "close": _btn("#bfe9ff", "#ff5252", "#ffffff")},
    },
    "미니멀 화이트": {
        "bg": "#ffffff", "fg": "#222222", "border": "#e6e6e6", "icon_text": "", "title_align": "center",
        "btn_w": 40, "bottom_line": True, "symbols": {"min": "–", "max": "□", "restore": "❐", "close": "×"},
        "colors": {"pin": _btn("#888888", "#f0f0f0", "#222222"), "min": _btn("#888888", "#f0f0f0", "#222222"),
                   "max": _btn("#888888", "#f0f0f0", "#222222"), "close": _btn("#888888", "#ff4d4f", "#ffffff")},
    },
}


def merge_config(cfg=None):
    """Defaults deep-merged with a (possibly partial) config."""
    out = copy.deepcopy(DEFAULT_TITLEBAR)
    for key, val in (cfg or {}).items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            for k2, v2 in val.items():
                if isinstance(v2, dict) and isinstance(out[key].get(k2), dict):
                    out[key][k2].update(v2)
                else:
                    out[key][k2] = copy.deepcopy(v2)
        else:
            out[key] = copy.deepcopy(val)
    return out


def _qcolor(s):
    if not s or s == "transparent":
        return QColor(0, 0, 0, 0)
    return QColor(s)


def set_topmost(window, on):
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                            ctypes.c_int, ctypes.c_int, ctypes.c_uint]
            # HWND_TOPMOST = -1, HWND_NOTOPMOST = -2; SWP_NOSIZE|SWP_NOMOVE|SWP_NOACTIVATE
            user32.SetWindowPos(int(window.winId()), -1 if on else -2, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
            return
        except Exception:
            pass
    window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, on)
    window.show()


class TitleBarButton(QAbstractButton):
    TIPS = {"pin": "항상 위", "min": "최소화", "max": "최대화", "close": "닫기"}

    def __init__(self, kind, bar):
        super().__init__(bar)
        self.kind = kind
        self.bar = bar
        self.hovered = False
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setToolTip(self.TIPS[kind])
        self.setCheckable(kind == "pin")

    def sizeHint(self):
        cfg = self.bar.cfg
        h = int(cfg["height"])
        if cfg["shape"] == "rect":
            return QSize(int(cfg["btn_w"]), h)
        pad = 8 if cfg["shape"] == "mac" else 10
        return QSize(int(cfg["btn_size"]) + pad, h)

    def enterEvent(self, e):
        self.hovered = True
        self.bar.set_group_hover(True)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.hovered = False
        self.bar.set_group_hover(False)
        super().leaveEvent(e)

    def symbol(self):
        syms = self.bar.cfg["symbols"]
        if self.kind == "max" and self.bar.is_window_maximized():
            return syms.get("restore", "")
        return syms.get(self.kind, "")

    def paintEvent(self, e):
        cfg = self.bar.cfg
        col = cfg["colors"][self.kind]
        active = self.hovered or (self.kind == "pin" and self.isChecked())
        bg = _qcolor(col["hover_bg"] if active else col["bg"])
        fg = _qcolor(col["hover_fg"] if active else col["fg"])
        if self.isDown() and bg.alpha():
            bg = bg.darker(115)
        shape = cfg["shape"]
        r = QRectF(self.rect())
        path = QPainterPath()
        if shape == "rect":
            path.addRect(r)
        else:
            d = float(min(int(cfg["btn_size"]), r.height() - 4))
            box = QRectF(r.center().x() - d / 2, r.center().y() - d / 2, d, d)
            if shape == "rounded":
                path.addRoundedRect(box, d * 0.28, d * 0.28)
            else:
                path.addEllipse(box)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if bg.alpha():
            p.fillPath(path, bg)
        if shape != "mac" or self.bar.group_hover:
            f = QFont(self.font())
            f.setPointSizeF(max(5.0, float(cfg["symbol_size"])))
            f.setBold(shape == "mac")
            p.setFont(f)
            p.setPen(fg)
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, self.symbol())
        p.end()


class TitleBar(QWidget):
    pinToggled = Signal(bool)

    def __init__(self, parent=None, cfg=None, preview=False):
        super().__init__(parent)
        self.preview = preview
        self.group_hover = False
        self.buttons = {}
        self._press_pos = None
        self.icon_label = QLabel(self)
        self.title_label = QLabel(self)
        for lb in (self.icon_label, self.title_label):
            lb.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.btn_box = QWidget(self)
        self.btn_box.setStyleSheet("background: transparent;")
        self.btn_layout = QHBoxLayout(self.btn_box)
        self.btn_layout.setContentsMargins(0, 0, 0, 0)
        self.btn_layout.setSpacing(0)
        self.row = QHBoxLayout(self)
        self.row.setContentsMargins(0, 0, 0, 0)
        self.row.setSpacing(0)
        self.apply(cfg)

    # ---- configuration -------------------------------------------------
    def apply(self, cfg):
        self.cfg = c = merge_config(cfg)
        self.setFixedHeight(int(c["height"]))
        weight = 700 if c["bold"] else 400
        self.title_label.setText(c["title"])
        self.title_label.setStyleSheet(
            f"color:{c['fg']}; background:transparent; font-size:{c['font_size']}pt; font-weight:{weight};")
        self.icon_label.setText(c["icon_text"])
        self.icon_label.setStyleSheet(
            f"color:{c['icon_color']}; background:transparent; font-size:{float(c['font_size']) + 2}pt;")
        self.icon_label.setVisible(bool(c["icon_text"]))

        old = list(self.buttons.values())
        while self.btn_layout.count():
            self.btn_layout.takeAt(0)
        for b in old:
            b.hide()
            b.deleteLater()
        self.buttons = {}
        pad = 0 if c["shape"] == "rect" else 6
        self.btn_layout.setContentsMargins(pad, 0, pad, 0)
        order = [k for k in c["order"] if k in BUTTON_KINDS]
        order += [k for k in BUTTON_KINDS if k not in order]
        for kind in order:
            if kind != "close" and not c.get("show_" + kind, True):
                continue
            b = TitleBarButton(kind, self)
            b.clicked.connect(lambda checked=False, k=kind: self._on_button(k))
            self.btn_layout.addWidget(b)
            self.buttons[kind] = b

        while self.row.count():
            self.row.takeAt(0)
        left = c["side"] == "left"
        centered = c["title_align"] == "center"
        if left:
            self.row.addWidget(self.btn_box)
            self.row.addSpacing(8)
        else:
            self.row.addSpacing(12)
        self.row.addWidget(self.icon_label)
        if c["icon_text"]:
            self.row.addSpacing(8)
        if centered:
            self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            self.title_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            self.row.addWidget(self.title_label)
        self.row.addStretch(1)
        if not left:
            self.row.addWidget(self.btn_box)
        else:
            self.row.addSpacing(8)
        self._place_title()
        self.update()

    def set_title(self, text):
        self.cfg["title"] = text
        self.title_label.setText(text)

    def _place_title(self):
        if self.cfg["title_align"] == "center":
            self.title_label.setGeometry(0, 0, self.width(), self.height())
            self.title_label.lower()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._place_title()

    def set_group_hover(self, on):
        self.group_hover = on
        for b in self.buttons.values():
            b.update()

    def update_buttons(self):
        for b in self.buttons.values():
            b.update()

    def is_window_maximized(self):
        if self.preview:
            return False
        w = self.window()
        if hasattr(w, "is_maximized_custom"):
            return w.is_maximized_custom()
        return w.isMaximized()

    # ---- actions -------------------------------------------------------
    def _on_button(self, kind):
        if self.preview:
            return
        w = self.window()
        if kind == "close":
            w.close()
        elif kind == "min":
            w.showMinimized()
        elif kind == "max":
            if hasattr(w, "toggle_maximize"):
                w.toggle_maximize()
            elif w.isMaximized():
                w.showNormal()
            else:
                w.showMaximized()
        elif kind == "pin":
            on = self.buttons["pin"].isChecked()
            set_topmost(w, on)
            self.pinToggled.emit(on)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._press_pos = e.globalPosition().toPoint()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self.preview or self._press_pos is None or not (e.buttons() & Qt.MouseButton.LeftButton):
            return super().mouseMoveEvent(e)
        gp = e.globalPosition().toPoint()
        if (gp - self._press_pos).manhattanLength() < 4:
            return
        self._press_pos = None
        w = self.window()
        if hasattr(w, "is_maximized_custom") and w.is_maximized_custom():
            w.toggle_maximize(drag_pos=gp)
        handle = w.windowHandle()
        if handle is not None:
            handle.startSystemMove()

    def mouseReleaseEvent(self, e):
        self._press_pos = None
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):
        if not self.preview and e.button() == Qt.MouseButton.LeftButton and self.cfg["dbl_click_max"]:
            w = self.window()
            if hasattr(w, "toggle_maximize"):
                w.toggle_maximize()
        super().mouseDoubleClickEvent(e)

    def paintEvent(self, e):
        c = self.cfg
        p = QPainter(self)
        if c.get("bg2"):
            g = QLinearGradient(0, 0, self.width(), 0)
            g.setColorAt(0, _qcolor(c["bg"]))
            g.setColorAt(1, _qcolor(c["bg2"]))
            p.fillRect(self.rect(), g)
        else:
            p.fillRect(self.rect(), _qcolor(c["bg"]))
        if c.get("bottom_line"):
            p.setPen(_qcolor(c["border"]))
            p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        p.end()


class FramelessWindow(QWidget):
    """Top-level window without the OS frame. Put your UI inside `self.content`."""

    BORDER = 6

    def __init__(self, titlebar_cfg=None, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self._maxed = False
        self._normal_geo = None
        self._edge = None
        self._cursor_overridden = False
        self._native_done = False
        self.titlebar = TitleBar(self, titlebar_cfg)
        self.content = QWidget(self)
        self.content.setObjectName("FramelessContent")
        self.content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(1, 1, 1, 1)
        self._root.setSpacing(0)
        self._root.addWidget(self.titlebar)
        self._root.addWidget(self.content, 1)
        self.setWindowTitle(self.titlebar.cfg["title"])
        self._edge_timer = QTimer(self)
        self._edge_timer.setInterval(40)
        self._edge_timer.timeout.connect(self._poll_edge)
        self._edge_timer.start()
        QApplication.instance().installEventFilter(self)

    # ---- public API ----------------------------------------------------
    def setCentralWidget(self, widget):
        lay = self.content.layout()
        if lay is None:
            lay = QVBoxLayout(self.content)
            lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(widget)

    def set_titlebar_config(self, cfg):
        self.titlebar.apply(cfg)
        self.setWindowTitle(self.titlebar.cfg["title"])
        self._apply_dwm()
        self.update()

    def is_maximized_custom(self):
        return self._maxed

    def toggle_maximize(self, drag_pos=None):
        if self._maxed:
            self._maxed = False
            geo = QRect(self._normal_geo) if self._normal_geo else QRect(100, 100, 1000, 700)
            if drag_pos is not None:
                ratio = (drag_pos.x() - self.x()) / max(1, self.width())
                geo.moveTo(int(drag_pos.x() - geo.width() * ratio), drag_pos.y() - self.titlebar.height() // 2)
            self.setGeometry(geo)
        else:
            self._normal_geo = self.geometry()
            screen = self.screen() or QApplication.primaryScreen()
            self._maxed = True
            self.setGeometry(screen.availableGeometry())
        m = 0 if self._maxed else 1
        self._root.setContentsMargins(m, m, m, m)
        self.titlebar.update_buttons()
        self._apply_dwm()
        self.update()

    def normal_geometry(self):
        return QRect(self._normal_geo) if self._maxed and self._normal_geo else self.geometry()

    # ---- resize edges --------------------------------------------------
    def _edge_at(self, gp):
        g = self.geometry()
        b = self.BORDER
        left = gp.x() - g.left() < b
        right = g.right() - gp.x() < b
        top = gp.y() - g.top() < b
        bottom = g.bottom() - gp.y() < b
        if not (left or right or top or bottom):
            return None
        parts = []
        if left:
            parts.append(Qt.Edge.LeftEdge)
        if right:
            parts.append(Qt.Edge.RightEdge)
        if top:
            parts.append(Qt.Edge.TopEdge)
        if bottom:
            parts.append(Qt.Edge.BottomEdge)
        edges = parts[0]
        for part in parts[1:]:
            edges = edges | part
        if (left and top) or (right and bottom):
            shape = Qt.CursorShape.SizeFDiagCursor
        elif (right and top) or (left and bottom):
            shape = Qt.CursorShape.SizeBDiagCursor
        elif left or right:
            shape = Qt.CursorShape.SizeHorCursor
        else:
            shape = Qt.CursorShape.SizeVerCursor
        return edges, shape

    def _poll_edge(self):
        if QApplication.mouseButtons() != Qt.MouseButton.NoButton:
            return
        edge = None
        if self.isVisible() and not self._maxed and not self.isMinimized():
            gp = QCursor.pos()
            w = QApplication.widgetAt(gp)
            if w is not None and w.window() is self:
                edge = self._edge_at(gp)
        self._edge = edge
        if edge is None:
            if self._cursor_overridden:
                QApplication.restoreOverrideCursor()
                self._cursor_overridden = False
        elif self._cursor_overridden:
            QApplication.changeOverrideCursor(QCursor(edge[1]))
        else:
            QApplication.setOverrideCursor(QCursor(edge[1]))
            self._cursor_overridden = True

    def eventFilter(self, obj, ev):
        if (self._edge is not None and ev.type() == QEvent.Type.MouseButtonPress
                and isinstance(obj, QWidget) and obj.window() is self
                and ev.button() == Qt.MouseButton.LeftButton):
            handle = self.windowHandle()
            if handle is not None and handle.startSystemResize(self._edge[0]):
                return True
        return super().eventFilter(obj, ev)

    # ---- native tweaks (Windows) ---------------------------------------
    def showEvent(self, e):
        super().showEvent(e)
        if not self._native_done:
            self._native_done = True
            self._apply_native_style()
            self._apply_dwm()

    def _apply_native_style(self):
        if sys.platform != "win32":
            return
        try:
            import ctypes
            user32 = ctypes.windll.user32
            user32.GetWindowLongW.restype = ctypes.c_long
            user32.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
            user32.SetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]
            hwnd = int(self.winId())
            style = user32.GetWindowLongW(hwnd, -16)
            user32.SetWindowLongW(hwnd, -16, style | 0x00020000)  # WS_MINIMIZEBOX: taskbar click minimizes
        except Exception:
            pass

    def _apply_dwm(self):
        if sys.platform != "win32" or not self._native_done:
            return
        try:
            import ctypes
            hwnd = ctypes.c_void_p(int(self.winId()))
            dwm = ctypes.windll.dwmapi
            corner = ctypes.c_int(1 if self._maxed else 2)  # Windows 11 rounded corners
            dwm.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(corner), 4)
            c = _qcolor(self.titlebar.cfg["border"])
            ref = ctypes.c_uint(c.red() | (c.green() << 8) | (c.blue() << 16))
            dwm.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(ref), 4)
        except Exception:
            pass

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), self.palette().window())
        if not self._maxed:
            p.setPen(_qcolor(self.titlebar.cfg["border"]))
            p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        p.end()

    def closeEvent(self, e):
        if self._cursor_overridden:
            QApplication.restoreOverrideCursor()
            self._cursor_overridden = False
        super().closeEvent(e)
