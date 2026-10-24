import base64
import copy
import json
import os
import traceback
from types import SimpleNamespace

from PySide6.QtCore import QMimeData, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QDrag, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QProgressBar,
                               QPushButton, QRadioButton, QScrollArea, QSlider, QSpinBox, QSplitter, QTextEdit,
                               QVBoxLayout, QWidget)

from .. import codegen
from ..frameless import TitleBar
from ..widgets import ColorButton, Page, PathPicker, button, label

EXEC_NS = {"QLabel": QLabel, "QPushButton": QPushButton, "QLineEdit": QLineEdit, "QTextEdit": QTextEdit,
           "QCheckBox": QCheckBox, "QRadioButton": QRadioButton, "QComboBox": QComboBox, "QListWidget": QListWidget,
           "QSlider": QSlider, "QProgressBar": QProgressBar, "QSpinBox": QSpinBox, "QFrame": QFrame, "Qt": Qt,
           "QPixmap": QPixmap, "base64": base64}

GEOMETRY_KEYS = ("x", "y", "w", "h")


def _snap(v, step):
    return int(round(v / step) * step) if step > 1 else int(v)


class _Overlay(QWidget):
    def __init__(self, item):
        super().__init__(item)
        self.item = item
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, e):
        canvas = self.item.canvas
        if canvas.selected is not self.item and not self.item.hovered:
            return
        p = QPainter(self)
        acc = QColor(canvas.accent)
        if canvas.selected is self.item:
            pen = QPen(acc, 1.5, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawRect(self.rect().adjusted(1, 1, -1, -1))
            h = DesignItem.HANDLE
            p.fillRect(self.width() - h, self.height() - h, h, h, acc)
        else:
            acc.setAlpha(120)
            p.setPen(QPen(acc, 1))
            p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        p.end()


class DesignItem(QWidget):
    HANDLE = 10

    def __init__(self, canvas, data):
        super().__init__(canvas)
        self.canvas = canvas
        self.data = data
        self.inner = None
        self.hovered = False
        self._drag = None
        self.setMouseTracking(True)
        self.overlay = _Overlay(self)
        self.rebuild()
        self.show()

    def rebuild(self):
        if self.inner is not None:
            self.inner.hide()
            self.inner.deleteLater()
        holder = SimpleNamespace(content=self)
        ns = dict(EXEC_NS)
        ns["self"] = holder
        try:
            exec("\n".join(codegen.widget_lines(self.data)), ns)
            w = getattr(holder, self.data["name"])
        except Exception as e:
            w = QLabel(f"⚠ {e}", self)
            w.setStyleSheet("color:#e5484d; background:#2a1518;")
        for c in [w] + w.findChildren(QWidget):
            c.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            c.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.inner = w
        w.show()
        self.sync_geometry()
        self.overlay.raise_()

    def sync_geometry(self):
        d = self.data
        self.setGeometry(d["x"], d["y"], d["w"], d["h"])
        self.inner.setGeometry(0, 0, d["w"], d["h"])
        self.overlay.setGeometry(0, 0, d["w"], d["h"])

    def _in_handle(self, p):
        return p.x() >= self.width() - self.HANDLE - 2 and p.y() >= self.height() - self.HANDLE - 2

    def enterEvent(self, e):
        self.hovered = True
        self.overlay.update()

    def leaveEvent(self, e):
        self.hovered = False
        self.overlay.update()

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return
        self.canvas.select(self)
        self.canvas.setFocus()
        mode = "resize" if self._in_handle(e.position().toPoint()) else "move"
        self._drag = (mode, e.globalPosition().toPoint(), QRect(self.geometry()))

    def mouseMoveEvent(self, e):
        p = e.position().toPoint()
        if self._drag is None:
            self.setCursor(Qt.CursorShape.SizeFDiagCursor if self._in_handle(p) else Qt.CursorShape.SizeAllCursor)
            return
        mode, start, geo = self._drag
        delta = e.globalPosition().toPoint() - start
        step = 1 if e.modifiers() & Qt.KeyboardModifier.AltModifier else self.canvas.snap
        d = self.data
        if mode == "move":
            d["x"] = max(0, min(_snap(geo.x() + delta.x(), step), self.canvas.width() - geo.width()))
            d["y"] = max(0, min(_snap(geo.y() + delta.y(), step), self.canvas.height() - geo.height()))
        else:
            d["w"] = max(16, _snap(geo.width() + delta.x(), step))
            d["h"] = max(12, _snap(geo.height() + delta.y(), step))
        self.sync_geometry()
        self.canvas.geometry_changed.emit(self)

    def mouseReleaseEvent(self, e):
        if self._drag is not None:
            self._drag = None
            self.canvas.committed.emit()


class DesignCanvas(QWidget):
    selection_changed = Signal(object)
    geometry_changed = Signal(object)
    committed = Signal()
    drop_requested = Signal(str, QPoint)

    def __init__(self):
        super().__init__()
        self.items = []
        self.selected = None
        self.snap = 8
        self.bg = "#14151c"
        self.accent = "#7c6cff"
        self.key_handler = None
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def paintEvent(self, e):
        p = QPainter(self)
        bg = QColor(self.bg)
        p.fillRect(self.rect(), bg)
        if self.snap > 1:
            dot = bg.lighter(170) if bg.lightness() < 128 else bg.darker(125)
            p.setPen(dot)
            step = self.snap * 2
            for x in range(0, self.width(), step):
                for y in range(0, self.height(), step):
                    p.drawPoint(x, y)
        p.end()

    def add(self, data):
        item = DesignItem(self, data)
        self.items.append(item)
        return item

    def remove(self, item):
        if item in self.items:
            self.items.remove(item)
        if self.selected is item:
            self.select(None)
        item.hide()
        item.deleteLater()

    def clear_items(self):
        for item in list(self.items):
            self.remove(item)

    def select(self, item):
        if self.selected is item:
            return
        old, self.selected = self.selected, item
        for it in (old, item):
            if it is not None:
                it.overlay.update()
        self.selection_changed.emit(item)

    def mousePressEvent(self, e):
        self.select(None)
        self.setFocus()

    def keyPressEvent(self, e):
        if self.key_handler and self.key_handler(e):
            return
        super().keyPressEvent(e)

    def dragEnterEvent(self, e):
        if e.mimeData().hasText() and e.mimeData().text().startswith("esd:"):
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        e.acceptProposedAction()

    def dropEvent(self, e):
        self.drop_requested.emit(e.mimeData().text()[4:], e.position().toPoint())
        e.acceptProposedAction()


class PaletteList(QListWidget):
    def __init__(self):
        super().__init__()
        self.setDragEnabled(True)
        for kind, meta in codegen.TYPES.items():
            item = QListWidgetItem(f"{meta['icon']}   {meta['name']}")
            item.setData(Qt.ItemDataRole.UserRole, kind)
            self.addItem(item)

    def startDrag(self, actions):
        it = self.currentItem()
        if it is None:
            return
        mime = QMimeData()
        mime.setText("esd:" + it.data(Qt.ItemDataRole.UserRole))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)


