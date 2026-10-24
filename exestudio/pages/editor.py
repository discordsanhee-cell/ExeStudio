import builtins
import keyword
import os
from pathlib import Path

from PySide6.QtCore import QRect, QRegularExpression, QSize, Qt
from PySide6.QtGui import (QColor, QFont, QFontMetricsF, QKeySequence, QPainter, QShortcut, QSyntaxHighlighter,
                           QTextCharFormat, QTextCursor, QTextFormat)
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QInputDialog, QMessageBox, QPlainTextEdit, QSplitter,
                               QTabWidget, QTextEdit, QVBoxLayout, QWidget)

from ..widgets import InterpreterCombo, LogConsole, Page, ProcessRunner, button, label

DARK = {"kw": "#c792ea", "builtin": "#82aaff", "self": "#f78c6c", "num": "#f78c6c", "str": "#c3e88d",
        "comment": "#676e95", "deco": "#ffcb6b", "defname": "#82aaff", "line": "#1f2030", "num_fg": "#4b4e6b",
        "num_bg": "#13141b"}
LIGHT = {"kw": "#8a2be2", "builtin": "#1f5fbf", "self": "#c2410c", "num": "#c2410c", "str": "#2e7d32",
         "comment": "#8a8fa3", "deco": "#b7791f", "defname": "#1f5fbf", "line": "#eef0f8", "num_fg": "#a0a4b8",
         "num_bg": "#f7f8fb"}


def _fmt(color, bold=False, italic=False):
    f = QTextCharFormat()
    f.setForeground(QColor(color))
    if bold:
        f.setFontWeight(QFont.Weight.Bold)
    f.setFontItalic(italic)
    return f


class PyHighlighter(QSyntaxHighlighter):
    def __init__(self, doc, colors):
        super().__init__(doc)
        c = colors
        self.rules = []
        kw = r"\b(" + "|".join(keyword.kwlist + ["match", "case"]) + r")\b"
        self.rules.append((QRegularExpression(kw), _fmt(c["kw"], bold=True)))
        bi = r"\b(" + "|".join(n for n in dir(builtins) if not n.startswith("_")) + r")\b"
        self.rules.append((QRegularExpression(bi), _fmt(c["builtin"])))
        self.rules.append((QRegularExpression(r"\b(self|cls)\b"), _fmt(c["self"], italic=True)))
        self.rules.append((QRegularExpression(r"\b[0-9][0-9_]*\.?[0-9_]*([eE][-+]?[0-9]+)?\b"), _fmt(c["num"])))
        self.rules.append((QRegularExpression(r"@[\w.]+"), _fmt(c["deco"])))
        self.rules.append((QRegularExpression(r"\b(?:def|class)\s+(\w+)"), _fmt(c["defname"], bold=True)))
        self.str_fmt = _fmt(c["str"])
        self.comment_fmt = _fmt(c["comment"], italic=True)
        self.str_re = QRegularExpression(r"""[rRbBfFuU]{0,2}("([^"\\\n]|\\.)*"|'([^'\\\n]|\\.)*')""")
        self.comment_re = QRegularExpression(r"#[^\n]*")
        self.tri = [(QRegularExpression('"""'), 1), (QRegularExpression("'''"), 2)]

    def highlightBlock(self, text):
        for rx, fmt in self.rules:
            it = rx.globalMatch(text)
            while it.hasNext():
                m = it.next()
                grp = 1 if rx.captureCount() >= 1 and m.capturedStart(1) >= 0 and "def" in rx.pattern() else 0
                self.setFormat(m.capturedStart(grp), m.capturedLength(grp), fmt)
        protected = []
        it = self.str_re.globalMatch(text)
        while it.hasNext():
            m = it.next()
            self.setFormat(m.capturedStart(), m.capturedLength(), self.str_fmt)
            protected.append((m.capturedStart(), m.capturedEnd()))
        it = self.comment_re.globalMatch(text)
        while it.hasNext():
            m = it.next()
            s = m.capturedStart()
            if not any(a <= s < b for a, b in protected):
                self.setFormat(s, len(text) - s, self.comment_fmt)
                break
        self.setCurrentBlockState(0)
        for rx, state in self.tri:
            if self._multiline(text, rx, state):
                break

    def _multiline(self, text, rx, state):
        if self.previousBlockState() == state:
            start, add = 0, 0
        else:
            m = rx.match(text)
            start = m.capturedStart()
            if start < 0:
                return False
            add = 3
        while start >= 0:
            m = rx.match(text, start + add)
            end = m.capturedStart()
            if end >= 0:
                length = end - start + add + 3
                self.setCurrentBlockState(0)
            else:
                self.setCurrentBlockState(state)
                length = len(text) - start
            self.setFormat(start, length, self.str_fmt)
            nxt = rx.match(text, start + length)
            start = nxt.capturedStart()
            add = 3
            if self.currentBlockState() == state:
                return True
        return False


