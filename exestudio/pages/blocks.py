import json
import os
from pathlib import Path

from PySide6.QtCore import QPoint, QTimer, QUrl, Qt
from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QLineEdit, QMessageBox, QSplitter, QVBoxLayout,
                               QWidget)

from .. import codegen, toolchain
from ..config import BUNDLED_PYTHON, DATA_DIR, resource_dir
from ..widgets import LogConsole, Page, ProcessRunner, button, label
from .editor import CodeEditor

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
except ImportError:  # QtWebEngine missing: page shows a message instead
    QWebEngineView = None

JS_EXAMPLES = ["👋 인사 프로그램", "🎯 숫자 맞히기 게임", "🌟 거북이 별 그리기", "🏃 방향키로 거북이 조종", "🖱 자동 클릭 매크로"]
COUNTER_EXAMPLE = "🔘 클릭 카운터 (GUI 디자이너 연동)"


def _counter_example():
    """A design + blocks pair showing designer widgets driven by click/key/message events."""
    mk = codegen.new_item
    label1 = mk("label", 20, 16, "label1")
    label1.update(text="0", font_size=40, bold=True, align="center", w=380, h=96)
    b1 = mk("button", 40, 128, "button1")
    b1.update(text="+1 클릭 (스페이스)", w=200, h=46)
    b2 = mk("button", 256, 128, "button2")
    b2.update(text="초기화", bg="#3a3c52", w=124, h=46)
    bar = mk("progress", 40, 196, "progress1")
    bar.update(value=0, w=340, h=24)
    design = {"title": "클릭 카운터", "width": 420, "height": 240, "bg": "#14151c", "items": [label1, b1, b2, bar]}

    def text(t):
        return {"block": {"type": "text", "fields": {"TEXT": t}}}

    def num(n):
        return {"block": {"type": "math_number", "fields": {"NUM": n}}}

    count = {"block": {"type": "variables_get", "fields": {"VAR": {"id": "v_c"}}}}

    def chain(blocks):
        for a, b in zip(blocks, blocks[1:]):
            a["next"] = {"block": b}
        return blocks[0]

    def reset():
        return [{"type": "variables_set", "fields": {"VAR": {"id": "v_c"}}, "inputs": {"VALUE": num(0)}},
                {"type": "w_set_text", "fields": {"W": "label1"}, "inputs": {"V": text("0")}},
                {"type": "w_set_value", "fields": {"W": "progress1"}, "inputs": {"V": num(0)}}]

    def hat(kind, x, y, blocks, **fields):
        return {"type": kind, "x": x, "y": y, "fields": fields, "next": {"block": chain(blocks)}}

    blocks = {
        "variables": [{"name": "count", "id": "v_c"}],
        "blocks": {"languageVersion": 0, "blocks": [
            hat("ev_start", 30, 30, reset()),
            hat("ev_click", 30, 230, [{"type": "msg_send", "fields": {"MSG": "더하기"}}], W="button1"),
            hat("ev_key", 30, 330, [{"type": "msg_send", "fields": {"MSG": "더하기"}}], KEY="space"),
            hat("ev_click", 30, 430, reset() + [{"type": "w_color", "fields": {"W": "label1", "WHICH": "color",
                                                                                 "C": "white"}}], W="button2"),
            hat("ev_msg", 470, 30, [
                {"type": "math_change", "fields": {"VAR": {"id": "v_c"}}, "inputs": {"DELTA": num(1)}},
                {"type": "w_set_text", "fields": {"W": "label1"}, "inputs": {"V": count}},
                {"type": "w_set_value", "fields": {"W": "progress1"}, "inputs": {"V": {"block": {
                    "type": "math_arithmetic", "fields": {"OP": "MULTIPLY"},
                    "inputs": {"A": count, "B": num(10)}}}}},
                {"type": "controls_if", "inputs": {
                    "IF0": {"block": {"type": "logic_compare", "fields": {"OP": "GTE"},
                                      "inputs": {"A": count, "B": num(10)}}},
                    "DO0": {"block": chain([
                        {"type": "w_color", "fields": {"W": "label1", "WHICH": "color", "C": "gold"}},
                        {"type": "ui_alert", "inputs": {"TEXT": text("10번 달성! 🎉")}}])}}},
            ], MSG="더하기"),
        ]},
    }
    return design, blocks


