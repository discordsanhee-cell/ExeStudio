import os
import shutil
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QFileDialog, QFormLayout, QGridLayout, QHBoxLayout,
                               QHeaderView, QLineEdit, QMessageBox, QProgressBar, QPushButton, QSplitter,
                               QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from .. import toolchain
from ..config import MANAGED_PYTHON_DIR
from ..widgets import LogConsole, Page, ProcessRunner, button, card, label, run_async


class ToolsPage(Page):
    TITLE = "도구 설치"
    SUBTITLE = "필요한 프로그램을 이 앱이 직접 다운로드·설치합니다. 파이썬, Git, VS Code, Inno Setup, 컴파일러 등 무엇이든요."

    def __init__(self, ctx):
        super().__init__(ctx)
        self.runner = ProcessRunner(self)
        split = QSplitter(Qt.Orientation.Vertical)
        self.root.addWidget(split, 1)
        tabs = QTabWidget()
        tabs.addTab(self._python_tab(), "🐍 파이썬")
        tabs.addTab(self._winget_tab(), "🧰 프로그램 (winget)")
        tabs.addTab(self._buildtools_tab(), "🔨 빌드 도구")
        tabs.addTab(self._shell_tab(), "⌨ 직접 명령 실행")
        split.addWidget(tabs)
        self.log = LogConsole()
        split.addWidget(self.log)
        split.setSizes([480, 220])
        self.runner.output.connect(self.log.append_text)
        self.runner.finished.connect(self._done)
        self._after = None

    # ------------------------------------------------ python
    def _python_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(12)
        c, cl = card()
        cl.addWidget(label("python.org에서 자동 설치 (관리자 권한 불필요)", "H2"))
        cl.addWidget(label(f"설치 위치: {MANAGED_PYTHON_DIR}\n이미 같은 버전(예: 3.12.x)이 컴퓨터에 깔려 있으면 설치기가 "
                           "그 파이썬을 수정하려 하니, 없는 버전을 입력하는 게 좋아요.", "Sub", wrap=True))
        row = QHBoxLayout()
        self.py_ver = QLineEdit(toolchain.DEFAULT_PYTHON_VERSION)
        self.py_ver.setFixedWidth(120)
        row.addWidget(label("버전"))
        row.addWidget(self.py_ver)
        row.addWidget(button("⬇ 다운로드 & 설치", self.install_python_org, accent=True))
        row.addStretch(1)
        cl.addLayout(row)
        self.dl_bar = QProgressBar()
        self.dl_bar.setValue(0)
        cl.addWidget(self.dl_bar)
        lay.addWidget(c)

        c2, cl2 = card()
        cl2.addWidget(label("다른 방법", "H2"))
        r2 = QHBoxLayout()
        r2.addWidget(button("winget으로 Python 3.12 설치", lambda: self.winget_install("Python.Python.3.12", True)))
        r2.addWidget(button("winget으로 Python 3.13 설치", lambda: self.winget_install("Python.Python.3.13", True)))
        r2.addWidget(button("📂 직접 깐 python.exe 추가", self.add_custom_python))
        r2.addWidget(button("🔄 파이썬 다시 찾기", lambda: self.ctx.refresh_interpreters(
            lambda: self.toast(f"파이썬 {len(self.ctx.interpreters)}개 찾음"))))
        r2.addStretch(1)
        cl2.addLayout(r2)
        lay.addWidget(c2)
        lay.addStretch(1)
        return w

    def install_python_org(self):
        ver = self.py_ver.text().strip()
        if not ver:
            return
        url = toolchain.PYTHON_URL.format(v=ver)
        dest = toolchain.python_installer_path(ver)
        self.log.append_text(f"⬇ 다운로드: {url}\n")

        def prog(t):
            done, total = t
            if total:
                self.dl_bar.setValue(int(done * 100 / total))

        def downloaded(path):
            self.dl_bar.setValue(100)
            self.log.append_text(f"✔ 다운로드 완료 → 설치를 시작합니다 (조용히 설치, 1~3분)\n")
            target = MANAGED_PYTHON_DIR
            py = target / "python.exe"
            self._after = self._python_installed
            self.runner.run([toolchain.python_install_args(path, target),
                             [py, "-m", "pip", "install", "--upgrade", "pip", "pyinstaller", "pillow"]])

        run_async(lambda p: toolchain.download(url, dest, p), downloaded,
                  lambda err: self.log.append_text(f"✖ 다운로드 실패 (버전 번호를 확인하세요)\n{err}\n"),
                  on_progress=prog)

    def _python_installed(self, code):
        if code == 0:
            py = str(MANAGED_PYTHON_DIR / "python.exe")
            self.ctx.refresh_interpreters(lambda: self.ctx.set_python(py))
            self.toast("파이썬 설치 완료! 자동으로 선택했어요")

    def add_custom_python(self):
        p, _ = QFileDialog.getOpenFileName(self, "python.exe 선택", "C:\\", "python.exe (python.exe)")
        if not p:
            return
        lst = self.ctx.settings.get("custom_pythons", [])
        if p not in lst:
            lst.append(os.path.normpath(p))
        self.ctx.settings["custom_pythons"] = lst
        self.ctx.settings.save()
        self.ctx.refresh_interpreters(lambda: self.toast("추가했어요"))

    # ------------------------------------------------ winget
    def _winget_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)
        if not toolchain.has_winget():
            lay.addWidget(label("⚠ winget을 찾을 수 없어요. Microsoft Store에서 '앱 설치 관리자'를 설치/업데이트하세요.",
                                "Bad", wrap=True))
        top = QHBoxLayout()
        self.wg_query = QLineEdit()
        self.wg_query.setPlaceholderText("winget에서 프로그램 검색 (예: obs, discord, blender)")
        self.wg_query.returnPressed.connect(self.winget_search)
        top.addWidget(self.wg_query, 1)
        top.addWidget(button("🔍 검색", self.winget_search))
        self.wg_user = QCheckBox("사용자 범위로 설치")
        top.addWidget(self.wg_user)
        top.addWidget(button("✔ 설치 여부 확인", self.winget_check))
        lay.addLayout(top)
        self.wg_table = QTableWidget(0, 4)
        self.wg_table.setHorizontalHeaderLabels(["이름", "ID", "설명 / 버전", "상태"])
        hh = self.wg_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.wg_table.verticalHeader().setVisible(False)
        self.wg_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.wg_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.wg_table.doubleClicked.connect(lambda idx: self.winget_install_selected())
        lay.addWidget(self.wg_table, 1)
        row = QHBoxLayout()
        row.addWidget(button("⬇ 선택 설치", self.winget_install_selected, accent=True))
        row.addWidget(button("⬆ 선택 업그레이드", lambda: self._winget_selected("upgrade")))
        row.addWidget(button("🗑 선택 제거", lambda: self._winget_selected("uninstall"), danger=True))
        row.addWidget(button("⭐ 추천 목록", self._show_catalog))
        row.addStretch(1)
        self.wg_id = QLineEdit()
        self.wg_id.setPlaceholderText("ID로 바로 설치 (예: OBSProject.OBSStudio)")
        row.addWidget(self.wg_id)
        row.addWidget(button("설치", lambda: self.winget_install(self.wg_id.text().strip())))
        lay.addLayout(row)
        self._show_catalog()
        return w

    def _set_rows(self, rows):
        self.wg_table.setRowCount(len(rows))
        for i, (name, pid, desc) in enumerate(rows):
            for j, val in enumerate((name, pid, desc, "")):
                self.wg_table.setItem(i, j, QTableWidgetItem(val))

    def _show_catalog(self):
        self._set_rows(toolchain.WINGET_CATALOG)

    def winget_search(self):
        q = self.wg_query.text().strip()
        if not q:
            return
        self.log.append_text(f"🔍 winget search {q}\n")

        def search():
            code, out = toolchain.run_capture(["winget", "search", q, "--accept-source-agreements",
                                               "--disable-interactivity"], 90)
            return out

        def done(out):
            rows = toolchain.parse_winget_table(out)
            if not rows:
                self.log.append_text(out + "\n(결과 표를 해석하지 못했어요. 위 출력의 ID를 'ID로 바로 설치'에 넣으세요)\n")
                return
            self._set_rows([(r["name"], r["id"], r["version"]) for r in rows])

        run_async(search, done)

    def winget_check(self):
        ids = [self.wg_table.item(i, 1).text() for i in range(self.wg_table.rowCount())]
        self.log.append_text("✔ 설치된 프로그램 목록을 확인하는 중…\n")

        def check():
            code, out = toolchain.run_capture(["winget", "list", "--accept-source-agreements",
                                               "--disable-interactivity"], 120)
            low = out.lower()
            return {pid: pid.lower() in low for pid in ids}

        def done(res):
            for i in range(self.wg_table.rowCount()):
                pid = self.wg_table.item(i, 1).text()
                self.wg_table.setItem(i, 3, QTableWidgetItem("✔ 설치됨" if res.get(pid) else "—"))

        run_async(check, done)

    def _selected_ids(self):
        rows = sorted({i.row() for i in self.wg_table.selectedIndexes()})
        return [self.wg_table.item(r, 1).text() for r in rows]

    def winget_install_selected(self):
        ids = self._selected_ids()
        if ids:
            self.runner.run([toolchain.winget_install_args(i, self.wg_user.isChecked()) for i in ids])

    def _winget_selected(self, verb):
        ids = self._selected_ids()
        if not ids:
            return
        if verb == "uninstall" and QMessageBox.question(self, "제거", f"{', '.join(ids)} 을(를) 제거할까요?") \
                != QMessageBox.StandardButton.Yes:
            return
        extra = ["--accept-package-agreements"] if verb == "upgrade" else []
        self.runner.run([["winget", verb, "-e", "--id", i, "--silent", "--accept-source-agreements",
                          "--disable-interactivity", *extra] for i in ids])

    def winget_install(self, pid, user_scope=False):
        if not pid:
            return
        if pid.startswith("Python."):
            self._after = lambda code: self.ctx.refresh_interpreters()
        self.runner.run([toolchain.winget_install_args(pid, user_scope or self.wg_user.isChecked())])

    # ------------------------------------------------ build tools
    def _buildtools_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(12)
        lay.addWidget(label("선택한 파이썬에 설치됩니다 (사이드바 아래에서 파이썬 선택).", "Sub"))
        grid = QGridLayout()
        grid.setSpacing(8)
        items = [("PyInstaller", ["pyinstaller", "pyinstaller-hooks-contrib"], "가장 많이 쓰는 EXE 빌더"),
                 ("Nuitka", ["nuitka", "zstandard", "ordered-set"], "C로 컴파일 — 빠르고 소스 보호"),
                 ("cx_Freeze", ["cx_Freeze"], "크로스플랫폼 빌더"),
                 ("auto-py-to-exe", ["auto-py-to-exe"], "PyInstaller용 GUI"),
                 ("Pillow", ["pillow"], "아이콘 변환에 필요"),
                 ("pywin32", ["pywin32"], "윈도우 API")]
        for i, (name, pkgs, desc) in enumerate(items):
            c, cl = card(margins=12, spacing=4)
            cl.addWidget(label(name, "H2"))
            cl.addWidget(label(desc, "Sub", wrap=True))
            cl.addWidget(button("설치 / 업데이트", lambda _=False, p=pkgs: self._pip(p)))
            grid.addWidget(c, i // 3, i % 3)
        lay.addLayout(grid)
        c, cl = card(vertical=False)
        cl.addWidget(label("Inno Setup (Setup.exe 제작) · UPX (EXE 압축) · C 컴파일러 (Nuitka)"))
        cl.addStretch(1)
        cl.addWidget(button("Inno Setup", lambda: self.winget_install("JRSoftware.InnoSetup")))
        cl.addWidget(button("UPX", lambda: self.winget_install("UPX.UPX")))
        cl.addWidget(button("VS Build Tools", lambda: self.winget_install("Microsoft.VisualStudio.2022.BuildTools")))
        lay.addWidget(c)
        lay.addStretch(1)
        return w

    def _pip(self, pkgs):
        py = self.ctx.python()
        if not py:
            QMessageBox.warning(self, "Python 없음", "먼저 '파이썬' 탭에서 파이썬을 설치하세요.")
            return
        self.runner.run([[py, "-m", "pip", "install", "--upgrade", *pkgs]], python=py)

    # ------------------------------------------------ shell
    def _shell_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)
        lay.addWidget(label("직접 설치한 도구도 여기서 바로 실행할 수 있어요. (cmd 명령, 예: git --version, npm i -g electron, "
                            "choco install …)", "Sub", wrap=True))
        row = QHBoxLayout()
        self.shell_cmd = QLineEdit()
        self.shell_cmd.setPlaceholderText("명령 입력 후 Enter")
        self.shell_cmd.returnPressed.connect(self.run_shell)
        row.addWidget(self.shell_cmd, 1)
        row.addWidget(button("▶ 실행", self.run_shell, accent=True))
        row.addWidget(button("■ 중지", self.runner.kill))
        lay.addLayout(row)
        self.shell_cwd = QLineEdit(str(Path.home()))
        f = QFormLayout()
        f.addRow("작업 폴더", self.shell_cwd)
        lay.addLayout(f)
        quick = QHBoxLayout()
        for cmd in ["python --version", "pip list", "git --version", "node -v", "winget --version", "where python"]:
            b = QPushButton(cmd)
            b.clicked.connect(lambda _=False, c=cmd: (self.shell_cmd.setText(c), self.run_shell()))
            quick.addWidget(b)
        quick.addStretch(1)
        lay.addLayout(quick)
        lay.addStretch(1)
        return w

    def run_shell(self):
        cmd = self.shell_cmd.text().strip()
        if not cmd:
            return
        comspec = os.environ.get("COMSPEC", "cmd.exe")
        cwd = self.shell_cwd.text().strip() or None
        self.runner.run([[comspec, "/d", "/s", "/c", f"chcp 65001>nul & {cmd}"]], cwd=cwd)

    def _done(self, code):
        after, self._after = self._after, None
        if after:
            after(code)
        self.toast("완료 ✔" if code == 0 else "작업 실패 — 로그 확인")