def empty_design():
    return {"title": "내 앱", "width": 720, "height": 460, "bg": "#14151c", "items": []}


class DesignerPage(Page):
    TITLE = "GUI 디자이너"
    SUBTITLE = "왼쪽 위젯을 캔버스로 끌어다 놓고, 오른쪽에서 글자·색·동작을 바꾸세요. 버튼 클릭 동작도 코딩 없이 정할 수 있어요."

    def __init__(self, ctx):
        super().__init__(ctx)
        self.design = empty_design()
        self.file_path = None
        self.history, self.hpos = [], -1
        self._previews = []
        self._commit_timer = QTimer(self)
        self._commit_timer.setSingleShot(True)
        self._commit_timer.setInterval(450)
        self._commit_timer.timeout.connect(self.push_history)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        for text, slot, tip in [("📄", self.new_design, "새 디자인"), ("📂", self.open_design, "디자인 열기 (.esd)"),
                                ("💾", self.save_design, "디자인 저장"), (None, None, None),
                                ("↶", self.undo, "실행 취소 (Ctrl+Z)"), ("↷", self.redo, "다시 실행 (Ctrl+Y)"),
                                ("⧉", self.duplicate, "복제 (Ctrl+D)"), ("🗑", self.delete_selected, "삭제 (Delete)"),
                                ("⬆", lambda: self.reorder(True), "맨 앞으로"),
                                ("⬇", lambda: self.reorder(False), "맨 뒤로"), (None, None, None),
                                ("👁 미리보기", self.preview, "실제 창으로 띄워보기"),
                                ("💻 코드", self.show_code, "생성된 코드를 에디터로"),
                                ("📤 .py", self.export_py, ".py 파일로 내보내기")]:
            if text is None:
                bar.addSpacing(10)
                continue
            b = button(text, slot, tip=tip)
            if len(text) <= 2:
                b.setFixedWidth(40)
            bar.addWidget(b)
        bar.addStretch(1)
        bar.addWidget(button("🔨 바로 EXE 빌드", self.build_exe, accent=True))
        self.root.addLayout(bar)

        split = QSplitter(Qt.Orientation.Horizontal)
        self.root.addWidget(split, 1)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(label("위젯 (끌어놓기 / 더블클릭)", "Sub"))
        self.palette = PaletteList()
        self.palette.itemDoubleClicked.connect(
            lambda it: self.add_item(it.data(Qt.ItemDataRole.UserRole), QPoint(24, 24)))
        ll.addWidget(self.palette, 3)
        ll.addWidget(label("레이어", "Sub"))
        self.layers = QListWidget()
        self.layers.currentRowChanged.connect(self._layer_selected)
        ll.addWidget(self.layers, 2)
        left.setMinimumWidth(180)
        split.addWidget(left)

        center = QScrollArea()
        center.setWidgetResizable(True)
        holder = QWidget()
        holder.setObjectName("CanvasHolder")
        holder.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(24, 24, 24, 24)
        self.window_frame = QFrame()
        self.window_frame.setObjectName("DesignWindow")
        wf = QVBoxLayout(self.window_frame)
        wf.setContentsMargins(1, 1, 1, 1)
        wf.setSpacing(0)
        self.tb_preview = TitleBar(self.window_frame, ctx.design_titlebar(), preview=True)
        wf.addWidget(self.tb_preview)
        self.canvas = DesignCanvas()
        self.canvas.accent = ctx.theme["accent"]
        self.canvas.key_handler = self._canvas_key
        self.canvas.selection_changed.connect(self._on_select)
        self.canvas.geometry_changed.connect(self._on_geometry)
        self.canvas.committed.connect(self.push_history)
        self.canvas.drop_requested.connect(self.add_item)
        wf.addWidget(self.canvas)
        hl.addWidget(self.window_frame, 0, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        hl.addStretch(1)
        center.setWidget(holder)
        split.addWidget(center)

        self.props_scroll = QScrollArea()
        self.props_scroll.setWidgetResizable(True)
        self.props_scroll.setMinimumWidth(300)
        split.addWidget(self.props_scroll)
        split.setSizes([200, 760, 320])
        split.setStretchFactor(1, 1)

        ctx.titlebar_changed.connect(self._titlebar_changed)
        self.load_design(empty_design())
        self.push_history()

    # ------------------------------------------------ design lifecycle
    def load_design(self, design):
        self.canvas.select(None)
        self.canvas.clear_items()
        self.design = codegen.sanitize_design(design)
        for data in self.design["items"]:
            self.canvas.add(data)
        self._apply_window()
        self._refresh_layers()
        self._show_props()

    def _apply_window(self):
        d = self.design
        self.canvas.bg = d["bg"]
        self.canvas.setFixedSize(int(d["width"]), int(d["height"]))
        self.canvas.update()
        cfg = self.ctx.design_titlebar()
        cfg["title"] = d["title"]
        self.tb_preview.apply(cfg)
        self.window_frame.setStyleSheet(f"QFrame#DesignWindow {{ border: 1px solid {cfg['border']}; }}")

    def _titlebar_changed(self, cfg):
        self._apply_window()

    def push_history(self):
        snap = json.dumps(self.design, ensure_ascii=False)
        if self.history and self.history[self.hpos] == snap:
            return
        self.history = self.history[:self.hpos + 1] + [snap]
        self.history = self.history[-100:]
        self.hpos = len(self.history) - 1

    def _restore(self):
        sel = self.canvas.selected.data["name"] if self.canvas.selected else None
        self.load_design(json.loads(self.history[self.hpos]))
        for it in self.canvas.items:
            if it.data["name"] == sel:
                self.canvas.select(it)

    def undo(self):
        self._commit_timer.stop()
        self.push_history()
        if self.hpos > 0:
            self.hpos -= 1
            self._restore()

    def redo(self):
        if self.hpos < len(self.history) - 1:
            self.hpos += 1
            self._restore()

    def _schedule_commit(self):
        self._commit_timer.start()

    # ------------------------------------------------ items
    def _unique_name(self, kind):
        used = {d["name"] for d in self.design["items"]}
        n = 1
        prefix = codegen.KOREAN_NAMES.get(kind, kind)
        while f"{prefix}{n}" in used:
            n += 1
        return f"{prefix}{n}"

    def _unique(self, base, exclude=None):
        used = {d["name"] for d in self.design["items"] if d is not exclude}
        name, n = base, 2
        while name in used or not codegen.valid_name(name):
            name = f"{base}{n}"
            n += 1
            if n > 99:
                return None
        return name

    def _apply_rename(self, it, new):
        old = it.data["name"]
        it.data["name"] = new
        it.rebuild()
        self._refresh_layers()
        self.ctx.main.page("blocks").rename_widget(old, new)

    def add_item(self, kind, pos):
        if kind not in codegen.TYPES:
            return
        meta = codegen.TYPES[kind]
        x = max(0, min(_snap(pos.x(), self.canvas.snap), self.canvas.width() - meta["w"]))
        y = max(0, min(_snap(pos.y(), self.canvas.snap), self.canvas.height() - meta["h"]))
        data = codegen.new_item(kind, x, y, self._unique_name(kind))
        data["auto_name"] = True
        if kind in ("button", "progress", "slider", "checkbox", "radio", "input", "textbox", "combo", "list"):
            data["accent"] = self.ctx.theme["accent"]
            if kind == "button":
                data["bg"] = self.ctx.theme["accent"]
        self.design["items"].append(data)
        item = self.canvas.add(data)
        self.canvas.select(item)
        self._refresh_layers()
        self.push_history()

    def delete_selected(self):
        it = self.canvas.selected
        if it is None:
            return
        self.design["items"].remove(it.data)
        self.canvas.remove(it)
        self._refresh_layers()
        self.push_history()

    def duplicate(self):
        it = self.canvas.selected
        if it is None:
            return
        data = copy.deepcopy(it.data)
        data["name"] = self._unique_name(data["type"])
        data["x"] += 16
        data["y"] += 16
        self.design["items"].append(data)
        new = self.canvas.add(data)
        self.canvas.select(new)
        self._refresh_layers()
        self.push_history()

    def reorder(self, front):
        it = self.canvas.selected
        if it is None:
            return
        items = self.design["items"]
        items.remove(it.data)
        if front:
            items.append(it.data)
            it.raise_()
        else:
            items.insert(0, it.data)
            it.lower()
        self.canvas.items.remove(it)
        if front:
            self.canvas.items.append(it)
        else:
            self.canvas.items.insert(0, it)
        self._refresh_layers()
        self.push_history()

    def _canvas_key(self, e):
        it = self.canvas.selected
        mods = e.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        k = e.key()
        if ctrl and k == Qt.Key.Key_Z:
            self.undo()
            return True
        if ctrl and k == Qt.Key.Key_Y:
            self.redo()
            return True
        if it is None:
            return False
        if k in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_selected()
            return True
        if ctrl and k == Qt.Key.Key_D:
            self.duplicate()
            return True
        step = 8 if mods & Qt.KeyboardModifier.ShiftModifier else 1
        moves = {Qt.Key.Key_Left: (-step, 0), Qt.Key.Key_Right: (step, 0), Qt.Key.Key_Up: (0, -step),
                 Qt.Key.Key_Down: (0, step)}
        if k in moves:
            dx, dy = moves[k]
            it.data["x"] = max(0, it.data["x"] + dx)
            it.data["y"] = max(0, it.data["y"] + dy)
            it.sync_geometry()
            self._on_geometry(it)
            self._schedule_commit()
            return True
        return False

    # ------------------------------------------------ layers
    def _refresh_layers(self):
        self.layers.blockSignals(True)
        self.layers.clear()
        for d in reversed(self.design["items"]):
            meta = codegen.TYPES[d["type"]]
            text = d.get("text") or ""
            item = QListWidgetItem(f"{meta['icon']}  {d['name']}" + (f"  — {text[:14]}" if text else ""))
            item.setData(Qt.ItemDataRole.UserRole, d["name"])
            self.layers.addItem(item)
        sel = self.canvas.selected
        if sel is not None:
            for i in range(self.layers.count()):
                if self.layers.item(i).data(Qt.ItemDataRole.UserRole) == sel.data["name"]:
                    self.layers.setCurrentRow(i)
        self.layers.blockSignals(False)

    def _layer_selected(self, row):
        if row < 0:
            return
        name = self.layers.item(row).data(Qt.ItemDataRole.UserRole)
        for it in self.canvas.items:
            if it.data["name"] == name:
                self.canvas.select(it)

    def _on_select(self, item):
        self._refresh_layers()
        self._show_props()

    def _on_geometry(self, item):
        for key in GEOMETRY_KEYS:
            w = self.prop_widgets.get(key)
            if w is not None:
                w.blockSignals(True)
                w.setValue(int(item.data[key]))
                w.blockSignals(False)

    # ------------------------------------------------ property panel
    def _show_props(self):
        host = QWidget()
        host.setObjectName("ScrollBody")
        lay = QVBoxLayout(host)
        lay.setContentsMargins(4, 0, 4, 0)
        lay.setSpacing(10)
        self.prop_widgets = {}
        it = self.canvas.selected
        if it is None:
            self._window_props(lay)
        else:
            self._item_props(lay, it)
        lay.addStretch(1)
        self.props_scroll.setWidget(host)

    def _form(self, lay, title):
        lay.addWidget(label(title, "H2"))
        f = QFormLayout()
        f.setSpacing(8)
        f.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        lay.addLayout(f)
        return f

    def _field(self, form, data, key, text, kind, on_change, **o):
        val = data.get(key)
        if kind == "text":
            w = QLineEdit(str(val if val is not None else ""))
            w.textChanged.connect(lambda v: on_change(key, v))
        elif kind == "multiline":
            w = QPlainTextEdit(str(val or ""))
            w.setFixedHeight(o.get("height", 90))
            w.setStyleSheet("font-family: Consolas; font-size: 9pt;")
            w.textChanged.connect(lambda: on_change(key, w.toPlainText()))
        elif kind == "int":
            w = QSpinBox()
            w.setRange(o.get("lo", 0), o.get("hi", 9999))
            w.setValue(int(val or 0))
            w.valueChanged.connect(lambda v: on_change(key, v))
        elif kind == "bool":
            w = QCheckBox(o.get("caption", ""))
            w.setChecked(bool(val))
            w.toggled.connect(lambda v: on_change(key, v))
        elif kind == "color":
            w = ColorButton(val or "transparent")
            w.colorChanged.connect(lambda v: on_change(key, v))
        elif kind == "choice":
            w = QComboBox()
            for value, name in o["choices"]:
                w.addItem(name, value)
            w.setCurrentIndex(max(0, w.findData(val)))
            w.currentIndexChanged.connect(lambda i: on_change(key, w.itemData(i)))
        elif kind == "file":
            w = PathPicker("open", "이미지 (*.png *.jpg *.jpeg *.gif *.bmp *.ico *.webp)")
            w.setText(val or "")
            w.changed.connect(lambda v: on_change(key, w.text()))
        else:
            raise ValueError(kind)
        form.addRow(text, w)
        self.prop_widgets[key] = w
        return w

    def _window_props(self, lay):
        f = self._form(lay, "🪟 창 설정")
        self._field(f, self.design, "title", "창 제목", "text", self._set_window)
        self._field(f, self.design, "width", "너비", "int", self._set_window, lo=120, hi=4000)
        self._field(f, self.design, "height", "높이", "int", self._set_window, lo=80, hi=3000)
        self._field(f, self.design, "bg", "배경색", "color", self._set_window)
        snap = QSpinBox()
        snap.setRange(1, 64)
        snap.setValue(self.canvas.snap)
        snap.valueChanged.connect(self._set_snap)
        f.addRow("그리드 간격", snap)
        lay.addWidget(label("타이틀바(X ㅁ ㅡ)는 '타이틀바 꾸미기'에서 만든 디자인이 그대로 들어갑니다.", "Sub", wrap=True))
        lay.addWidget(button("🪟 타이틀바 꾸미러 가기", lambda: self.ctx.main.goto("titlebar")))
        lay.addWidget(label("팁: 위젯 선택 후 방향키로 1px, Shift+방향키로 8px 이동 · Alt 누른 채 드래그하면 스냅 해제",
                            "Sub", wrap=True))

    def _set_snap(self, v):
        self.canvas.snap = v
        self.canvas.update()

    def _set_window(self, key, value):
        self.design[key] = value
        self._apply_window()
        self._schedule_commit()

    def _item_props(self, lay, it):
        d = it.data
        t = d["type"]
        meta = codegen.TYPES[t]

        def change(key, value):
            if key == "name":
                return
            d[key] = value
            if key in GEOMETRY_KEYS:
                it.sync_geometry()
            else:
                it.rebuild()
            if key == "text":
                self._refresh_layers()
                if d.get("auto_name"):
                    auto_name()
            self._schedule_commit()

        f = self._form(lay, f"{meta['icon']} {meta['name']}")
        name = QLineEdit(d["name"])
        name.setToolTip("블록 코딩에서 이 이름으로 골라요. 글자를 바꾸면 자동으로 지어져요 (직접 바꾸면 고정).")
        name.editingFinished.connect(lambda: self._rename(it, name))
        f.addRow("이름", name)
        self._name_edit = name

        def auto_name():
            new = codegen.name_from_text(t, d.get("text"))
            if new and d.get("auto_name") and new != d["name"] and not new.startswith(d["name"] + "_"):
                new = self._unique(new, exclude=d)
                if new and new != d["name"]:
                    self._apply_rename(it, new)
                    name.setText(new)
        blk_row = QHBoxLayout()
        blk_row.addWidget(button("🧩 클릭하면… (블록)", lambda: self._to_blocks(it, "click"), accent=True,
                                 tip="블록 코딩에 '이 위젯을 클릭했을 때' 블록을 만들어요"))
        if t in ("input", "textbox", "slider", "spin", "checkbox", "radio", "combo", "list"):
            blk_row.addWidget(button("🧩 값이 바뀌면…", lambda: self._to_blocks(it, "change")))
        lay.addLayout(blk_row)
        if "text" in d and t not in ("input", "textbox"):
            self._field(f, d, "text", "글자", "text", change)
        if t in ("input", "textbox"):
            self._field(f, d, "placeholder", "안내 문구", "text", change)
            self._field(f, d, "text", "기본 내용", "text" if t == "input" else "multiline", change)
        if t == "input":
            self._field(f, d, "password", "", "bool", change, caption="비밀번호 칸 (●●●)")
        if t in ("checkbox", "radio"):
            self._field(f, d, "checked", "", "bool", change, caption="처음부터 선택됨")
        if t in ("combo", "list"):
            self._field(f, d, "items", "항목 (쉼표 구분)", "text", change)
        if t in ("slider", "progress", "spin"):
            self._field(f, d, "min", "최솟값", "int", change, lo=-100000, hi=100000)
            self._field(f, d, "max", "최댓값", "int", change, lo=-100000, hi=100000)
            self._field(f, d, "value", "현재값", "int", change, lo=-100000, hi=100000)
        if t == "image":
            self._field(f, d, "path", "이미지 파일", "file", change)
        if t == "label":
            self._field(f, d, "align", "정렬", "choice", change,
                        choices=[("left", "왼쪽"), ("center", "가운데"), ("right", "오른쪽")])

        g = self._form(lay, "📐 위치 & 크기")
        for key, text in [("x", "X"), ("y", "Y"), ("w", "너비"), ("h", "높이")]:
            self._field(g, d, key, text, "int", change, lo=0 if key in "xy" else 8, hi=8000)
        row = QHBoxLayout()
        row.addWidget(button("↔ 가로 가운데", lambda: self._center(it, True)))
        row.addWidget(button("↕ 세로 가운데", lambda: self._center(it, False)))
        lay.addLayout(row)

        s = self._form(lay, "🎨 스타일")
        if "font_size" in d:
            self._field(s, d, "font_size", "글자 크기", "int", change, lo=5, hi=96)
            self._field(s, d, "bold", "", "bool", change, caption="굵게")
        for key, text in [("fg", "글자색" if t not in ("slider",) else "손잡이 색"),
                          ("bg", "배경색" if t not in ("slider",) else "트랙 색"),
                          ("border", "테두리색"), ("accent", "강조색")]:
            if key in d:
                self._field(s, d, key, text, "color", change)
        if "radius" in d:
            self._field(s, d, "radius", "모서리 둥글기", "int", change, lo=0, hi=200)
        self._field(s, d, "tooltip", "툴팁", "text", change)

        if t == "button":
            a = self._form(lay, "⚡ 클릭하면 (블록 없이 간단히)")
            lay.addWidget(label("블록 코딩으로 실행/EXE를 만들면 이 설정 대신 블록이 동작해요.", "Sub", wrap=True))
            self._field(a, d, "action", "동작", "choice",
                        lambda k, v: (change(k, v), QTimer.singleShot(0, self._show_props)),
                        choices=list(codegen.ACTIONS.items()))
            act = d.get("action", "none")
            hint = {"message": "보여줄 메시지", "show_input": "입력칸 변수 이름 (예: input1)", "url": "주소 (https://…)",
                    "run": "명령 (예: notepad.exe)", "code": "파이썬 코드 (self.위젯이름 으로 접근)"}.get(act)
            if hint:
                self._field(a, d, "action_arg", hint, "multiline" if act in ("code", "message") else "text", change,
                            height=120 if act == "code" else 60)

    def _to_blocks(self, it, kind):
        blocks = self.ctx.main.page("blocks")
        self.ctx.main.goto("blocks")
        blocks.add_event_for(it.data["name"], kind)
        self.toast("블록 코딩에 이벤트 블록을 만들었어요. 아래에 할 일을 붙이세요!")

    def _rename(self, it, edit):
        new = edit.text().strip()
        if new == it.data["name"]:
            return
        used = {d["name"] for d in self.design["items"] if d is not it.data}
        if not codegen.valid_name(new) or new in used:
            edit.setText(it.data["name"])
            self.toast("한글/영문/숫자/_ 로 된, 겹치지 않는 이름을 써 주세요 (close, show 같은 예약어 불가)")
            return
        it.data["auto_name"] = False
        self._apply_rename(it, new)
        self.push_history()

    def _center(self, it, horizontal):
        if horizontal:
            it.data["x"] = max(0, (self.canvas.width() - it.data["w"]) // 2)
        else:
            it.data["y"] = max(0, (self.canvas.height() - it.data["h"]) // 2)
        it.sync_geometry()
        self._on_geometry(it)
        self.push_history()

    # ------------------------------------------------ files & output
    def new_design(self):
        if self.design["items"] and QMessageBox.question(self, "새 디자인", "지금 디자인을 지우고 새로 시작할까요?") \
                != QMessageBox.StandardButton.Yes:
            return
        self.file_path = None
        self.load_design(empty_design())
        self.push_history()

    def open_design(self):
        p, _ = QFileDialog.getOpenFileName(self, "디자인 열기", self.ctx.settings["projects_dir"],
                                           "EXE Studio 디자인 (*.esd);;JSON (*.json)")
        if not p:
            return
        try:
            with open(p, encoding="utf-8") as f:
                self.load_design(json.load(f))
            self.file_path = p
            self.push_history()
        except Exception as e:
            QMessageBox.warning(self, "열기 실패", str(e))

    def save_design(self):
        p = self.file_path
        if not p:
            os.makedirs(self.ctx.settings["projects_dir"], exist_ok=True)
            p, _ = QFileDialog.getSaveFileName(self, "디자인 저장",
                                               os.path.join(self.ctx.settings["projects_dir"], "design.esd"),
                                               "EXE Studio 디자인 (*.esd)")
            if not p:
                return False
        with open(p, "w", encoding="utf-8") as f:
            json.dump(self.design, f, ensure_ascii=False, indent=2)
        self.file_path = p
        self.toast("디자인 저장 완료")
        return True

    def code(self):
        return codegen.design_to_code(self.design, self.ctx.design_titlebar())

    def preview(self):
        try:
            ns = {"__name__": "__esd_preview__"}
            exec(compile(self.code(), "<design>", "exec"), ns)
            win = ns["MainWindow"]()
            win.show()
            self._previews = [w for w in self._previews if w.isVisible()] + [win]
        except Exception:
            QMessageBox.critical(self, "미리보기 오류", traceback.format_exc()[-2500:])

    def show_code(self):
        self.ctx.main.page("editor").new_file(self.code())
        self.ctx.main.goto("editor")

    def _ask_py_path(self):
        if self.file_path:
            default = os.path.splitext(self.file_path)[0] + ".py"
        else:
            safe = "".join(ch for ch in self.design["title"] if ch.isalnum() or ch in "-_ ").strip() or "my_app"
            default = os.path.join(self.ctx.settings["projects_dir"], safe, "main.py")
        os.makedirs(os.path.dirname(default), exist_ok=True)
        p, _ = QFileDialog.getSaveFileName(self, ".py로 내보내기", default, "Python (*.py *.pyw)")
        return p

    def export_py(self):
        p = self._ask_py_path()
        if not p:
            return None
        with open(p, "w", encoding="utf-8") as f:
            f.write(self.code())
        self.ctx.settings.add_recent(p)
        self.toast(f"내보내기 완료: {os.path.basename(p)}")
        return p

    def build_exe(self):
        p = self.export_py()
        if not p:
            return
        build = self.ctx.main.page("build")
        build.set_script(p, name=self.design["title"])
        self.ctx.main.goto("build")
