import json
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame,
                               QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QMessageBox, QPushButton, QScrollArea, QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from .. import codegen
from ..frameless import PRESETS, FramelessWindow, TitleBar, merge_config
from ..widgets import ColorButton, Page, button, card, label

KIND_NAMES = {"close": "닫기  X", "max": "최대화  ㅁ", "min": "최소화  ㅡ", "pin": "항상 위  📌"}
SYMBOL_PICKS = {
    "close": ["✕", "×", "✖", "⨯", "✗", "X", "ⓧ", "⊗", "☒", "💀", "🔥", "[X]"],
    "max": ["□", "☐", "▢", "◻", "⬜", "▣", "⛶", "⤢", "⊞", "○", "◯", "[ ]"],
    "restore": ["❐", "⧉", "◱", "⊡", "▭", "◎", "[=]"],
    "min": ["—", "─", "‒", "_", "▁", "⎯", "⊖", "▾", "⌄", "–", "[_]"],
    "pin": ["📌", "📍", "★", "☆", "◉", "↑", "♥", "⚲", "[^]"],
}
SHAPES = [("rect", "사각형 (윈도우)"), ("rounded", "둥근 사각형"), ("circle", "원형"), ("mac", "맥 스타일 (신호등)")]


class TitleBarPage(Page):
    TITLE = "타이틀바 꾸미기"
    SUBTITLE = "X · ㅁ · ㅡ 버튼의 기호, 색, 모양, 위치, 순서까지 전부 바꿀 수 있어요. 만든 디자인은 새 프로젝트와 GUI 디자이너에 그대로 들어갑니다."

    def __init__(self, ctx):
        super().__init__(ctx)
        self.cfg = ctx.design_titlebar()
        self._loading = False
        self.w = {}
        self._test_windows = []

        body = QHBoxLayout()
        body.setSpacing(16)
        self.root.addLayout(body, 1)

        # ------------------------------------------------ left: controls
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedWidth(440)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        form_host = QWidget()
        form_host.setObjectName("ScrollBody")
        col = QVBoxLayout(form_host)
        col.setContentsMargins(0, 0, 8, 0)
        col.setSpacing(12)
        scroll.setWidget(form_host)
        body.addWidget(scroll)

        c1, l1 = card()
        l1.addWidget(label("프리셋", "H2"))
        self.preset = QComboBox()
        self.preset.addItem("— 프리셋 선택 —")
        self.preset.addItems(list(PRESETS))
        self.preset.activated.connect(self._apply_preset)
        l1.addWidget(self.preset)
        col.addWidget(c1)

        c2, l2 = card()
        l2.addWidget(label("제목 & 아이콘", "H2"))
        f2 = QFormLayout()
        f2.setSpacing(8)
        self.w["title"] = QLineEdit()
        f2.addRow("제목", self.w["title"])
        self.w["title_align"] = QComboBox()
        self.w["title_align"].addItem("왼쪽", "left")
        self.w["title_align"].addItem("가운데", "center")
        f2.addRow("제목 정렬", self.w["title_align"])
        self.w["font_size"] = self._spin(6, 30)
        f2.addRow("글자 크기", self.w["font_size"])
        self.w["bold"] = QCheckBox("굵게")
        f2.addRow("", self.w["bold"])
        self.w["icon_text"] = QLineEdit()
        self.w["icon_text"].setPlaceholderText("비우면 아이콘 없음 (이모지 가능)")
        f2.addRow("아이콘 문자", self.w["icon_text"])
        self.w["icon_color"] = ColorButton()
        f2.addRow("아이콘 색", self.w["icon_color"])
        l2.addLayout(f2)
        col.addWidget(c2)

        c3, l3 = card()
        l3.addWidget(label("바 모양 & 색", "H2"))
        f3 = QFormLayout()
        f3.setSpacing(8)
        self.w["height"] = self._spin(22, 90)
        f3.addRow("높이", self.w["height"])
        self.w["bg"] = ColorButton()
        f3.addRow("배경색", self.w["bg"])
        self.w["bg2"] = ColorButton(allow_none=True)
        self.w["bg2"].setToolTip("그라데이션 끝 색 (우클릭 → 없음)")
        f3.addRow("그라데이션 끝", self.w["bg2"])
        self.w["fg"] = ColorButton()
        f3.addRow("제목 글자색", self.w["fg"])
        self.w["border"] = ColorButton()
        f3.addRow("창 테두리색", self.w["border"])
        self.w["bottom_line"] = QCheckBox("타이틀바 아래 구분선")
        f3.addRow("", self.w["bottom_line"])
        self.w["dbl_click_max"] = QCheckBox("더블클릭하면 최대화")
        f3.addRow("", self.w["dbl_click_max"])
        l3.addLayout(f3)
        col.addWidget(c3)

        c4, l4 = card()
        l4.addWidget(label("버튼 배치", "H2"))
        f4 = QFormLayout()
        f4.setSpacing(8)
        self.w["side"] = QComboBox()
        self.w["side"].addItem("오른쪽 (윈도우)", "right")
        self.w["side"].addItem("왼쪽 (맥)", "left")
        f4.addRow("위치", self.w["side"])
        self.w["shape"] = QComboBox()
        for key, name in SHAPES:
            self.w["shape"].addItem(name, key)
        f4.addRow("모양", self.w["shape"])
        self.w["btn_w"] = self._spin(24, 90)
        f4.addRow("버튼 너비 (사각형)", self.w["btn_w"])
        self.w["btn_size"] = self._spin(8, 60)
        f4.addRow("버튼 크기 (원/둥근)", self.w["btn_size"])
        self.w["symbol_size"] = self._spin(5, 30)
        f4.addRow("기호 크기", self.w["symbol_size"])
        for k, text in [("show_pin", "📌 항상 위 버튼 표시"), ("show_min", "ㅡ 최소화 버튼 표시"),
                        ("show_max", "ㅁ 최대화 버튼 표시")]:
            self.w[k] = QCheckBox(text)
            f4.addRow("", self.w[k])
        l4.addLayout(f4)
        l4.addWidget(label("순서 (드래그해서 바꾸기)", "Sub"))
        self.order = QListWidget()
        self.order.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.order.setFixedHeight(150)
        self.order.model().rowsMoved.connect(lambda *a: self._sync())
        l4.addWidget(self.order)
        col.addWidget(c4)

        c5, l5 = card()
        l5.addWidget(label("버튼별 꾸미기", "H2"))
        self.kind_tabs = QTabWidget()
        for kind in ("close", "max", "min", "pin"):
            self.kind_tabs.addTab(self._kind_tab(kind), KIND_NAMES[kind])
        l5.addWidget(self.kind_tabs)
        col.addWidget(c5)
        col.addStretch(1)

        # ------------------------------------------------ right: preview + actions
        right = QVBoxLayout()
        right.setSpacing(12)
        body.addLayout(right, 1)
        pc, pl = card(margins=18)
        pl.addWidget(label("실시간 미리보기", "H2"))
        pl.addWidget(label("버튼에 마우스를 올려 호버 색을 확인하세요.", "Sub"))
        self.frame = QFrame()
        self.frame.setObjectName("PreviewFrame")
        self.frame.setMinimumHeight(260)
        fl = QVBoxLayout(self.frame)
        fl.setContentsMargins(1, 1, 1, 1)
        fl.setSpacing(0)
        self.preview = TitleBar(self.frame, self.cfg, preview=True)
        fl.addWidget(self.preview)
        self.preview_body = QLabel("여기가 앱 내용 영역이에요 ✨")
        self.preview_body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fl.addWidget(self.preview_body, 1)
        pl.addWidget(self.frame, 1)
        right.addWidget(pc, 1)

        ac, al = card()
        al.addWidget(label("적용 & 내보내기", "H2"))
        grid = QGridLayout()
        grid.setSpacing(8)
        acts = [
            ("🧪 실제 창으로 테스트", self.test_window, True),
            ("💾 새 프로젝트·디자이너에 사용", self.save_design, True),
            ("🎨 EXE Studio 자체에 적용", self.apply_to_app, False),
            ("↺ EXE Studio 테마 기본값", self.reset_app, False),
            ("📤 예제 앱 코드 내보내기 (.py)", self.export_code, False),
            ("📝 예제 앱을 에디터에서 열기", self.open_in_editor, False),
            ("📁 디자인 저장 (.json)", self.save_json, False),
            ("📂 디자인 불러오기", self.load_json, False),
        ]
        for i, (text, slot, acc) in enumerate(acts):
            grid.addWidget(button(text, slot, accent=acc), i // 2, i % 2)
        al.addLayout(grid)
        right.addWidget(ac)

        self._connect_all()
        self._load_to_form(self.cfg)

    # ------------------------------------------------ builders
    def _spin(self, lo, hi):
        s = QSpinBox()
        s.setRange(lo, hi)
        return s

    def _kind_tab(self, kind):
        w = QWidget()
        f = QFormLayout(w)
        f.setContentsMargins(10, 12, 10, 10)
        f.setSpacing(8)
        keys = [kind] + (["restore"] if kind == "max" else [])
        for sk in keys:
            edit = QLineEdit()
            edit.setMaxLength(6)
            self.w[f"sym_{sk}"] = edit
            f.addRow("기호" if sk != "restore" else "복원 기호", edit)
            picks = QGridLayout()
            picks.setSpacing(3)
            for i, sym in enumerate(SYMBOL_PICKS[sk]):
                b = QPushButton(sym)
                b.setFixedSize(34, 28)
                b.setStyleSheet("padding:0; font-size:11pt;")
                b.clicked.connect(lambda _=False, e=edit, s=sym: e.setText(s))
                picks.addWidget(b, i // 6, i % 6)
            picks.setColumnStretch(6, 1)
            f.addRow("", picks)
        for ck, text in [("fg", "기호 색"), ("bg", "배경색"), ("hover_bg", "호버 배경"), ("hover_fg", "호버 기호 색")]:
            cb = ColorButton()
            self.w[f"col_{kind}_{ck}"] = cb
            f.addRow(text, cb)
        return w

    def _connect_all(self):
        for key, w in self.w.items():
            if isinstance(w, ColorButton):
                w.colorChanged.connect(self._sync)
            elif isinstance(w, QLineEdit):
                w.textChanged.connect(self._sync)
            elif isinstance(w, QSpinBox):
                w.valueChanged.connect(self._sync)
            elif isinstance(w, QCheckBox):
                w.toggled.connect(self._sync)
            elif isinstance(w, QComboBox):
                w.currentIndexChanged.connect(self._sync)

    # ------------------------------------------------ form <-> cfg
    def _load_to_form(self, cfg):
        self._loading = True
        c = merge_config(cfg)
        for key in ("title", "icon_text"):
            self.w[key].setText(c[key])
        for key in ("font_size", "height", "btn_w", "btn_size", "symbol_size"):
            self.w[key].setValue(int(c[key]))
        for key in ("bold", "bottom_line", "dbl_click_max", "show_pin", "show_min", "show_max"):
            self.w[key].setChecked(bool(c[key]))
        for key in ("icon_color", "bg", "bg2", "fg", "border"):
            self.w[key].setColor(c[key])
        for key in ("title_align", "side", "shape"):
            i = self.w[key].findData(c[key])
            self.w[key].setCurrentIndex(max(0, i))
        for sk in ("close", "max", "restore", "min", "pin"):
            self.w[f"sym_{sk}"].setText(c["symbols"].get(sk, ""))
        for kind in ("close", "max", "min", "pin"):
            for ck in ("fg", "bg", "hover_bg", "hover_fg"):
                self.w[f"col_{kind}_{ck}"].setColor(c["colors"][kind][ck])
        self.order.clear()
        order = [k for k in c["order"] if k in KIND_NAMES]
        order += [k for k in ("pin", "min", "max", "close") if k not in order]
        for k in order:
            item = QListWidgetItem(KIND_NAMES[k])
            item.setData(Qt.ItemDataRole.UserRole, k)
            self.order.addItem(item)
        self._loading = False
        self.cfg = c
        self._refresh_preview()

    def _sync(self, *_):
        if self._loading:
            return
        c = self.cfg
        for key in ("title", "icon_text"):
            c[key] = self.w[key].text()
        for key in ("font_size", "height", "btn_w", "btn_size", "symbol_size"):
            c[key] = self.w[key].value()
        for key in ("bold", "bottom_line", "dbl_click_max", "show_pin", "show_min", "show_max"):
            c[key] = self.w[key].isChecked()
        for key in ("icon_color", "bg", "bg2", "fg", "border"):
            c[key] = self.w[key].color()
        for key in ("title_align", "side", "shape"):
            c[key] = self.w[key].currentData()
        for sk in ("close", "max", "restore", "min", "pin"):
            c["symbols"][sk] = self.w[f"sym_{sk}"].text()
        for kind in ("close", "max", "min", "pin"):
            for ck in ("fg", "bg", "hover_bg", "hover_fg"):
                c["colors"][kind][ck] = self.w[f"col_{kind}_{ck}"].color()
        c["order"] = [self.order.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.order.count())]
        self._refresh_preview()

    def _refresh_preview(self):
        self.preview.apply(self.cfg)
        light = self.ctx.theme["dark"] is False
        body_bg = "#ffffff" if light else "#14151c"
        self.frame.setStyleSheet(f"QFrame#PreviewFrame {{ border: 1px solid {self.cfg['border']}; "
                                 f"background: {body_bg}; }}")
        self.preview_body.setStyleSheet("color: #8f92ab; font-size: 12pt;")

    def _apply_preset(self, i):
        if i <= 0:
            return
        name = self.preset.itemText(i)
        cfg = merge_config(PRESETS[name])
        cfg["title"] = self.cfg.get("title") or cfg["title"]
        self._load_to_form(cfg)
        self.preset.setCurrentIndex(0)
        self.toast(f"프리셋 '{name}' 적용")

    # ------------------------------------------------ actions
    def test_window(self):
        w = FramelessWindow(self.cfg)
        w.resize(640, 400)
        w.content.setStyleSheet("#FramelessContent { background: %s; }" %
                                ("#ffffff" if not self.ctx.theme["dark"] else "#14151c"))
        lay = QVBoxLayout(w.content)
        msg = QLabel("드래그로 이동 · 가장자리로 크기 조절 · 더블클릭 최대화\n버튼들을 눌러 보세요!")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setStyleSheet("color: #8f92ab; font-size: 12pt;")
        lay.addWidget(msg)
        w.show()
        self._test_windows = [x for x in self._test_windows if x.isVisible()] + [w]

    def save_design(self):
        self.ctx.set_design_titlebar(self.cfg)
        self.toast("저장 완료! 새 프로젝트와 GUI 디자이너가 이 타이틀바를 사용합니다")

    def apply_to_app(self):
        cfg = merge_config(self.cfg)
        cfg["title"] = "EXE Studio"
        self.ctx.set_app_titlebar(cfg)
        self.toast("EXE Studio 타이틀바를 바꿨어요")

    def reset_app(self):
        self.ctx.set_app_titlebar(None)
        self.toast("테마 기본 타이틀바로 되돌렸어요")

    def export_code(self):
        p, _ = QFileDialog.getSaveFileName(self, "코드 내보내기",
                                           os.path.join(self.ctx.settings["projects_dir"], "titlebar_app.py"),
                                           "Python (*.py)")
        if p:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(codegen.titlebar_app_code(self.cfg))
            self.ctx.settings.add_recent(p)
            self.toast("내보내기 완료")

    def open_in_editor(self):
        self.ctx.main.page("editor").new_file(codegen.titlebar_app_code(self.cfg))
        self.ctx.main.goto("editor")

    def save_json(self):
        p, _ = QFileDialog.getSaveFileName(self, "디자인 저장", "titlebar.json", "JSON (*.json)")
        if p:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(self.cfg, f, ensure_ascii=False, indent=2)
            self.toast("저장했어요")

    def load_json(self):
        p, _ = QFileDialog.getOpenFileName(self, "디자인 불러오기", "", "JSON (*.json)")
        if p:
            try:
                with open(p, encoding="utf-8") as f:
                    self._load_to_form(json.load(f))
            except Exception as e:
                QMessageBox.warning(self, "불러오기 실패", str(e))