class _NumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.number_width(), 0)

    def paintEvent(self, e):
        self.editor.paint_numbers(e)


class CodeEditor(QPlainTextEdit):
    def __init__(self, path=None, dark=True):
        super().__init__()
        self.path = path
        self.colors = DARK if dark else LIGHT
        f = QFont("Consolas", 11)
        f.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(f)
        self.setStyleSheet("QPlainTextEdit { font-family: Consolas, 'D2Coding', monospace; font-size: 11pt; "
                           "border-radius: 0; border: none; }")
        self.setTabStopDistance(QFontMetricsF(f).horizontalAdvance(" ") * 4)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.numbers = _NumberArea(self)
        self.blockCountChanged.connect(self._update_width)
        self.updateRequest.connect(self._update_area)
        self.cursorPositionChanged.connect(self._highlight_line)
        self._update_width()
        self._highlight_line()
        self.hl = PyHighlighter(self.document(), self.colors)

    def number_width(self):
        digits = len(str(max(1, self.blockCount())))
        return 18 + self.fontMetrics().horizontalAdvance("9") * max(3, digits)

    def _update_width(self, *_):
        self.setViewportMargins(self.number_width(), 0, 0, 0)

    def _update_area(self, rect, dy):
        if dy:
            self.numbers.scroll(0, dy)
        else:
            self.numbers.update(0, rect.y(), self.numbers.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_width()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        cr = self.contentsRect()
        self.numbers.setGeometry(QRect(cr.left(), cr.top(), self.number_width(), cr.height()))

    def paint_numbers(self, e):
        p = QPainter(self.numbers)
        p.fillRect(e.rect(), QColor(self.colors["num_bg"]))
        block = self.firstVisibleBlock()
        num = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        cur = self.textCursor().blockNumber()
        h = self.fontMetrics().height()
        while block.isValid() and top <= e.rect().bottom():
            if block.isVisible() and bottom >= e.rect().top():
                p.setPen(QColor(self.colors["kw"] if num == cur else self.colors["num_fg"]))
                p.drawText(0, top, self.numbers.width() - 8, h, Qt.AlignmentFlag.AlignRight, str(num + 1))
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            num += 1
        p.end()

    def _highlight_line(self):
        sel = QTextEdit.ExtraSelection()
        sel.format.setBackground(QColor(self.colors["line"]))
        sel.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        sel.cursor = self.textCursor()
        sel.cursor.clearSelection()
        self.setExtraSelections([sel])

    def keyPressEvent(self, e):
        cur = self.textCursor()
        if e.key() == Qt.Key.Key_Tab and not cur.hasSelection():
            cur.insertText("    ")
            return
        if e.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab) and cur.hasSelection():
            self._indent(e.key() == Qt.Key.Key_Backtab)
            return
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            line = cur.block().text()[:cur.positionInBlock()]
            indent = line[:len(line) - len(line.lstrip())]
            if line.rstrip().endswith(":"):
                indent += "    "
            super().keyPressEvent(e)
            self.textCursor().insertText(indent)
            return
        if e.key() == Qt.Key.Key_Slash and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._toggle_comment()
            return
        super().keyPressEvent(e)

    def _selected_blocks(self):
        cur = self.textCursor()
        doc = self.document()
        a = doc.findBlock(cur.selectionStart()).blockNumber()
        b = doc.findBlock(max(cur.selectionStart(), cur.selectionEnd() - (1 if cur.hasSelection() else 0)))
        return a, b.blockNumber()

    def _indent(self, dedent):
        a, b = self._selected_blocks()
        cur = self.textCursor()
        cur.beginEditBlock()
        for n in range(a, b + 1):
            blk = self.document().findBlockByNumber(n)
            c = QTextCursor(blk)
            if dedent:
                txt = blk.text()
                k = len(txt) - len(txt.lstrip(" "))
                for _ in range(min(4, k)):
                    c.deleteChar()
            else:
                c.insertText("    ")
        cur.endEditBlock()

    def _toggle_comment(self):
        a, b = self._selected_blocks()
        blocks = [self.document().findBlockByNumber(n) for n in range(a, b + 1)]
        uncomment = all(bl.text().lstrip().startswith("#") or not bl.text().strip() for bl in blocks)
        cur = self.textCursor()
        cur.beginEditBlock()
        for bl in blocks:
            txt = bl.text()
            if not txt.strip():
                continue
            k = len(txt) - len(txt.lstrip())
            c = QTextCursor(bl)
            c.movePosition(QTextCursor.MoveOperation.Right, n=k)
            if uncomment:
                drop = 2 if txt[k:k + 2] == "# " else 1
                for _ in range(drop):
                    c.deleteChar()
            else:
                c.insertText("# ")
        cur.endEditBlock()


