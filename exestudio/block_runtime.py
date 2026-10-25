# ============================== 블록 런타임 ==============================
# Event system used by programs made with EXE Studio's block coding (copied verbatim into them).
# Every event handler runs in its own thread (like Entry/Scratch), and all UI work is sent to the
# GUI thread through _ui(), so long-running blocks never freeze the window.
import math
import os
import random
import threading
import time
import traceback

import subprocess

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QPainter, QPen, QPixmap, QPolygonF, QWindow
from PySide6.QtWidgets import QComboBox, QInputDialog, QListWidget, QMessageBox

_APP = QApplication.instance() or QApplication(sys.argv)
_APP.setQuitOnLastWindowClosed(False)
_WIN = None
_TITLE = "프로그램"
_STOP = threading.Event()
_STATE = {"answer": "", "active": 0, "keep_alive": False, "stage": None, "stage_window": None, "errors": 0}
_COUNT_LOCK = threading.Lock()
_HANDLERS = {"start": [], "key": [], "click": [], "change": [], "every": [], "msg": [], "mouse": [], "usb_in": [], "usb_out": [], "serial": [],
             "sprite_click": []}
_KEYS_DOWN = set()
_CLICKABLE = {}


class _Stop(Exception):
    pass


class _Bridge(QObject):
    call = Signal(object)

    def __init__(self):
        super().__init__()
        self.call.connect(self._run, Qt.ConnectionType.BlockingQueuedConnection)

    def _run(self, box):
        try:
            box[1] = box[0]()
        except BaseException as e:
            box[2] = e


_BRIDGE = _Bridge()


def _ui(fn):
    """Run fn on the GUI thread and return its result."""
    if threading.current_thread() is threading.main_thread():
        return fn()
    if _STOP.is_set():
        raise _Stop()
    box = [fn, None, None]
    _BRIDGE.call.emit(box)
    if box[2] is not None:
        raise box[2]
    return box[1]


# Scripts take turns like in Scratch/Entry: only the script holding _RUN executes block code. It lets
# the others run while it waits, at the end of every loop pass, and while a dialog is open.
_RUN = threading.Lock()
_LOCAL = threading.local()


class _released:
    def __enter__(self):
        self.held = getattr(_LOCAL, "held", False)
        if self.held:
            _LOCAL.held = False
            _RUN.release()

    def __exit__(self, *exc):
        if self.held:
            _RUN.acquire()
            _LOCAL.held = True
        return False


def _tick():
    if _STOP.is_set():
        raise _Stop()
    with _released():
        time.sleep(0.0005)
    if _STOP.is_set():
        raise _Stop()


def _wait(sec):
    if _TRACE["on"] and _TRACE["cur"]:
        _TRACE["last"] = 0.0
        _hl(_TRACE["cur"])  # make sure a waiting block is the one shown as running
    end = time.time() + max(0.0, float(_num(sec)))
    with _released():
        while True:
            if _STOP.is_set():
                raise _Stop()
            left = end - time.time()
            if left <= 0:
                break
            time.sleep(min(0.05, left))
    if _STOP.is_set():
        raise _Stop()


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0
    return int(f) if f.is_integer() else f


# ---------------------------------------------------------------- events
def _on(kind, arg=None):
    def deco(fn):
        _HANDLERS[kind].append((arg, fn))
        return fn
    return deco


def _run_handler(fn):
    with _COUNT_LOCK:
        _STATE["active"] += 1
    try:
        _RUN.acquire()
        _LOCAL.held = True
        fn()
    except (_Stop, SystemExit):
        pass
    except Exception:
        msg = traceback.format_exc(limit=3)
        _STATE["errors"] += 1
        if _STATE["errors"] <= 3:
            try:
                with _released():
                    _ui(lambda: QMessageBox.warning(_parent(), "블록 실행 중 오류", msg[-1500:]))
            except Exception:
                pass
    finally:
        if getattr(_LOCAL, "held", False):
            _LOCAL.held = False
            _RUN.release()
        with _COUNT_LOCK:
            _STATE["active"] -= 1
        _maybe_quit()


def _spawn(fn):
    threading.Thread(target=_run_handler, args=(fn,), daemon=True).start()


def _fire(kind, arg=None):
    for a, fn in _HANDLERS[kind]:
        if a == arg or a == "any":
            _spawn(fn)


def _broadcast(name):
    _fire("msg", str(name))


def _every_loop(interval, fn):
    while not _STOP.is_set():
        try:
            _wait(interval)
        except _Stop:
            return
        _run_handler(fn)


def _our_windows_open():
    wins = [_WIN, _STATE["stage_window"]]
    return any(w is not None and w.isVisible() for w in wins)


def _maybe_quit():
    if _STATE["active"] == 0 and not _STATE["keep_alive"] and not _our_windows_open() and not _STOP.is_set():
        try:
            _ui(_APP.quit)
        except _Stop:
            pass


def _exit():
    try:
        _ui(_APP.quit)
    finally:
        _STOP.set()
    raise _Stop()


# ---------------------------------------------------------------- keys / clicks / close
_KEYMAP = {Qt.Key.Key_Space: "space", Qt.Key.Key_Return: "enter", Qt.Key.Key_Enter: "enter",
           Qt.Key.Key_Up: "up", Qt.Key.Key_Down: "down", Qt.Key.Key_Left: "left", Qt.Key.Key_Right: "right",
           Qt.Key.Key_Escape: "esc", Qt.Key.Key_Tab: "tab", Qt.Key.Key_Backspace: "backspace",
           Qt.Key.Key_Shift: "shift", Qt.Key.Key_Control: "ctrl", Qt.Key.Key_Alt: "alt"}
_KEYMAP = {int(k.value): v for k, v in _KEYMAP.items()}
_F1 = int(Qt.Key.Key_F1.value)


def _key_name(ev):
    k = int(ev.key())
    if k in _KEYMAP:
        return _KEYMAP[k]
    if _F1 <= k < _F1 + 12:
        return f"f{k - _F1 + 1}"
    if 0x30 <= k <= 0x39 or 0x41 <= k <= 0x5A:
        return chr(k).lower()
    return None


