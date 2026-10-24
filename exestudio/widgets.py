"""Shared widgets and helpers used by every page."""
import codecs
import os
import re
import subprocess
import sys
import traceback

from PySide6.QtCore import (QObject, QProcess, QProcessEnvironment, QRunnable, QThreadPool, QTimer, Qt,
                            Signal)
from PySide6.QtGui import QColor, QTextCursor
from PySide6.QtWidgets import (QApplication, QColorDialog, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QMenu, QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout,
                               QWidget)

from . import toolchain

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


# ---------------------------------------------------------------- small factories
def label(text, name=None, wrap=False):
    lb = QLabel(text)
    if name:
        lb.setObjectName(name)
    lb.setWordWrap(wrap)
    return lb


def button(text, slot=None, accent=False, danger=False, flat=False, tip=None):
    b = QPushButton(text)
    if accent:
        b.setProperty("accent", True)
    if danger:
        b.setProperty("danger", True)
    if flat:
        b.setProperty("flat", True)
    if tip:
        b.setToolTip(tip)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if slot:
        b.clicked.connect(slot)
    return b


def card(vertical=True, margins=16, spacing=10):
    f = QFrame()
    f.setObjectName("Card")
    lay = QVBoxLayout(f) if vertical else QHBoxLayout(f)
    lay.setContentsMargins(margins, margins, margins, margins)
    lay.setSpacing(spacing)
    return f, lay


def hrow(*widgets, spacing=8, stretch_end=False):
    lay = QHBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(0, 0, 0, 0)
    for w in widgets:
        if w is None:
            lay.addStretch(1)
        elif isinstance(w, int):
            lay.addSpacing(w)
        else:
            lay.addWidget(w)
    if stretch_end:
        lay.addStretch(1)
    return lay


def divider():
    f = QFrame()
    f.setObjectName("Divider")
    return f


def open_path(path):
    try:
        os.startfile(str(path))
    except Exception:
        subprocess.Popen(["explorer", str(path)])


def reveal(path):
    subprocess.Popen(["explorer", "/select,", os.path.normpath(str(path))])


def human_size(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} PB"


def folder_size(path):
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


# ---------------------------------------------------------------- background jobs
class _Signals(QObject):
    done = Signal(object)
    error = Signal(str)
    progress = Signal(object)


_alive = set()


class _Job(QRunnable):
    def __init__(self, fn, sig, with_progress):
        super().__init__()
        self.fn, self.sig, self.with_progress = fn, sig, with_progress

    def run(self):
        try:
            result = self.fn(self._progress) if self.with_progress else self.fn()
        except Exception as e:
            self._emit(self.sig.error, f"{e}\n\n{traceback.format_exc()}")
            return
        self._emit(self.sig.done, result)

    def _progress(self, value):
        self._emit(self.sig.progress, value)

    @staticmethod
    def _emit(signal, value):
        try:
            signal.emit(value)
        except RuntimeError:  # app is shutting down and the receiver is gone
            pass


def run_async(fn, on_done=None, on_error=None, on_progress=None):
    """Run fn() in a worker thread; callbacks fire on the GUI thread."""
    sig = _Signals()
    _alive.add(sig)
    if on_done:
        sig.done.connect(on_done)
    if on_error:
        sig.error.connect(on_error)
    if on_progress:
        sig.progress.connect(on_progress)
    sig.done.connect(lambda *_: _alive.discard(sig))
    sig.error.connect(lambda *_: _alive.discard(sig))
    QThreadPool.globalInstance().start(_Job(fn, sig, on_progress is not None))


