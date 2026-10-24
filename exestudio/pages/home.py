import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QListWidget, QPushButton, QVBoxLayout

from .. import toolchain
from ..config import APP_VERSION, BUNDLED_PYTHON
from ..widgets import Page, button, card, label, run_async, tile

TILES = [
    ("blocks", "🧩", "블록 코딩", "스크래치처럼 블록으로 EXE 만들기"),
    ("templates", "✨", "새 프로젝트", "템플릿 10종으로 바로 시작"),
    ("designer", "🎨", "GUI 디자이너", "끌어다 놓아 화면 만들기"),
    ("titlebar", "🪟", "타이틀바 꾸미기", "X ㅁ ㅡ 버튼 직접 디자인"),
    ("build", "🔨", "EXE 빌드", "PyInstaller / Nuitka"),
    ("installer", "💿", "설치파일 만들기", "Setup.exe 제작"),
    ("packages", "📦", "패키지 관리", "pip 원클릭 설치"),
    ("tools", "🧰", "도구 설치", "파이썬·Git·컴파일러 자동 설치"),
]


class HomePage(Page):
    TITLE = "무엇이든 만들고, EXE로 굽자 🚀"
    SUBTITLE = f"EXE Studio {APP_VERSION} — 예쁜 GUI 디자인부터 타이틀바 커스텀, 패키지 설치, EXE·설치파일 빌드까지 한 곳에서."

    def __init__(self, ctx):
        super().__init__(ctx, scroll=True)
        status_row = QHBoxLayout()
        status_row.setSpacing(12)
        self.status = {}
        for key, title in [("python", "🐍 Python"), ("pyinstaller", "🔨 PyInstaller"), ("nuitka", "⚙ Nuitka"),
                           ("winget", "🧰 winget"), ("inno", "💿 Inno Setup")]:
            c, cl = card(margins=14, spacing=4)
            cl.addWidget(label(title, "Sub"))
            val = label("확인 중…", "H2")
            cl.addWidget(val)
            status_row.addWidget(c)
            self.status[key] = val
        self.root.addLayout(status_row)

        self.root.addWidget(label("바로 가기", "H2"))
        grid = QGridLayout()
        grid.setSpacing(12)
        for i, (key, emoji, name, desc) in enumerate(TILES):
            b = tile(f"{emoji}   {name}\n{desc}", lambda _=False, k=key: self.ctx.main.goto(k))
            grid.addWidget(b, i // 4, i % 4)
        self.root.addLayout(grid)

        bottom = QHBoxLayout()
        bottom.setSpacing(12)
        rc, rl = card()
        rl.addWidget(label("🕘 최근 파일 (더블클릭해서 열기)", "H2"))
        self.recent = QListWidget()
        self.recent.setMinimumHeight(170)
        self.recent.itemDoubleClicked.connect(self._open_recent)
        rl.addWidget(self.recent)
        bottom.addWidget(rc, 3)
        hc, hl = card()
        hl.addWidget(label("💡 이렇게 시작해 보세요", "H2"))
        for t in ["1. '타이틀바 꾸미기'에서 X ㅁ ㅡ 버튼을 마음대로 디자인",
                  "2. 'GUI 디자이너'에서 버튼·입력칸을 끌어다 화면 만들기",
                  "3. '🔨 바로 EXE 빌드' 한 번이면 실행 파일 완성",
                  "4. '설치파일 만들기'로 Setup.exe까지!",
                  "필요한 건 '도구 설치'에서 이 앱이 직접 깔아줘요."]:
            hl.addWidget(label(t, "Sub", wrap=True))
        hl.addStretch(1)
        bottom.addWidget(hc, 2)
        self.root.addLayout(bottom)
        self.root.addStretch(1)
        ctx.interpreters_changed.connect(self.refresh_status)
        ctx.python_changed.connect(lambda *_: self.refresh_status())

    def on_show(self):
        self.recent.clear()
        for p in self.ctx.settings.get("recent_files", []):
            if os.path.exists(p):
                self.recent.addItem(p)
        self.refresh_status()

    def _open_recent(self, item):
        p = item.text()
        if p.lower().endswith(".blk"):
            self.ctx.main.goto("blocks")
            QTimer.singleShot(1500, lambda: self.ctx.main.page("blocks").load_file(p))
        elif p.lower().endswith(".esd"):
            page = self.ctx.main.page("designer")
            import json
            with open(p, encoding="utf-8") as f:
                page.load_design(json.load(f))
            page.file_path = p
            self.ctx.main.goto("designer")
        else:
            self.ctx.main.page("editor").open_file(p)
            self.ctx.main.goto("editor")

    def _set(self, key, ok, text):
        w = self.status[key]
        w.setText(text)
        w.setObjectName("Ok" if ok else "Bad")
        w.style().unpolish(w)
        w.style().polish(w)

    def refresh_status(self):
        py = self.ctx.python()
        info = next((i for i in self.ctx.interpreters if i["path"] == py), None)
        if info:
            self._set("python", True, f"{info['version']} ({info['source']})")
        else:
            self._set("python", False, "없음" if self.ctx.interpreters_loaded else "검색 중…")
        self._set("winget", toolchain.has_winget(), "사용 가능" if toolchain.has_winget() else "없음")
        iscc = toolchain.find_iscc()
        self._set("inno", bool(iscc), "설치됨" if iscc else "미설치")
        if not py:
            return

        def check():
            return toolchain.module_versions(py, ["pyinstaller", "nuitka"])

        def done(v):
            for k in ("pyinstaller", "nuitka"):
                self._set(k, bool(v.get(k)), v.get(k) or "미설치 (자동 설치됨)")

        run_async(check, done)