class EditorPage(Page):
    TITLE = "코드 에디터"
    SUBTITLE = "파이썬 코드를 쓰고 바로 실행해 보세요. Ctrl+S 저장 · F5 실행 · Ctrl+/ 주석 · Ctrl+F 찾기"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.runner = ProcessRunner(self)
        bar = QHBoxLayout()
        bar.setSpacing(6)
        for text, slot in [("📄 새 파일", self.new_file), ("📂 열기", self.open_dialog), ("💾 저장", self.save),
                           ("다른 이름으로", self.save_as)]:
            bar.addWidget(button(text, slot))
        bar.addSpacing(12)
        self.run_btn = button("▶ 실행 (F5)", self.run, accent=True)
        self.stop_btn = button("■ 중지", self.runner.kill)
        bar.addWidget(self.run_btn)
        bar.addWidget(self.stop_btn)
        bar.addWidget(button("🔨 EXE 빌드", self.build_this, tip="이 파일을 EXE로 빌드"))
        bar.addWidget(button("🔍", self.find, tip="찾기 (Ctrl+F)"))
        bar.addStretch(1)
        combo = InterpreterCombo(ctx)
        combo.setMinimumWidth(190)
        bar.addWidget(combo)
        self.root.addLayout(bar)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.console = LogConsole()
        split = QSplitter(Qt.Orientation.Vertical)
        split.addWidget(self.tabs)
        split.addWidget(self.console)
        split.setSizes([520, 180])
        self.root.addWidget(split, 1)
        self.runner.output.connect(self.console.append_text)
        self.runner.finished.connect(lambda c: self.console.append_text(
            "\n✔ 실행 종료\n" if c == 0 else ""))

        for seq, slot in [("Ctrl+S", self.save), ("F5", self.run), ("Ctrl+O", self.open_dialog),
                          ("Ctrl+N", self.new_file), ("Ctrl+F", self.find), ("F3", self.find_next)]:
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(slot)
        self._last_find = ""
        self.new_file()

    # ---- tabs ----------------------------------------------------------
    def current(self):
        return self.tabs.currentWidget()

    def _add_editor(self, ed, title):
        ed.document().modificationChanged.connect(lambda m, e=ed: self._retitle(e))
        i = self.tabs.addTab(ed, title)
        self.tabs.setCurrentIndex(i)
        self._retitle(ed)
        return ed

    def _retitle(self, ed):
        i = self.tabs.indexOf(ed)
        if i < 0:
            return
        name = Path(ed.path).name if ed.path else "새 파일"
        self.tabs.setTabText(i, ("● " if ed.document().isModified() else "") + name)
        self.tabs.setTabToolTip(i, ed.path or "저장되지 않음")

    def new_file(self, text=None):
        ed = CodeEditor(dark=self.ctx.theme["dark"])
        ed.setPlainText(text if isinstance(text, str) else
                        '# 새 파이썬 파일\n\nprint("안녕하세요, EXE Studio!")\n')
        ed.document().setModified(isinstance(text, str))
        return self._add_editor(ed, "새 파일")

    def open_file(self, path):
        path = os.path.normpath(str(path))
        for i in range(self.tabs.count()):
            ed = self.tabs.widget(i)
            if ed.path and os.path.normcase(ed.path) == os.path.normcase(path):
                self.tabs.setCurrentIndex(i)
                return ed
        try:
            text = Path(path).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = Path(path).read_text(encoding="cp949", errors="replace")
        except OSError as e:
            QMessageBox.warning(self, "열기 실패", str(e))
            return None
        cur = self.current()
        if cur is not None and not cur.path and not cur.document().isModified() and self.tabs.count() == 1:
            self.tabs.removeTab(0)
        ed = CodeEditor(path, dark=self.ctx.theme["dark"])
        ed.setPlainText(text)
        ed.document().setModified(False)
        self.ctx.settings.add_recent(path)
        return self._add_editor(ed, Path(path).name)

    def open_dialog(self):
        p, _ = QFileDialog.getOpenFileName(self, "파이썬 파일 열기", self.ctx.settings["projects_dir"],
                                           "Python (*.py *.pyw);;모든 파일 (*.*)")
        if p:
            self.open_file(p)

    def save(self, ed=None):
        ed = ed or self.current()
        if ed is None:
            return False
        if not ed.path:
            return self.save_as(ed)
        Path(ed.path).write_text(ed.toPlainText(), encoding="utf-8")
        ed.document().setModified(False)
        self._retitle(ed)
        return True

    def save_as(self, ed=None):
        ed = ed or self.current()
        if ed is None:
            return False
        p, _ = QFileDialog.getSaveFileName(self, "다른 이름으로 저장", ed.path or self.ctx.settings["projects_dir"],
                                           "Python (*.py);;GUI Python (*.pyw)")
        if not p:
            return False
        ed.path = os.path.normpath(p)
        self.ctx.settings.add_recent(ed.path)
        return self.save(ed)

    def close_tab(self, i):
        ed = self.tabs.widget(i)
        if ed.document().isModified():
            r = QMessageBox.question(self, "저장", f"'{self.tabs.tabText(i).lstrip('● ')}' 변경 내용을 저장할까요?",
                                     QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
                                     | QMessageBox.StandardButton.Cancel)
            if r == QMessageBox.StandardButton.Cancel:
                return False
            if r == QMessageBox.StandardButton.Save and not self.save(ed):
                return False
        self.tabs.removeTab(i)
        ed.deleteLater()
        if self.tabs.count() == 0:
            self.new_file()
        return True

    def maybe_save_all(self):
        for i in reversed(range(self.tabs.count())):
            ed = self.tabs.widget(i)
            if ed.document().isModified():
                self.tabs.setCurrentIndex(i)
                if not self.close_tab(i):
                    return False
        return True

    # ---- actions -------------------------------------------------------
    def run(self):
        ed = self.current()
        if ed is None or not self.save(ed):
            return
        py = self.ctx.python()
        if not py:
            QMessageBox.warning(self, "Python 없음", "파이썬이 없습니다. '도구 설치'에서 설치하세요.")
            return
        self.console.clear()
        self.runner.run([[py, "-u", ed.path]], cwd=os.path.dirname(ed.path), python=py)

    def build_this(self):
        ed = self.current()
        if ed is None or not self.save(ed):
            return
        self.ctx.main.page("build").set_script(ed.path)
        self.ctx.main.goto("build")

    def find(self):
        text, ok = QInputDialog.getText(self, "찾기", "찾을 내용:", text=self._last_find)
        if ok and text:
            self._last_find = text
            self.find_next()

    def find_next(self):
        ed = self.current()
        if ed is None or not self._last_find:
            return
        if not ed.find(self._last_find):
            ed.moveCursor(QTextCursor.MoveOperation.Start)
            if not ed.find(self._last_find):
                self.toast(f"'{self._last_find}' 을(를) 찾을 수 없어요")