# ---------------------------------------------------------------- processes
class ProcessRunner(QObject):
    """Runs a chain of commands one after another, streaming output. A step may also be a callable."""

    output = Signal(str)
    finished = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.proc = None
        self.queue = []
        self.running = False
        self._cancel = False
        self._decoder = None
        self.cwd = None
        self.python = None

    def run(self, steps, cwd=None, python=None):
        if self.running:
            self.output.emit("⚠ 이미 작업이 실행 중입니다. 끝난 뒤 다시 시도하세요.\n")
            return False
        self.queue = list(steps)
        self.cwd, self.python = cwd, python
        self.running, self._cancel = True, False
        self._next()
        return True

    def _next(self):
        if self._cancel:
            return
        if not self.queue:
            self.running = False
            self.finished.emit(0)
            return
        step = self.queue.pop(0)
        if callable(step):
            try:
                msg = step()
                if msg:
                    self.output.emit(str(msg) + "\n")
            except Exception as e:
                self.output.emit(f"✖ {e}\n")
                self._fail(-3)
                return
            QTimer.singleShot(0, self._next)
            return
        args = [str(a) for a in step]
        p = QProcess(self)
        p.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        env = QProcessEnvironment()
        for k, v in toolchain.clean_env(self.python).items():
            env.insert(k, v)
        p.setProcessEnvironment(env)
        if self.cwd:
            p.setWorkingDirectory(str(self.cwd))
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        p.readyReadStandardOutput.connect(self._read)
        p.finished.connect(self._done)
        p.errorOccurred.connect(self._error)
        self.proc = p
        self.output.emit("\n$ " + " ".join(f'"{a}"' if " " in a else a for a in args) + "\n")
        p.start(args[0], args[1:])

    def _read(self):
        if self.proc is None:
            return
        data = bytes(self.proc.readAllStandardOutput())
        text = ANSI.sub("", self._decoder.decode(data))
        if text:
            self.output.emit(text)

    def _done(self, code, status=None):
        self._read()
        if self._cancel:
            return
        if code != 0:
            self.output.emit(f"\n✖ 실패 (종료 코드 {code})\n")
            self._fail(code)
        else:
            self._next()

    def _error(self, err):
        if err == QProcess.ProcessError.FailedToStart and not self._cancel:
            prog = self.proc.program() if self.proc else "?"
            self.output.emit(f"\n✖ 실행할 수 없습니다: {prog}\n")
            self._fail(-1)

    def _fail(self, code):
        self.queue = []
        self.running = False
        self.finished.emit(code)

    def kill(self):
        if not self.running:
            return
        self._cancel = True
        self.queue = []
        if self.proc is not None and self.proc.state() != QProcess.ProcessState.NotRunning:
            self.proc.kill()
        self.running = False
        self.output.emit("\n■ 중지됨\n")
        self.finished.emit(-2)


class LogConsole(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Console")
        self.setReadOnly(True)
        self.setMaximumBlockCount(8000)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setPlaceholderText("여기에 작업 로그가 표시됩니다…")

    def append_text(self, text):
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        self.moveCursor(QTextCursor.MoveOperation.End)
        self.insertPlainText(text)
        self.moveCursor(QTextCursor.MoveOperation.End)
        self.ensureCursorVisible()

    def contextMenuEvent(self, e):
        menu = self.createStandardContextMenu()
        menu.addSeparator()
        menu.addAction("로그 지우기", self.clear)
        menu.exec(e.globalPos())


# ---------------------------------------------------------------- inputs
class ColorButton(QPushButton):
    colorChanged = Signal(str)

    def __init__(self, color="#ffffff", allow_alpha=True, allow_none=False, parent=None):
        super().__init__(parent)
        self.allow_alpha = allow_alpha
        self.allow_none = allow_none
        self._color = color
        self.setFixedHeight(30)
        self.setMinimumWidth(120)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._pick)
        self._refresh()

    def color(self):
        return self._color

    def setColor(self, c, emit=False):
        self._color = c if c else ("" if self.allow_none else "transparent")
        self._refresh()
        if emit:
            self.colorChanged.emit(self._color)

    def _refresh(self):
        if not self._color:
            self.setText("없음")
            self.setStyleSheet("QPushButton{border:1px dashed #888; border-radius:6px; font-size:9pt;}")
            return
        c = QColor(0, 0, 0, 0) if self._color == "transparent" else QColor(self._color)
        light = c.alpha() < 90 or c.lightness() > 150
        css = f"rgba({c.red()},{c.green()},{c.blue()},{c.alpha()})"
        txt = "#111" if light else "#fff"
        self.setText(self._color)
        self.setStyleSheet(f"QPushButton{{background:{css}; color:{txt}; border:1px solid #777; "
                           f"border-radius:6px; font-family:Consolas; font-size:9pt; padding:2px 8px;}}")

    def _pick(self):
        start = QColor(self._color) if self._color not in ("", "transparent") else QColor("#ffffff")
        if self.allow_alpha:
            c = QColorDialog.getColor(start, self.window(), "색 선택",
                                      QColorDialog.ColorDialogOption.ShowAlphaChannel)
        else:
            c = QColorDialog.getColor(start, self.window(), "색 선택")
        if c.isValid():
            name = c.name(QColor.NameFormat.HexArgb) if c.alpha() < 255 else c.name()
            self.setColor(name, emit=True)

    def contextMenuEvent(self, e):
        menu = QMenu(self)
        if self.allow_alpha:
            menu.addAction("투명", lambda: self.setColor("transparent", emit=True))
        if self.allow_none:
            menu.addAction("없음", lambda: self.setColor("", emit=True))
        menu.addAction("색 코드 복사", lambda: QApplication.clipboard().setText(self._color))
        menu.exec(e.globalPos())