def _key_down(name):
    return str(name) in _KEYS_DOWN


class _Filter(QObject):
    def eventFilter(self, obj, ev):
        t = ev.type()
        if t in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease) and isinstance(obj, QWindow):
            name = _key_name(ev)
            if name:
                if t == QEvent.Type.KeyPress:
                    _KEYS_DOWN.add(name)
                    _fire("key", name)
                elif not ev.isAutoRepeat():
                    _KEYS_DOWN.discard(name)
        elif t == QEvent.Type.MouseButtonRelease and obj in _CLICKABLE:
            _fire("click", _CLICKABLE[obj])
        elif t == QEvent.Type.MouseButtonPress and _WIN is not None and obj is _WIN.content:
            _fire("mouse")
        elif t == QEvent.Type.Close and obj is not None and obj in (_WIN, _STATE["stage_window"]):
            QTimer.singleShot(0, _after_close)
        return False


def _after_close():
    if not _our_windows_open():
        _STOP.set()
        _APP.quit()


_FILTER = _Filter()


# ---------------------------------------------------------------- dialogs
def _parent():
    return _WIN if _WIN is not None and _WIN.isVisible() else None


def _box(icon, text, buttons=QMessageBox.StandardButton.Ok, title=None):
    m = QMessageBox(icon, str(title or _TITLE), str(text), buttons, _parent())
    if _parent() is None:
        m.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    return m.exec()


def _alert(text):
    with _released():
        _ui(lambda: _box(QMessageBox.Icon.Information, text))


def _big(title, text):
    def show():
        m = QMessageBox(_parent())
        m.setWindowTitle(str(title))
        m.setText(str(text))
        m.setStyleSheet("QLabel { font-size: 20pt; font-weight: 700; min-width: 320px; }")
        if _parent() is None:
            m.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        m.exec()
    with _released():
        _ui(show)


def _confirm(text):
    yes, no = QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No
    with _released():
        return _ui(lambda: _box(QMessageBox.Icon.Question, text, yes | no)) == yes


def _ask_text(text):
    def ask():
        d = QInputDialog(_parent())
        d.setWindowTitle(_TITLE)
        d.setLabelText(str(text))
        if _parent() is None:
            d.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        return d.textValue() if d.exec() else ""
    with _released():
        ans = _ui(ask)
    _STATE["answer"] = ans
    return ans


def _ask_number(text):
    def ask():
        d = QInputDialog(_parent())
        d.setWindowTitle(_TITLE)
        d.setLabelText(str(text))
        d.setInputMode(QInputDialog.InputMode.DoubleInput)
        d.setDoubleRange(-1e12, 1e12)
        d.setDoubleDecimals(3)
        if _parent() is None:
            d.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        return d.doubleValue() if d.exec() else 0
    with _released():
        ans = _num(_ui(ask))
    _STATE["answer"] = ans
    return ans


def _answer():
    return _STATE.get("answer", "")


def _clip(text):
    _ui(lambda: QApplication.clipboard().setText(str(text)))


def _color(c):
    if c == "random":
        return "#%06x" % random.randint(0, 0xFFFFFF)
    return c


# ---------------------------------------------------------------- widgets
def _w(name):
    w = getattr(_WIN, str(name), None)
    if w is None:
        raise RuntimeError(f"'{name}' 위젯이 없어요. GUI 디자이너에서 만들어 주세요.")
    return w


def _set_text(name, value):
    def f():
        w, v = _w(name), str(value)
        if hasattr(w, "setPlainText"):
            w.setPlainText(v)
        elif isinstance(w, QComboBox):
            i = w.findText(v)
            if i < 0:
                w.addItem(v)
                i = w.count() - 1
            w.setCurrentIndex(i)
        elif hasattr(w, "setText"):
            w.setText(v)
        elif hasattr(w, "setValue"):
            w.setValue(int(_num(v)))
    _ui(f)


def _get_text(name):
    def f():
        w = _w(name)
        if hasattr(w, "toPlainText"):
            return w.toPlainText()
        if isinstance(w, QComboBox):
            return w.currentText()
        if isinstance(w, QListWidget):
            it = w.currentItem()
            return it.text() if it else ""
        if hasattr(w, "text") and callable(w.text):
            return w.text()
        if hasattr(w, "value"):
            return str(w.value())
        return ""
    return _ui(f)


def _set_value(name, value):
    def f():
        w = _w(name)
        if hasattr(w, "setChecked") and not hasattr(w, "setValue"):
            w.setChecked(bool(value) and value not in ("0", "false", "False"))
        elif isinstance(w, QComboBox):
            w.setCurrentIndex(int(_num(value)))
        elif isinstance(w, QListWidget):
            w.setCurrentRow(int(_num(value)))
        elif hasattr(w, "setValue"):
            w.setValue(int(round(float(_num(value)))))
        else:
            _set_text(name, value)
    _ui(f)


def _get_value(name):
    def f():
        w = _w(name)
        if hasattr(w, "isChecked") and not hasattr(w, "value"):
            return w.isChecked()
        if isinstance(w, QComboBox):
            return w.currentIndex()
        if isinstance(w, QListWidget):
            return w.currentRow()
        if hasattr(w, "value"):
            return w.value()
        return _num(_get_text(name))
    return _ui(f)


def _set_visible(name, mode):
    def f():
        w = _w(name)
        {"show": w.show, "hide": w.hide, "enable": lambda: w.setEnabled(True),
         "disable": lambda: w.setEnabled(False)}[mode]()
    _ui(f)


def _set_color(name, which, color):
    def f():
        w = _w(name)
        over = getattr(w, "_esd_over", None)
        if over is None:
            over = {}
            w._esd_over = over
            w._esd_base = w.styleSheet()
        over[which] = _color(color)
        cls = type(w).__name__
        rules = "; ".join(f"{k}: {v}" for k, v in over.items())
        w.setStyleSheet(f"{w._esd_base} {cls} {{ {rules}; }}")
    _ui(f)


