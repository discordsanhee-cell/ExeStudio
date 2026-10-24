import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QLineEdit, QMessageBox,
                               QPushButton, QVBoxLayout)

from ..templates import TEMPLATES
from ..widgets import LogConsole, Page, PathPicker, ProcessRunner, button, card, label, tile


class NewProjectPage(Page):
    TITLE = "새 프로젝트"
    SUBTITLE = "템플릿을 고르면 바로 실행되는 프로젝트를 만들어 줘요. 필요한 패키지도 자동 설치합니다."

    def __init__(self, ctx):
        super().__init__(ctx, scroll=True)
        self.runner = ProcessRunner(self)
        self.selected = TEMPLATES[0]
        self.cards = {}
        grid = QGridLayout()
        grid.setSpacing(12)
        for i, t in enumerate(TEMPLATES):
            b = tile(f"{t['emoji']}   {t['name']}\n{t['desc']}", lambda _=False, tt=t: self.select(tt),
                     checkable=True)
            self.cards[t["id"]] = b
            grid.addWidget(b, i // 3, i % 3)
        self.root.addLayout(grid)

        c, cl = card()
        cl.addWidget(label("프로젝트 정보", "H2"))
        f = QFormLayout()
        f.setSpacing(8)
        self.name = QLineEdit("MyApp")
        f.addRow("프로젝트 이름", self.name)
        self.location = PathPicker("dir")
        self.location.setText(ctx.settings["projects_dir"])
        f.addRow("저장 위치", self.location)
        self.auto_install = QCheckBox("필요한 패키지 자동 설치")
        self.auto_install.setChecked(True)
        f.addRow("", self.auto_install)
        self.open_editor = QCheckBox("만든 뒤 에디터에서 열기")
        self.open_editor.setChecked(True)
        f.addRow("", self.open_editor)
        cl.addLayout(f)
        self.info = label("", "Sub", wrap=True)
        cl.addWidget(self.info)
        row = QHBoxLayout()
        row.addWidget(button("✨ 프로젝트 만들기", self.create, accent=True))
        row.addWidget(button("▶ 만들고 바로 실행", lambda: self.create(run=True)))
        row.addStretch(1)
        cl.addLayout(row)
        self.root.addWidget(c)
        self.log = LogConsole()
        self.log.setMinimumHeight(160)
        self.root.addWidget(self.log)
        self.runner.output.connect(self.log.append_text)
        self.runner.finished.connect(self._installed)
        self._pending_run = None
        self.select(self.selected)

    def select(self, t):
        self.selected = t
        for tid, b in self.cards.items():
            b.setChecked(tid == t["id"])
        reqs = ", ".join(t["reqs"]) or "없음 (파이썬 기본 기능만 사용)"
        extra = " · 콘솔 프로그램이에요 (빌드할 때 '콘솔 창: 표시')" if t.get("console") else ""
        self.info.setText(f"선택: {t['emoji']} {t['name']} — 필요한 패키지: {reqs}{extra}")

    def create(self, run=False):
        t = self.selected
        name = self.name.text().strip() or "MyApp"
        folder_name = "".join(ch for ch in name if ch.isalnum() or ch in "-_ ").strip() or "MyApp"
        folder = Path(self.location.text() or self.ctx.settings["projects_dir"]) / folder_name
        files = t["make"](name, self.ctx.design_titlebar())
        if folder.exists() and any(folder.iterdir()):
            if QMessageBox.question(self, "폴더가 이미 있어요",
                                    f"{folder}\n에 같은 이름의 파일이 있으면 덮어씁니다. 계속할까요?") \
                    != QMessageBox.StandardButton.Yes:
                return
        folder.mkdir(parents=True, exist_ok=True)
        for fname, content in files.items():
            (folder / fname).write_text(content, encoding="utf-8")
        (folder / "requirements.txt").write_text("\n".join(t["reqs"]) + "\n", encoding="utf-8")
        main = folder / "main.py"
        self.ctx.settings.add_recent(str(main))
        self.log.append_text(f"✔ 프로젝트 생성: {folder}\n")
        build = self.ctx.main.page("build")
        build.set_script(str(main), name=name, console=bool(t.get("console")))
        if self.open_editor.isChecked():
            self.ctx.main.page("editor").open_file(main)
        py = self.ctx.python()
        self._pending_run = main if run else None
        if self.auto_install.isChecked() and t["reqs"] and py:
            self.log.append_text("📦 필요한 패키지를 설치합니다…\n")
            self.runner.run([[py, "-m", "pip", "install", *t["reqs"]]], python=py)
        else:
            self._installed(0)

    def _installed(self, code):
        if code == 0:
            self.toast("프로젝트 준비 완료 ✨")
            if self._pending_run is not None:
                editor = self.ctx.main.page("editor")
                editor.open_file(self._pending_run)
                self.ctx.main.goto("editor")
                editor.run()
            elif self.open_editor.isChecked():
                self.ctx.main.goto("editor")
        self._pending_run = None