class BlocksPage(Page):
    TITLE = "블록 코딩"
    SUBTITLE = ("엔트리처럼 🚩시작·이벤트 블록 아래에 블록을 붙여요. GUI 디자이너에서 만든 버튼·라벨은 🧱화면 요소 블록으로 "
                "조종하고, 버튼 한 번으로 EXE까지!")

    def __init__(self, ctx):
        super().__init__(ctx)
        self.runner = ProcessRunner(self)
        self.logic = ""
        self.loose = 0
        self._last_n = -1
        self._widgets_sent = None
        self.file_path = None
        self.ready = False
        self._pending_js = []

        bar = QHBoxLayout()
        bar.setSpacing(6)
        for text, slot, tip in [("📄", self.new_ws, "새로 만들기"), ("📂", self.open_ws, "블록 파일 열기 (.blk)"),
                                ("💾", self.save_ws, "블록 파일 저장 (디자인 포함)")]:
            b = button(text, slot, tip=tip)
            b.setFixedWidth(40)
            bar.addWidget(b)
        self.examples = QComboBox()
        self.examples.addItem("📚 예제 불러오기…")
        self.examples.addItems([COUNTER_EXAMPLE] + JS_EXAMPLES)
        self.examples.activated.connect(self._example)
        bar.addWidget(self.examples)
        bar.addSpacing(10)
        bar.addWidget(button("▶ 실행", self.run, accent=True))
        bar.addWidget(button("■ 중지", self.runner.kill))
        bar.addWidget(button("🎨 GUI 디자이너", lambda: self.ctx.main.goto("designer"), tip="화면(버튼·라벨) 만들러 가기"))
        bar.addWidget(button("💻 전체 코드", self.to_editor, tip="완성된 프로그램 코드를 에디터에서 보기"))
        bar.addStretch(1)
        self.name = QLineEdit("블록프로그램")
        self.name.setFixedWidth(150)
        self.name.setToolTip("만들 EXE 이름")
        bar.addWidget(label("이름", "Sub"))
        bar.addWidget(self.name)
        bar.addWidget(button("🔨 EXE 만들기", self.build_exe, accent=True))
        self.root.addLayout(bar)

        split = QSplitter(Qt.Orientation.Horizontal)
        self.root.addWidget(split, 1)
        if QWebEngineView is None:
            split.addWidget(label("⚠ 이 PC에서는 블록 편집기(QtWebEngine)를 불러올 수 없어요.", "Bad"))
            self.view = None
        else:
            self.view = QWebEngineView()
            self.view.loadFinished.connect(self._loaded)
            split.addWidget(self.view)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(8, 0, 0, 0)
        self.design_info = label("", "Sub", wrap=True)
        rl.addWidget(self.design_info)
        rl.addWidget(label("블록이 만든 파이썬 코드 (자동)", "Sub"))
        self.preview = CodeEditor(dark=ctx.theme["dark"])
        self.preview.setReadOnly(True)
        rl.addWidget(self.preview, 3)
        rl.addWidget(label("실행 결과", "Sub"))
        self.log = LogConsole()
        rl.addWidget(self.log, 2)
        split.addWidget(right)
        split.setSizes([900, 380])
        split.setStretchFactor(0, 1)

        self.runner.output.connect(self.log.append_text)
        self.runner.finished.connect(lambda c: self.log.append_text("\n✔ 프로그램 종료\n" if c == 0 else ""))
        self.poll = QTimer(self)
        self.poll.setInterval(700)
        self.poll.timeout.connect(self._poll)
        self._loaded_once = False

    # ---- web view plumbing ----------------------------------------------
    def ensure_loaded(self):
        if self.view is not None and not self._loaded_once:
            self._loaded_once = True
            url = QUrl.fromLocalFile(str(resource_dir() / "assets" / "blockly" / "index.html"))
            url.setQuery("dark=1" if self.ctx.theme["dark"] else "dark=0")
            self.view.load(url)

    def on_show(self):
        self.ensure_loaded()
        self.poll.start()
        self._poll()

    def hideEvent(self, e):
        self.poll.stop()
        super().hideEvent(e)

    def _js(self, script, callback=None):
        if self.view is None:
            return
        if not self.ready:
            self.ensure_loaded()
            self._pending_js.append((script, callback))
            return
        if callback:
            self.view.page().runJavaScript(script, 0, callback)
        else:
            self.view.page().runJavaScript(script)

    def _loaded(self, ok):
        self.ready = ok
        if not ok:
            self.log.append_text("✖ 블록 편집기를 불러오지 못했어요.\n")
            return
        self._sync_widgets(force=True)
        pending, self._pending_js = self._pending_js, []
        for script, cb in pending:
            self._js(script, cb)
        self._poll()

    # ---- designer link ---------------------------------------------------
    def design(self):
        return self.ctx.main.page("designer").design

    def _sync_widgets(self, force=False):
        items = self.design().get("items", [])
        widgets = []
        for it in items:
            meta = codegen.TYPES[it["type"]]
            text = (it.get("text") or "").strip().replace("\n", " ")
            lbl = f"{meta['icon']} {it['name']}" + (f" ({text[:12]})" if text else "")
            widgets.append({"name": it["name"], "type": it["type"], "label": lbl})
        if force or widgets != self._widgets_sent:
            self._widgets_sent = widgets
            if self.ready:
                self.view.page().runJavaScript(f"setWidgets({json.dumps(widgets, ensure_ascii=False)})")
        d = self.design()
        if items:
            self.design_info.setText(f"🎨 연결된 화면: '{d.get('title')}' — 위젯 {len(items)}개 "
                                     f"({', '.join(i['name'] for i in items[:6])}{'…' if len(items) > 6 else ''})")
        else:
            self.design_info.setText("🎨 GUI 디자이너에 만든 화면이 없어요. 화면 없이 대화상자·무대만으로도 프로그램이 돼요.")

    def rename_widget(self, old, new):
        """Keep blocks pointing at a widget after it is renamed in the designer."""
        if not self.ready:
            return
        self._sync_widgets(force=True)
        self.view.page().runJavaScript(f"renameWidget({json.dumps(old)}, {json.dumps(new)})")

    def add_event_for(self, widget, kind="click"):
        self._sync_widgets(force=True)
        self._js(f"addEventFor({json.dumps(widget)}, {json.dumps(kind)})")

    # ---- polling / code --------------------------------------------------
    def _poll(self):
        if not self.ready:
            return
        self._sync_widgets()
        self._js("typeof getState === 'function' ? getState() : ''", self._state)

    def _state(self, result):
        if not result:
            return
        state = json.loads(result)
        if state["n"] == self._last_n and self.logic:
            return
        self._last_n = state["n"]
        self.logic = state["code"]
        self.loose = state.get("loose", 0)
        note = ""
        if self.loose:
            note = (f"# ⚠ 시작·이벤트 블록에 붙지 않은 블록 묶음이 {self.loose}개 있어요.\n"
                    "#   '🚩 프로그램이 시작되면' 같은 블록 아래에 붙여야 실행돼요.\n\n")
        bar = self.preview.verticalScrollBar().value()
        self.preview.setPlainText(note + (self.logic or "# 블록을 끌어다 놓으면 여기에 코드가 생겨요\n"))
        self.preview.verticalScrollBar().setValue(bar)

    def full_program(self, logic):
        return codegen.block_program(self.design(), self.ctx.design_titlebar(), logic,
                                     self.name.text().strip() or "블록프로그램")

    def _with_program(self, then):
        if self.view is None:
            return

        def got(result):
            state = json.loads(result) if result else {"code": ""}
            if "@_on(" not in state["code"]:
                QMessageBox.information(self, "시작 블록이 없어요",
                                        "'🚩 시작·이벤트'에서 '프로그램이 시작되면' 같은 블록을 놓고 그 아래에 블록을 붙여 주세요.")
                return
            then(self.full_program(state["code"]))

        self._js("getState()", got)

    # ---- workspace files ------------------------------------------------
    def new_ws(self):
        if QMessageBox.question(self, "새로 만들기", "지금 블록을 모두 지울까요?") == QMessageBox.StandardButton.Yes:
            self.file_path = None
            self._js("clearWs()")

    def _example(self, i):
        name = self.examples.itemText(i)
        self.examples.setCurrentIndex(0)
        if i <= 0:
            return
        designer = self.ctx.main.page("designer")
        if name == COUNTER_EXAMPLE:
            if designer.design.get("items") and QMessageBox.question(
                    self, "디자인 바꾸기", "이 예제는 GUI 디자이너의 화면도 바꿔요. 계속할까요?") != QMessageBox.StandardButton.Yes:
                return
            design, blocks = _counter_example()
            designer.load_design(design)
            designer.push_history()
            self.name.setText("클릭카운터")
            self._sync_widgets(force=True)
            self._js(f"loadWs({json.dumps(blocks, ensure_ascii=False)})")
        else:
            self.name.setText(name.split(" ", 1)[1].replace(" ", ""))
            self._js(f"loadExample({json.dumps(name)})")

    def save_ws(self):
        p = self.file_path
        if not p:
            os.makedirs(self.ctx.settings["projects_dir"], exist_ok=True)
            p, _ = QFileDialog.getSaveFileName(self, "블록 저장",
                                               os.path.join(self.ctx.settings["projects_dir"], f"{self.name.text()}.blk"),
                                               "블록 파일 (*.blk)")
            if not p:
                return

        def write(data):
            bundle = {"format": "esd-blocks-1", "name": self.name.text(), "design": self.design(),
                      "blocks": json.loads(data)}
            Path(p).write_text(json.dumps(bundle, ensure_ascii=False, indent=1), encoding="utf-8")
            self.file_path = p
            self.ctx.settings.add_recent(p)
            self.toast("블록 + 화면 디자인 저장 완료")

        self._js("saveWs()", write)

    def open_ws(self):
        p, _ = QFileDialog.getOpenFileName(self, "블록 열기", self.ctx.settings["projects_dir"], "블록 파일 (*.blk)")
        if p:
            self.load_file(p)

    def load_file(self, p):
        try:
            data = json.loads(Path(p).read_text(encoding="utf-8"))
        except Exception as e:
            QMessageBox.warning(self, "열기 실패", str(e))
            return
        blocks = data
        if isinstance(data, dict) and data.get("format") == "esd-blocks-1":
            blocks = data["blocks"]
            if data.get("design", {}).get("items"):
                designer = self.ctx.main.page("designer")
                designer.load_design(data["design"])
                designer.push_history()
            self.name.setText(data.get("name") or Path(p).stem)
        else:
            self.name.setText(Path(p).stem)
        self.file_path = p
        self._sync_widgets(force=True)
        self._js(f"loadWs({json.dumps(blocks, ensure_ascii=False)})")

    # ---- run / export ---------------------------------------------------
    def run(self):
        self._with_program(self._run_code)

    def _python(self):
        """Block programs need PySide6: the bundled runtime always has it, so prefer that."""
        return str(BUNDLED_PYTHON) if BUNDLED_PYTHON.exists() else self.ctx.python()

    def _run_code(self, code):
        py = self._python()
        if not py:
            QMessageBox.warning(self, "Python 없음", "'도구 설치'에서 파이썬을 먼저 설치하세요.")
            return
        folder = DATA_DIR / "blocks_run"
        folder.mkdir(parents=True, exist_ok=True)
        script = folder / "block_program.py"
        script.write_text(code, encoding="utf-8")
        self.log.clear()
        missing = toolchain.missing_modules(py, toolchain.scan_imports(script))
        steps = []
        if missing:
            self.log.append_text(f"📦 필요한 패키지 설치: {', '.join(missing)}\n")
            steps.append([py, "-m", "pip", "install", *toolchain.pip_names(missing)])
        steps.append([py, "-u", str(script)])
        self.log.append_text("▶ 실행 중… (창을 닫으면 끝나요)\n")
        self.runner.run(steps, cwd=str(folder), python=py)

    def to_editor(self):
        self._with_program(lambda code: (self.ctx.main.page("editor").new_file(code), self.ctx.main.goto("editor")))

    def build_exe(self):
        self._with_program(self._build)

    def _build(self, code):
        name = "".join(ch for ch in self.name.text() if ch.isalnum() or ch in "-_ ").strip() or "블록프로그램"
        folder = Path(self.ctx.settings["projects_dir"]) / name
        folder.mkdir(parents=True, exist_ok=True)
        script = folder / "main.py"
        script.write_text(code, encoding="utf-8")
        blk = folder / f"{name}.blk"
        self._js("saveWs()", lambda data: blk.write_text(json.dumps(
            {"format": "esd-blocks-1", "name": name, "design": self.design(), "blocks": json.loads(data)},
            ensure_ascii=False, indent=1), encoding="utf-8"))
        build = self.ctx.main.page("build")
        build.set_script(str(script), name=name, console=False)
        self.ctx.main.goto("build")
        build.start_build(python=self._python())