def _move(name, x, y):
    _ui(lambda: _w(name).move(int(_num(x)), int(_num(y))))


def _list_add(name, value):
    _ui(lambda: _w(name).addItem(str(value)))


def _list_clear(name):
    _ui(lambda: _w(name).clear())


def _set_title(text):
    def f():
        _WIN.setWindowTitle(str(text))
        _WIN.titlebar.set_title(str(text))
    _ui(f)


# ---------------------------------------------------------------- turtle stage
_SPEED_DELAY = {0: 0.0, 10: 0.004, 6: 0.012, 1: 0.05}


class _Sprite:
    """An object on the stage: an emoji/text shape or a picture, in turtle coordinates (0,0 = centre)."""

    def __init__(self, name, shape):
        self.name = name
        self.shape = str(shape)
        self.pix = None
        self.x = self.y = 0.0
        self.heading = 0.0
        self.size = 100.0
        self.visible = True
        self.say = ""

    def box(self):
        if self.pix is not None:
            w, h = self.pix.width(), self.pix.height()
            k = 120.0 / max(w, h, 1) if max(w, h) > 120 else 1.0
            w, h = w * k, h * k
        else:
            w = h = 56.0
        return w * self.size / 100.0, h * self.size / 100.0

    def hit(self, x, y):
        w, h = self.box()
        return self.visible and abs(x - self.x) <= w / 2 and abs(y - self.y) <= h / 2


