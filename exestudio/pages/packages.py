from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QGridLayout, QHBoxLayout, QHeaderView, QLineEdit,
                               QMessageBox, QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from .. import toolchain
from ..widgets import InterpreterCombo, LogConsole, Page, ProcessRunner, button, card, label, run_async


class PackagesPage(Page):
    TITLE = "패키지 관리"
    SUBTITLE = "선택한 파이썬에 pip 패키지를 설치·업데이트·삭제합니다. 인기 패키지는 버튼 한 번으로 설치돼요."

    def __init__(self, ctx):
        super().__init__(ctx)
        self.runner = ProcessRunner(self)
        self.all_rows = []

        top = QHBoxLayout()
        top.addWidget(label("Python:", "Sub"))
        top.addWidget(InterpreterCombo(ctx))
        top.addStretch(1)
        top.addWidget(button("🔄 새로고침", self.refresh))
        top.addWidget(button("⬆ pip 업그레이드", lambda: self._pip(["install", "--upgrade", "pip"])))
        top.addWidget(button("📥 requirements.txt 설치", self.install_reqs))
        top.addWidget(button("📤 requirements.txt 내보내기", self.export_reqs))
        self.root.addLayout(top)

        split = QSplitter(Qt.Orientation.Horizontal)
        self.root.addWidget(split, 1)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.spec = QLineEdit()
        self.spec.setPlaceholderText("설치할 패키지 (예: requests  또는  numpy==2.1  여러 개는 띄어쓰기)")
        self.spec.returnPressed.connect(self.install_spec)
        row.addWidget(self.spec, 1)
        row.addWidget(button("설치", self.install_spec, accent=True))
        ll.addLayout(row)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("🔍 설치된 패키지 검색")
        self.filter.textChanged.connect(self._fill)
        ll.addWidget(self.filter)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["패키지", "버전"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        ll.addWidget(self.table, 1)
        ll.addLayout(self._row(button("⬆ 선택 업데이트", self.upgrade_selected),
                               button("🗑 선택 삭제", self.uninstall_selected, danger=True)))
        self.count = label("", "Sub")
        ll.addWidget(self.count)
        split.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(10, 0, 0, 0)
        c, cl = card()
        cl.addWidget(label("⭐ 인기 패키지 원클릭 설치", "H2"))
        grid = QGridLayout()
        grid.setSpacing(6)
        for i, (pkg, desc) in enumerate(toolchain.PIP_CATALOG):
            b = QPushButton(pkg)
            b.setToolTip(desc)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, p=pkg: self._pip(["install", "--upgrade", p]))
            grid.addWidget(b, i // 4, i % 4)
        cl.addLayout(grid)
        rl.addWidget(c)
        self.log = LogConsole()
        rl.addWidget(self.log, 1)
        split.addWidget(right)
        split.setSizes([480, 620])

        self.runner.output.connect(self.log.append_text)
        self.runner.finished.connect(self._done)
        ctx.python_changed.connect(lambda *_: self.refresh())
        self._loaded = False

    def _row(self, *ws):
        lay = QHBoxLayout()
        for w in ws:
            lay.addWidget(w)
        lay.addStretch(1)
        return lay

    def on_show(self):
        if not self._loaded:
            self.refresh()

    def refresh(self):
        py = self.ctx.python()
        if not py:
            return
        self._loaded = True
        self.count.setText("불러오는 중…")
        run_async(lambda: toolchain.pip_list(py), self._loaded_rows,
                  lambda err: (self.count.setText("목록을 불러오지 못했어요"), self.log.append_text(err)))

    def _loaded_rows(self, rows):
        self.all_rows = sorted(rows, key=lambda r: r["name"].lower())
        self._fill()

    def _fill(self):
        q = self.filter.text().strip().lower()
        rows = [r for r in self.all_rows if q in r["name"].lower()]
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self.table.setItem(i, 0, QTableWidgetItem(r["name"]))
            self.table.setItem(i, 1, QTableWidgetItem(r["version"]))
        self.count.setText(f"설치된 패키지 {len(self.all_rows)}개" + (f" · 검색 결과 {len(rows)}개" if q else ""))

    def _selected(self):
        return sorted({self.table.item(i.row(), 0).text() for i in self.table.selectedIndexes()})

    def _pip(self, args):
        py = self.ctx.python()
        if not py:
            QMessageBox.warning(self, "Python 없음", "먼저 파이썬을 설치하거나 선택하세요.")
            return
        self.runner.run([[py, "-m", "pip", *args]], python=py)

    def install_spec(self):
        pkgs = self.spec.text().split()
        if pkgs:
            self._pip(["install", *pkgs])

    def upgrade_selected(self):
        pkgs = self._selected()
        if pkgs:
            self._pip(["install", "--upgrade", *pkgs])

    def uninstall_selected(self):
        pkgs = self._selected()
        if pkgs and QMessageBox.question(self, "삭제", f"{', '.join(pkgs)} 을(를) 삭제할까요?") \
                == QMessageBox.StandardButton.Yes:
            self._pip(["uninstall", "-y", *pkgs])

    def install_reqs(self):
        p, _ = QFileDialog.getOpenFileName(self, "requirements.txt", "", "Text (*.txt)")
        if p:
            self._pip(["install", "-r", p])

    def export_reqs(self):
        p, _ = QFileDialog.getSaveFileName(self, "requirements.txt 저장", "requirements.txt", "Text (*.txt)")
        if not p:
            return
        py = self.ctx.python()

        def freeze():
            code, out = toolchain.run_capture([py, "-m", "pip", "freeze"], 60, python=py)
            with open(p, "w", encoding="utf-8") as f:
                f.write(out)
            return p

        run_async(freeze, lambda path: self.toast("내보내기 완료"))

    def _done(self, code):
        self.toast("완료 ✔" if code == 0 else "실패 — 로그를 확인하세요")
        self.refresh()