class PathPicker(QWidget):
    changed = Signal(str)

    def __init__(self, mode="open", file_filter="", placeholder="", parent=None):
        super().__init__(parent)
        self.mode, self.file_filter = mode, file_filter
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        self.edit.textChanged.connect(self.changed)
        lay.addWidget(self.edit, 1)
        lay.addWidget(button("찾아보기…", self._browse))

    def text(self):
        return self.edit.text().strip().strip('"')

    def setText(self, t):
        self.edit.setText(str(t) if t else "")

    def _browse(self):
        start = self.text() or os.path.expanduser("~")
        if self.mode == "dir":
            p = QFileDialog.getExistingDirectory(self, "폴더 선택", start)
        elif self.mode == "save":
            p, _ = QFileDialog.getSaveFileName(self, "저장 위치", start, self.file_filter)
        else:
            p, _ = QFileDialog.getOpenFileName(self, "파일 선택", os.path.dirname(start) if os.path.isfile(start)
                                               else start, self.file_filter)
        if p:
            self.setText(os.path.normpath(p))


class InterpreterCombo(QComboBox):
    """Python interpreter picker kept in sync across the whole app."""

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self._busy = False
        self.setMinimumWidth(240)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        ctx.interpreters_changed.connect(self.reload)
        ctx.python_changed.connect(self._select)
        self.currentIndexChanged.connect(self._changed)
        self.reload()

    def reload(self):
        self._busy = True
        self.clear()
        for it in self.ctx.interpreters:
            self.addItem(f"[{it['source']}] Python {it['version']}", it["path"])
            self.setItemData(self.count() - 1, it["path"], Qt.ItemDataRole.ToolTipRole)
        if not self.ctx.interpreters:
            self.addItem("파이썬 검색 중… / 없음", "")
        self._select(self.ctx.python())
        self._busy = False

    def _select(self, path):
        i = self.findData(path)
        if i >= 0 and i != self.currentIndex():
            self.blockSignals(True)
            self.setCurrentIndex(i)
            self.blockSignals(False)

    def _changed(self, i):
        if self._busy:
            return
        path = self.itemData(i)
        if path:
            self.ctx.set_python(path)


# ---------------------------------------------------------------- page base
class Page(QWidget):
    TITLE = ""
    SUBTITLE = ""

    def __init__(self, ctx, scroll=False):
        super().__init__()
        self.ctx = ctx
        self.setObjectName("Page")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        holder = QWidget()
        holder.setObjectName("ScrollBody")
        self.root = QVBoxLayout(holder)
        self.root.setContentsMargins(28, 20, 28, 20)
        self.root.setSpacing(14)
        if scroll:
            area = QScrollArea()
            area.setWidgetResizable(True)
            area.setFrameShape(QFrame.Shape.NoFrame)
            area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            area.setWidget(holder)
            outer.addWidget(area)
        else:
            outer.addWidget(holder)
        if self.TITLE:
            head = QVBoxLayout()
            head.setSpacing(2)
            head.addWidget(label(self.TITLE, "H1"))
            if self.SUBTITLE:
                head.addWidget(label(self.SUBTITLE, "Sub", wrap=True))
            self.root.addLayout(head)

    def on_show(self):
        pass

    def toast(self, text):
        self.ctx.toast(text)


class Toast(QLabel):
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_text(self, text, ms=2600):
        self.setText(text)
        self.adjustSize()
        p = self.parentWidget()
        self.move(p.width() - self.width() - 24, p.height() - self.height() - 24)
        self.raise_()
        self.show()
        self._timer.start(ms)


def tile(text, slot=None, checkable=False, height=76):
    """Big two-line card button that shrinks with the window instead of forcing horizontal scroll."""
    b = QPushButton(text)
    b.setObjectName("Tile")
    b.setCheckable(checkable)
    b.setMinimumHeight(height)
    b.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setToolTip(text.replace("\n", " — "))
    if slot:
        b.clicked.connect(slot)
    return b