class _Stage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = []
        self.sprites = {}
        self.bg = QColor("white")
        self.reset_turtle()
        self.delay = _SPEED_DELAY[6]
        self.turtle_used = False

    def to_stage(self, pos):
        return pos.x() - self.width() / 2, self.height() / 2 - pos.y()

    def mousePressEvent(self, e):
        x, y = self.to_stage(e.position())
        for sp in reversed(list(self.sprites.values())):
            if sp.hit(x, y):
                _fire("sprite_click", sp.name)
                break
        _fire("mouse")

    def _draw_sprites(self, p):
        for sp in self.sprites.values():
            if not sp.visible:
                continue
            w, h = sp.box()
            p.save()
            p.translate(self.pt(sp.x, sp.y))
            p.rotate(-sp.heading)
            if sp.pix is not None:
                p.drawPixmap(QRectF(-w / 2, -h / 2, w, h).toRect(), sp.pix)
            else:
                f = QFont(["Segoe UI Emoji", "Malgun Gothic"])
                f.setPixelSize(max(4, int(44 * sp.size / 100)))
                p.setFont(f)
                p.setPen(QColor("#222222"))
                p.drawText(QRectF(-w / 2, -h / 2, w, h), Qt.AlignmentFlag.AlignCenter, sp.shape)
            p.restore()
            if sp.say:
                f = QFont("Malgun Gothic", 11, QFont.Weight.Bold)
                p.setFont(f)
                tw = p.fontMetrics().horizontalAdvance(sp.say) + 20
                th = p.fontMetrics().height() + 12
                c = self.pt(sp.x, sp.y)
                r = QRectF(c.x() - tw / 2, c.y() - h / 2 - th - 10, tw, th)
                p.setPen(QPen(QColor("#555555"), 1.2))
                p.setBrush(QColor("#ffffff"))
                p.drawRoundedRect(r, 10, 10)
                p.drawPolygon(QPolygonF([QPointF(c.x() - 6, r.bottom()), QPointF(c.x() + 6, r.bottom()),
                                         QPointF(c.x(), r.bottom() + 8)]))
                p.setPen(QColor("#222222"))
                p.drawText(r, Qt.AlignmentFlag.AlignCenter, sp.say)

    def reset_turtle(self):
        self.x = self.y = 0.0
        self.heading = 0.0
        self.pen = True
        self.color = QColor("black")
        self.pen_width = 2
        self.visible = True
        self.fill = None

    def pt(self, x, y):
        return QPointF(self.width() / 2 + x, self.height() / 2 - y)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), self.bg)
        for it in self.items:
            if it[0] == "line":
                _, x1, y1, x2, y2, col, w = it
                p.setPen(QPen(col, w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                p.drawLine(self.pt(x1, y1), self.pt(x2, y2))
            elif it[0] == "poly":
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(it[2])
                p.drawPolygon(QPolygonF([self.pt(x, y) for x, y in it[1]]))
            elif it[0] == "text":
                _, x, y, text, col = it
                p.setPen(col)
                p.setFont(QFont("Malgun Gothic", 16, QFont.Weight.Bold))
                p.drawText(self.pt(x, y), text)
        self._draw_sprites(p)
        if self.visible and self.turtle_used:
            self._draw_turtle(p)
        p.end()

    def _draw_turtle(self, p):
        """A real little turtle (shell in the pen colour), facing the current heading."""
        p.save()
        p.translate(self.pt(self.x, self.y))
        p.rotate(-self.heading)  # turtle angles go counter-clockwise, screen rotation goes clockwise
        p.scale(1.4, 1.4)
        skin, outline = QColor("#5fa85a"), QColor("#2f5e2c")
        p.setPen(QPen(outline, 1.2))
        p.setBrush(skin)
        for lx, ly in ((7, 9), (7, -9), (-7, 9), (-7, -9)):  # legs
            p.drawEllipse(QPointF(lx, ly), 4.2, 3.4)
        p.drawPolygon(QPolygonF([QPointF(-11, -2.5), QPointF(-17, 0), QPointF(-11, 2.5)]))  # tail
        p.drawEllipse(QPointF(15, 0), 5.5, 4.6)  # head
        p.setBrush(QColor("#111111"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(17.5, 2.0), 1.1, 1.1)  # eyes
        p.drawEllipse(QPointF(17.5, -2.0), 1.1, 1.1)
        shell = QColor(self.color)
        if shell.lightness() > 235:  # keep a white pen's turtle visible on a white stage
            shell = QColor("#d9d9d9")
        p.setPen(QPen(shell.darker(160), 1.6))
        p.setBrush(shell)
        p.drawEllipse(QPointF(0, 0), 12, 10)  # shell
        p.setPen(QPen(shell.darker(135), 1.1))
        p.drawEllipse(QPointF(0, 0), 5, 4.2)  # shell pattern
        for ang in range(0, 360, 60):
            r = math.radians(ang)
            p.drawLine(QPointF(5 * math.cos(r), 4.2 * math.sin(r)), QPointF(11 * math.cos(r), 9 * math.sin(r)))
        p.restore()

    def step_to(self, x, y):
        if self.pen:
            self.items.append(("line", self.x, self.y, x, y, QColor(self.color), self.pen_width))
        self.x, self.y = x, y
        if self.fill is not None:
            self.fill[1].append((x, y))
        self.update()


def _stage():
    if _STATE["stage"] is not None:
        return _STATE["stage"]

    def make():
        if _STATE["stage"] is not None:
            return _STATE["stage"]
        host = None
        for name, kind in DESIGN_ITEMS:
            if kind == "stage":
                host = getattr(_WIN, name, None)
                break
        if host is None and not _STATE["has_design"]:
            host = _WIN.content
            _WIN.resize(max(_WIN.width(), 600), max(_WIN.height(), 600 + _WIN.titlebar.height()))
        if host is not None:
            st = _Stage(host)
            lay = QVBoxLayout(host)
            lay.setContentsMargins(1, 1, 1, 1)
            lay.addWidget(st)
            if not _WIN.isVisible():
                _WIN.show()
        else:
            win = QWidget()
            win.setWindowTitle(f"{_TITLE} — 무대")
            win.resize(560, 560)
            lay = QVBoxLayout(win)
            lay.setContentsMargins(0, 0, 0, 0)
            st = _Stage(win)
            lay.addWidget(st)
            _STATE["stage_window"] = win
            win.show()
            win.activateWindow()
        _STATE["stage"] = st
        return st
    return _ui(make)


def _tstage():
    """The stage, remembering that turtle blocks are in use (the turtle is only drawn once they are)."""
    st = _stage()
    if not st.turtle_used:
        st.turtle_used = True
        _ui(st.update)
    return st


class _Turtle:
    def _go(self, dist):
        st = _tstage()
        a = math.radians(st.heading)
        tx, ty = st.x + dist * math.cos(a), st.y + dist * math.sin(a)
        n = max(1, int(abs(dist) / 6)) if st.delay else 1
        sx, sy = st.x, st.y
        for i in range(1, n + 1):
            k = i / n
            _ui(lambda k=k: st.step_to(sx + (tx - sx) * k, sy + (ty - sy) * k))
            if st.delay:
                _wait(st.delay)
            else:
                _tick()

    def forward(self, d):
        self._go(float(_num(d)))

    def back(self, d):
        self._go(-float(_num(d)))

    def _turn(self, deg):
        st = _tstage()

        def f():
            st.heading = (st.heading + deg) % 360
            st.update()
        _ui(f)
        if st.delay:
            _wait(st.delay)

    def left(self, deg):
        self._turn(float(_num(deg)))

    def right(self, deg):
        self._turn(-float(_num(deg)))

    def goto(self, x, y):
        st = _tstage()
        _ui(lambda: st.step_to(float(_num(x)), float(_num(y))))

    def circle(self, r):
        r = float(_num(r))
        seg = 2 * math.pi * abs(r) / 36
        for _ in range(36):
            self._go(seg)
            self._turn(10 if r >= 0 else -10)

    def _set(self, **kw):
        st = _tstage()

        def f():
            for k, v in kw.items():
                setattr(st, k, v)
            st.update()
        _ui(f)

    def color(self, c):
        self._set(color=QColor(_color(c)))

    def bgcolor(self, c):
        self._set(bg=QColor(_color(c)))

    def width(self, w):
        self._set(pen_width=max(1, float(_num(w))))

    def penup(self):
        self._set(pen=False)

    def pendown(self):
        self._set(pen=True)

    def speed(self, s):
        self._set(delay=_SPEED_DELAY.get(int(s), 0.012))

    def hideturtle(self):
        self._set(visible=False)

    def showturtle(self):
        self._set(visible=True)

    def begin_fill(self):
        st = _tstage()
        _ui(lambda: setattr(st, "fill", (len(st.items), [(st.x, st.y)])))

    def end_fill(self):
        st = _tstage()

        def f():
            if st.fill is not None and len(st.fill[1]) > 2:
                st.items.insert(st.fill[0], ("poly", list(st.fill[1]), QColor(st.color)))
            st.fill = None
            st.update()
        _ui(f)

    def write(self, text):
        st = _tstage()

        def f():
            st.items.append(("text", st.x, st.y, str(text), QColor(st.color)))
            st.update()
        _ui(f)

    def home(self):
        self.goto(0, 0)
        self._set(heading=0.0)

    def clear(self):
        self._set(items=[])

    def pos(self, axis):
        st = _tstage()
        return round(st.x if axis == "x" else st.y, 2)


_T = _Turtle()


# ---------------------------------------------------------------- objects (sprites)
def _spr(name):
    sp = _stage().sprites.get(str(name))
    if sp is None:
        raise RuntimeError(f"'{name}' 오브젝트가 없어요. 먼저 '오브젝트 만들기' 블록을 실행하세요.")
    return sp


def _spr_do(name, fn):
    st = _stage()

    def f():
        fn(_spr(name), st)
        st.update()
    _ui(f)


def _spr_new(name, shape):
    st = _stage()

    def f():
        st.sprites[str(name)] = _Sprite(str(name), shape)
        st.update()
    _ui(f)


def _spr_image(name, path):
    p = os.path.abspath(str(path))

    def f(sp, st):
        pix = QPixmap(p)
        if pix.isNull():
            raise RuntimeError(f"그림 파일을 열 수 없어요: {path}")
        sp.pix = pix
    _spr_do(name, f)


def _spr_goto(name, x, y):
    _spr_do(name, lambda sp, st: (setattr(sp, "x", float(_num(x))), setattr(sp, "y", float(_num(y)))))


def _spr_move(name, dist):
    def f(sp, st):
        a = math.radians(sp.heading)
        sp.x += float(_num(dist)) * math.cos(a)
        sp.y += float(_num(dist)) * math.sin(a)
    _spr_do(name, f)


def _spr_change(name, axis, delta):
    _spr_do(name, lambda sp, st: setattr(sp, axis, getattr(sp, axis) + float(_num(delta))))


def _spr_set(name, prop, value):
    _spr_do(name, lambda sp, st: setattr(sp, prop, float(_num(value)) % 360 if prop == "heading"
                                         else max(1.0, float(_num(value))) if prop == "size" else float(_num(value))))


def _spr_turn(name, deg):
    _spr_do(name, lambda sp, st: setattr(sp, "heading", (sp.heading + float(_num(deg))) % 360))


def _spr_show(name, on):
    _spr_do(name, lambda sp, st: setattr(sp, "visible", bool(on)))


def _spr_front(name):
    def f(sp, st):
        st.sprites.pop(sp.name)
        st.sprites[sp.name] = sp
    _spr_do(name, f)


def _spr_say(name, text, secs=0):
    _spr_do(name, lambda sp, st: setattr(sp, "say", str(text)))
    if float(_num(secs)) > 0:
        _wait(secs)
        _spr_do(name, lambda sp, st: setattr(sp, "say", ""))


def _spr_get(name, prop):
    v = _ui(lambda: getattr(_spr(name), prop))
    return round(v, 2) if isinstance(v, float) else v


def _spr_touch(name, target):
    st = _stage()

    def f():
        sp = _spr(name)
        if not sp.visible:
            return False
        w, h = sp.box()
        if target == "__wall__":
            return abs(sp.x) + w / 2 >= st.width() / 2 or abs(sp.y) + h / 2 >= st.height() / 2
        if target == "__mouse__":
            pos = st.mapFromGlobal(QCursor.pos())
            return sp.hit(*st.to_stage(QPointF(pos)))
        other = st.sprites.get(str(target))
        if other is None or other is sp or not other.visible:
            return False
        ow, oh = other.box()
        return abs(sp.x - other.x) * 2 < w + ow and abs(sp.y - other.y) * 2 < h + oh
    return _ui(f)


def _spr_bounce(name):
    def f(sp, st):
        w, h = sp.box()
        hw, hh = st.width() / 2, st.height() / 2
        if abs(sp.x) + w / 2 > hw:
            sp.heading = (180 - sp.heading) % 360
            sp.x = math.copysign(hw - w / 2, sp.x)
        if abs(sp.y) + h / 2 > hh:
            sp.heading = (-sp.heading) % 360
            sp.y = math.copysign(hh - h / 2, sp.y)
    _spr_do(name, f)


# ---------------------------------------------------------------- mouse
def _mouse(kind):
    def f():
        if kind == "down":
            return QApplication.mouseButtons() != Qt.MouseButton.NoButton
        st = _STATE["stage"]
        host = st if st is not None else (_WIN.content if _WIN is not None else None)
        if host is None:
            return 0
        pos = host.mapFromGlobal(QCursor.pos())
        if st is not None:
            x, y = st.to_stage(QPointF(pos))
        else:
            x, y = pos.x(), pos.y()
        return round(x if kind == "x" else y)
    return _ui(f)


# ---------------------------------------------------------------- variables on screen
_WATCH = {}


def _watch(label, getter):
    def f():
        if label in _WATCH:
            _WATCH[label][0] = getter
            return
        host = _STATE["stage"] or _WIN.content
        if host is _WIN.content and not _WIN.isVisible():
            _WIN.show()
        lb = QLabel(host)
        lb.setStyleSheet("QLabel { background: rgba(30,31,43,215); color: #ffffff; border-radius: 8px; "
                         "padding: 4px 10px; font: bold 11pt 'Malgun Gothic'; }")
        lb.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lb.show()
        _WATCH[label] = [getter, lb]
        if "timer" not in _STATE:
            t = QTimer(_BRIDGE)
            t.setInterval(100)
            t.timeout.connect(_watch_tick)
            t.start()
            _STATE["timer"] = t
        _watch_tick()
    _ui(f)


def _unwatch(label):
    def f():
        item = _WATCH.pop(label, None)
        if item:
            item[1].deleteLater()
        _watch_tick()
    _ui(f)


def _watch_tick():
    st = _STATE["stage"]
    for i, (label, (getter, lb)) in enumerate(_WATCH.items()):
        if st is not None and lb.parent() is not st:
            lb.setParent(st)
            lb.show()
        try:
            v = getter()
            v = int(v) if isinstance(v, float) and v.is_integer() else v
        except Exception:
            v = "?"
        lb.setText(f"{label}: {v}")
        lb.adjustSize()
        lb.move(8, 8 + i * (lb.height() + 6))
        lb.raise_()


# ---------------------------------------------------------------- sound
_SND = {"n": 0, "vol": 1000, "open": []}


def _mci(cmd):
    import ctypes
    buf = ctypes.create_unicode_buffer(256)
    err = ctypes.windll.winmm.mciSendStringW(cmd, buf, 255, None)
    return err, buf.value


def _snd_play(path, wait=False):
    p = os.path.abspath(str(path))
    if not os.path.isfile(p):
        raise RuntimeError(f"소리 파일이 없어요: {path}")

    def start():
        _SND["n"] += 1
        alias = f"esd{_SND['n']}"
        err, _ = _mci(f'open "{p}" type mpegvideo alias {alias}')
        if err:
            raise RuntimeError(f"소리 파일을 열 수 없어요: {path}")
        _mci(f"setaudio {alias} volume to {_SND['vol']}")
        _mci(f"play {alias}")
        _SND["open"].append(alias)
        return alias
    alias = _ui(start)
    if wait:
        while _ui(lambda: _mci(f"status {alias} mode")[1]) == "playing":
            _wait(0.05)
        _ui(lambda: _snd_close(alias))


def _snd_close(alias):
    _mci(f"close {alias}")
    if alias in _SND["open"]:
        _SND["open"].remove(alias)


def _snd_stop():
    _ui(lambda: [_snd_close(a) for a in list(_SND["open"])])


def _snd_volume(pct):
    def f():
        _SND["vol"] = max(0, min(1000, int(float(_num(pct)) * 10)))
        for a in _SND["open"]:
            _mci(f"setaudio {a} volume to {_SND['vol']}")
    _ui(f)


def _snd_sys(kind):
    import winsound
    winsound.MessageBeep({"ok": 0, "info": 0x40, "warn": 0x30, "error": 0x10, "question": 0x20}.get(kind, 0))


def _tone(hz, secs):
    import winsound
    with _released():
        winsound.Beep(max(37, min(32767, int(float(_num(hz))))), max(1, int(float(_num(secs)) * 1000)))


_SPEAK_PS = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
             "try { $v = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -eq 'ko-KR' } | "
             "Select-Object -First 1; if ($v) { $s.SelectVoice($v.VoiceInfo.Name) } } catch {}; "
             "$s.Volume = [int]$env:ESD_SAY_VOLUME; $s.Speak($env:ESD_SAY)")


def _speak(text):
    """Reads text aloud with the Windows voice (Korean if installed). The text goes in through an environment
    variable, never into the PowerShell command itself."""
    env = dict(os.environ, ESD_SAY=str(text), ESD_SAY_VOLUME=str(max(0, min(100, _SND["vol"] // 10))))
    with _released():
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _SPEAK_PS], env=env,
                       creationflags=0x08000000, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)


# ---------------------------------------------------------------- internet
def _net_get(url, timeout=15, agent="Mozilla/5.0 (EXE Studio program)"):
    import urllib.request
    url = str(url).strip()
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    req = urllib.request.Request(url, headers={"User-Agent": agent, "Accept-Language": "ko"})
    with _released():
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read(5 * 1024 * 1024)
            enc = r.headers.get_content_charset() or "utf-8"
    return data.decode(enc, "replace")


def _net_text(url):
    """Web page as plain text (tags removed)."""
    import html
    import re as _re
    raw = _net_get(url)
    raw = _re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
    text = html.unescape(_re.sub(r"(?s)<[^>]+>", " ", raw))
    return _re.sub(r"\s+", " ", text).strip()


_WEATHER_KO = [("thunder", "천둥번개"), ("blizzard", "눈보라"), ("heavy snow", "폭설"), ("snow", "눈"),
               ("sleet", "진눈깨비"), ("freezing", "어는 비"), ("heavy rain", "폭우"), ("torrential", "폭우"),
               ("drizzle", "이슬비"), ("shower", "소나기"), ("rain", "비"), ("fog", "안개"), ("mist", "옅은 안개"),
               ("haze", "실안개"), ("overcast", "흐림"), ("partly cloudy", "구름 조금"), ("cloudy", "구름 많음"),
               ("sunny", "맑음"), ("clear", "맑음")]


def _weather(city):
    import urllib.parse
    try:
        # wttr.in answers browsers with an HTML page and command-line tools with plain text
        text = _net_get(f"https://wttr.in/{urllib.parse.quote(str(city))}?format=%t+%C",
                        agent="curl/8.0").strip()
    except Exception:
        return "날씨를 가져올 수 없어요"
    temp, _, cond = text.partition(" ")
    low = cond.lower()
    for en, ko in _WEATHER_KO:
        if en in low:
            return f"{temp} {ko}"
    return text


def _online():
    try:
        _net_get("https://www.google.com/generate_204", timeout=5)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- saved data (survives restarts)
def _data_file():
    safe = "".join(ch for ch in _TITLE if ch.isalnum() or ch in "-_ ").strip() or "BlockProgram"
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "ExeStudioPrograms", safe, "data.json")


_DATA_LOCK = threading.Lock()


def _data_all():
    import json
    try:
        with open(_data_file(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _data_save(key, value):
    import json
    with _DATA_LOCK:
        d = _data_all()
        d[str(key)] = value if isinstance(value, (int, float, str, bool, list)) else str(value)
        path = _data_file()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        os.replace(path + ".tmp", path)


def _data_load(key, default=0):
    with _DATA_LOCK:
        return _data_all().get(str(key), default)


def _data_delete(key):
    import json
    with _DATA_LOCK:
        d = _data_all()
        d.pop(str(key), None)
        path = _data_file()
        if os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False)


# ---------------------------------------------------------------- timer
_TIMER = {"start": time.monotonic(), "paused": None}


def _timer(action="value"):
    now = time.monotonic()
    if action == "reset":
        _TIMER["start"], _TIMER["paused"] = now, None
    elif action == "stop" and _TIMER["paused"] is None:
        _TIMER["paused"] = now
    elif action == "start" and _TIMER["paused"] is not None:
        _TIMER["start"] += now - _TIMER["paused"]
        _TIMER["paused"] = None
    end = _TIMER["paused"] if _TIMER["paused"] is not None else now
    return round(end - _TIMER["start"], 1)


# ---------------------------------------------------------------- download with virus check (never runs the file)
try:
    import serial as _serial
    import serial.tools.list_ports as _list_ports
except ImportError:
    _serial = _list_ports = None
try:
    import psutil as _psutil
except ImportError:
    _psutil = None

_SCAN_HOME = os.path.join(os.environ.get("LOCALAPPDATA", ""), "ExeStudio")
_SCAN_EXCLUDE = [r"(?i)(webshell|chopper).*generic", r"(?i)generic.*(webshell|chopper)", r"(?i)^WEBSHELL_.*Generic"]
_YARA = {}


def _yara_rules():
    if "rules" not in _YARA:
        import yara
        folder = os.path.join(_SCAN_HOME, "yara")
        files = {os.path.splitext(n)[0]: os.path.join(folder, n) for n in os.listdir(folder)
                 if n.lower().endswith((".yar", ".yara"))}
        ext = {k: "" for k in ("filename", "filepath", "extension", "filetype", "md5", "owner")}
        _YARA["ext"] = ext
        _YARA["rules"] = yara.compile(filepaths=files, externals=ext)
    return _YARA["rules"]


def _download_checked(url, save_path, sha256=""):
    """Downloads an https file, checks it with ClamAV then YARA, and saves it only if both pass. Never runs it."""
    import hashlib
    import re
    import shutil
    import subprocess
    import tempfile
    import urllib.request
    url = str(url).strip()
    if not url.lower().startswith("https://"):
        raise RuntimeError("보안을 위해 https:// 주소만 내려받을 수 있어요.")
    work = tempfile.mkdtemp(prefix="esd_dl_")
    tmp = os.path.join(work, "download.bin")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "EXE-Studio-download"})
        with _released():
            with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
                total = 0
                while True:
                    chunk = r.read(1 << 16)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > 2 * 1024 ** 3:
                        raise RuntimeError("파일이 2GB보다 커서 중지했어요.")
                    f.write(chunk)
        digest = hashlib.sha256(open(tmp, "rb").read()).hexdigest()
        if str(sha256).strip() and digest != str(sha256).strip().lower():
            raise RuntimeError("해시가 달라요. 받은 파일을 저장하지 않았어요.")
        clam = os.path.join(_SCAN_HOME, "clamav-bin", "ClamAV", "clamscan.exe")
        if not os.path.exists(clam):
            raise RuntimeError("ClamAV가 없어서 검사할 수 없어요. 파일은 저장하지 않았어요.")
        proc = subprocess.run([clam, "--no-summary", f"--database={os.path.join(_SCAN_HOME, 'clamav')}", tmp],
                              capture_output=True, text=True, creationflags=0x08000000)
        if proc.returncode == 1:
            raise RuntimeError("ClamAV 탐지: " + (proc.stdout.strip() or "위협") + " — 저장하지 않았어요.")
        if proc.returncode != 0:
            raise RuntimeError("ClamAV 검사 오류 — 저장하지 않았어요.")
        hits = [m.rule for m in _yara_rules().match(tmp, externals=_YARA["ext"])]
        hits = [h for h in hits if not any(re.search(x, h) for x in _SCAN_EXCLUDE)]
        if hits:
            raise RuntimeError("YARA 탐지: " + ", ".join(hits[:5]) + " — 저장하지 않았어요.")
        os.makedirs(os.path.dirname(os.path.abspath(str(save_path))) or ".", exist_ok=True)
        shutil.copyfile(tmp, str(save_path))
        return os.path.abspath(str(save_path))
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ---------------------------------------------------------------- rule update and file scan
_RULES_URL = "https://github.com/Neo23x0/signature-base/archive/refs/heads/master.zip"
_SCAN_LAST = {"msg": ""}


def _clam_bin(name):
    return os.path.join(_SCAN_HOME, "clamav-bin", "ClamAV", name)


def _rules_update(which="both"):
    """Updates YARA rules (signature-base, checked before use) and/or the ClamAV database."""
    import shutil
    import subprocess
    import tempfile
    import urllib.request
    import zipfile
    done = []
    if which in ("yara", "both"):
        work = tempfile.mkdtemp(prefix="esd_rules_")
        try:
            zp = os.path.join(work, "rules.zip")
            with _released():
                urllib.request.urlretrieve(_RULES_URL, zp)  # fixed https address
            staged = os.path.join(work, "yara")
            os.makedirs(staged)
            with zipfile.ZipFile(zp) as z:
                for n in z.namelist():
                    if "/yara/" in n and n.lower().endswith((".yar", ".yara")) and not n.endswith("/"):
                        with z.open(n) as src, open(os.path.join(staged, os.path.basename(n)), "wb") as dst:
                            shutil.copyfileobj(src, dst)
            import yara
            files = {os.path.splitext(f)[0]: os.path.join(staged, f) for f in os.listdir(staged)}
            ext = {k: "" for k in ("filename", "filepath", "extension", "filetype", "md5", "owner")}
            yara.compile(filepaths=files, externals=ext)  # refuse a rule set that does not compile
            target = os.path.join(_SCAN_HOME, "yara")
            if os.path.exists(target):
                shutil.rmtree(target)
            shutil.copytree(staged, target)
            _YARA.clear()
            done.append(f"YARA 규칙 {len(files)}개")
        finally:
            shutil.rmtree(work, ignore_errors=True)
    if which in ("clamav", "both"):
        fresh = _clam_bin("freshclam.exe")
        if not os.path.exists(fresh):
            raise RuntimeError("ClamAV가 없어요. ExeStudio를 한 번 실행해 주세요.")
        db = os.path.join(_SCAN_HOME, "clamav")
        os.makedirs(db, exist_ok=True)
        conf = os.path.join(db, "freshclam.conf")
        with open(conf, "w", encoding="ascii") as f:
            f.write("DatabaseDirectory " + db + chr(10) + "DatabaseMirror database.clamav.net" + chr(10))
        with _released():
            p = subprocess.run([fresh, "--config-file=" + conf], capture_output=True, text=True,
                               creationflags=0x08000000, timeout=1800)
        if p.returncode not in (0, 1):
            raise RuntimeError("ClamAV DB 업데이트 실패")
        done.append("ClamAV 바이러스 DB")
    return ", ".join(done) + " 업데이트 완료"


def _scan_file(path, engine="both"):
    """True when the file is clean. The reason is kept for the '마지막 검사 결과' block."""
    import subprocess
    import re
    path = str(path)
    if not os.path.isfile(path):
        raise RuntimeError("검사할 파일이 없어요: " + path)
    reasons = []
    if engine in ("clamav", "both"):
        clam = _clam_bin("clamscan.exe")
        if not os.path.exists(clam):
            raise RuntimeError("ClamAV가 없어요. ExeStudio를 한 번 실행해 주세요.")
        with _released():
            p = subprocess.run([clam, "--no-summary", "--database=" + os.path.join(_SCAN_HOME, "clamav"), path],
                               capture_output=True, text=True, creationflags=0x08000000, timeout=600)
        if p.returncode == 1:
            reasons.append("ClamAV 탐지: " + (p.stdout.strip() or "위협"))
        elif p.returncode != 0:
            raise RuntimeError("ClamAV 검사 오류")
    if engine in ("yara", "both"):
        hits = [m.rule for m in _yara_rules().match(path, externals=_YARA["ext"])]
        hits = [h for h in hits if not any(re.search(x, h) for x in _SCAN_EXCLUDE)]
        if hits:
            reasons.append("YARA 탐지: " + ", ".join(hits[:5]))
    _SCAN_LAST["msg"] = " / ".join(reasons) if reasons else "깨끗함"
    return not reasons


def _scan_last():
    return _SCAN_LAST["msg"]


# ---------------------------------------------------------------- USB and serial
def _port_list():
    if _list_ports is None:
        return []
    return sorted(p.device for p in _list_ports.comports())


def _usb_watch():
    last = set(_port_list())
    while not _STOP.is_set():
        time.sleep(1.0)
        now = set(_port_list())
        for dev in sorted(now - last):
            _STATE["usb_last"] = dev
            _fire("usb_in", dev)
        for dev in sorted(last - now):
            _STATE["usb_last"] = dev
            _fire("usb_out", dev)
        last = now


_SERIAL = {}


def _serial_open(port, baud=9600):
    if _serial is None:
        raise RuntimeError("시리얼 기능(pyserial)을 쓸 수 없어요.")
    port = str(port).strip()
    if port in _SERIAL:
        return
    try:
        ser = _serial.Serial(port, int(_num(baud)), timeout=0.2)
    except (_serial.SerialException, OSError) as e:
        raise RuntimeError(f"{port} 포트를 열 수 없어요. 장치가 연결돼 있는지 확인하세요. ({e})")
    _SERIAL[port] = {"ser": ser, "last": ""}
    threading.Thread(target=_serial_reader, args=(port,), daemon=True).start()


def _serial_reader(port):
    info = _SERIAL[port]
    ser, buf = info["ser"], b""
    while not _STOP.is_set():
        try:
            data = ser.read(256)
        except (_serial.SerialException, OSError):
            break
        if not data:
            continue
        buf += data
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            info["last"] = line.decode("utf-8", "replace").strip()
            _fire("serial", port)


def _serial_send(port, text):
    info = _SERIAL.get(str(port).strip())
    if not info:
        raise RuntimeError(f"{port} 포트가 열려 있지 않아요. 먼저 '포트 열기' 블록을 실행하세요.")
    info["ser"].write((str(text) + "\n").encode("utf-8"))


def _serial_last(port):
    info = _SERIAL.get(str(port).strip())
    return info["last"] if info else ""


def _battery():
    """Battery percentage, or -1 when this PC has no battery (desktops)."""
    if _psutil is None:
        return -1
    info = _psutil.sensors_battery()
    return -1 if info is None else round(info.percent)


def _battery_charging():
    if _psutil is None:
        return False
    info = _psutil.sensors_battery()
    return bool(info and info.power_plugged)


# ---------------------------------------------------------------- running-block highlight (EXE Studio only)
_TRACE = {"on": bool(os.environ.get("ESD_TRACE")), "last": 0.0, "cur": None}


def _hl(block_id):
    if not _TRACE["on"]:
        return
    _TRACE["cur"] = block_id
    now = time.monotonic()
    if now - _TRACE["last"] > 0.04:
        _TRACE["last"] = now
        try:
            print("\x1eHL:" + str(block_id), flush=True)
        except Exception:
            pass


# ---------------------------------------------------------------- start
def _esd_main(window_cls, has_design, title):
    global _WIN, _TITLE
    _TITLE = title
    _STATE["has_design"] = bool(has_design)
    _WIN = window_cls()
    _APP.installEventFilter(_FILTER)
    signals = {"input": "textChanged", "textbox": "textChanged", "slider": "valueChanged",
               "spin": "valueChanged", "checkbox": "toggled", "radio": "toggled", "combo": "currentIndexChanged",
               "list": "currentRowChanged", "progress": "valueChanged"}
    for name, kind in DESIGN_ITEMS:
        w = getattr(_WIN, name, None)
        if w is None:
            continue
        if kind == "button":
            w.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            w.clicked.connect(lambda _=False, n=name: _fire("click", n))
        else:
            _CLICKABLE[w] = name
        if kind in signals:
            getattr(w, signals[kind]).connect(lambda *_, n=name: _fire("change", n))
    need_window = bool(has_design or _HANDLERS["key"] or _HANDLERS["click"] or _HANDLERS["change"]
                       or _HANDLERS["mouse"] or _HANDLERS["sprite_click"])
    _STATE["keep_alive"] = bool(need_window or _HANDLERS["every"] or _HANDLERS["usb_in"]
                                or _HANDLERS["usb_out"] or _HANDLERS["serial"])
    if _HANDLERS["usb_in"] or _HANDLERS["usb_out"]:
        threading.Thread(target=_usb_watch, daemon=True).start()
    if need_window:
        _WIN.show()
    for _, fn in _HANDLERS["start"]:
        _spawn(fn)
    for interval, fn in _HANDLERS["every"]:
        threading.Thread(target=_every_loop, args=(float(interval), fn), daemon=True).start()
    if not _HANDLERS["start"] and not _STATE["keep_alive"]:
        _WIN.show()
        _STATE["keep_alive"] = True
    code = _APP.exec()
    _STOP.set()
    sys.exit(code)
