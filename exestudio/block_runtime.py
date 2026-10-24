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

from PySide6.QtCore import QEvent, QObject, QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF, QWindow
from PySide6.QtWidgets import QComboBox, QInputDialog, QListWidget, QMessageBox

_APP = QApplication.instance() or QApplication(sys.argv)
_APP.setQuitOnLastWindowClosed(False)
_WIN = None
_TITLE = "프로그램"
_STOP = threading.Event()
_STATE = {"answer": "", "active": 0, "keep_alive": False, "stage": None, "stage_window": None, "errors": 0}
_COUNT_LOCK = threading.Lock()
_HANDLERS = {"start": [], "key": [], "click": [], "change": [], "every": [], "msg": []}
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
    end = time.time() + max(0.0, float(sec))
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
        if a == arg or (kind == "key" and a == "any"):
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


class _Stage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = []
        self.bg = QColor("white")
        self.reset_turtle()
        self.delay = _SPEED_DELAY[6]

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
        if self.visible:
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


class _Turtle:
    def _go(self, dist):
        st = _stage()
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
        st = _stage()

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
        st = _stage()
        _ui(lambda: st.step_to(float(_num(x)), float(_num(y))))

    def circle(self, r):
        r = float(_num(r))
        seg = 2 * math.pi * abs(r) / 36
        for _ in range(36):
            self._go(seg)
            self._turn(10 if r >= 0 else -10)

    def _set(self, **kw):
        st = _stage()

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
        st = _stage()
        _ui(lambda: setattr(st, "fill", (len(st.items), [(st.x, st.y)])))

    def end_fill(self):
        st = _stage()

        def f():
            if st.fill is not None and len(st.fill[1]) > 2:
                st.items.insert(st.fill[0], ("poly", list(st.fill[1]), QColor(st.color)))
            st.fill = None
            st.update()
        _ui(f)

    def write(self, text):
        st = _stage()

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
        st = _stage()
        return round(st.x if axis == "x" else st.y, 2)


_T = _Turtle()


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
    need_window = bool(has_design or _HANDLERS["key"] or _HANDLERS["click"] or _HANDLERS["change"])
    _STATE["keep_alive"] = bool(need_window or _HANDLERS["every"])
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
