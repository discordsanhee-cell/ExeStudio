import io
import os
import re
import shlex
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout, QGridLayout, QHBoxLayout, QLineEdit,
                               QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QProgressBar, QSplitter,
                               QVBoxLayout, QWidget)

from .. import toolchain
from ..widgets import (InterpreterCombo, LogConsole, Page, PathPicker, ProcessRunner, button, card, folder_size,
                       human_size, label, open_path, reveal, run_async)

VERSION_TEMPLATE = """VSVersionInfo(
  ffi=FixedFileInfo(filevers={v}, prodvers={v}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0,
                    date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('041204B0', [
      StringStruct('CompanyName', {company!r}),
      StringStruct('FileDescription', {desc!r}),
      StringStruct('FileVersion', {ver!r}),
      StringStruct('InternalName', {name!r}),
      StringStruct('LegalCopyright', {copyright!r}),
      StringStruct('OriginalFilename', {orig!r}),
      StringStruct('ProductName', {product!r}),
      StringStruct('ProductVersion', {ver!r})])]),
    VarFileInfo([VarStruct('Translation', [0x0412, 1200])])
  ]
)
"""


def version_tuple(text):
    nums = [int(x) for x in re.findall(r"\d+", text or "")][:4]
    return tuple(nums + [0] * (4 - len(nums))) if nums else (1, 0, 0, 0)


def safe_name(text):
    s = "".join(ch for ch in (text or "") if ch.isalnum() or ch in "-_ ").strip()
    return s or "MyApp"


def to_ico(src, dest):
    from PIL import Image
    img = Image.open(src).convert("RGBA")
    side = max(img.size)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(img, ((side - img.width) // 2, (side - img.height) // 2))
    square.save(dest, format="ICO", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    return dest


class BuildPage(Page):
    TITLE = "EXE 빌드"
    SUBTITLE = "파이썬 스크립트를 실행 파일(.exe)로 만듭니다. 필요한 패키지와 빌드 도구는 자동으로 설치돼요."

    def __init__(self, ctx):
        super().__init__(ctx)
        self.runner = ProcessRunner(self)
        self.last_output = None
        self.started_at = 0
        self.after_success = None  # one-shot follow-up, e.g. making a Setup.exe right after the build

        split = QSplitter(Qt.Orientation.Horizontal)
        self.root.addWidget(split, 1)

        # ------------------------------------------------ options (left)
        from PySide6.QtWidgets import QScrollArea
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        host = QWidget()
        host.setObjectName("ScrollBody")
        col = QVBoxLayout(host)
        col.setContentsMargins(0, 0, 10, 0)
        col.setSpacing(12)
        scroll.setWidget(host)
        split.addWidget(scroll)

        c1, l1 = card()
        l1.addWidget(label("📄 기본", "H2"))
        f1 = QFormLayout()
        f1.setSpacing(8)
        self.script = PathPicker("open", "Python (*.py *.pyw)", "빌드할 .py 파일")
        self.script.changed.connect(self._script_changed)
        f1.addRow("스크립트", self.script)
        self.name = QLineEdit()
        self.name.setPlaceholderText("EXE 이름 (확장자 빼고)")
        f1.addRow("앱 이름", self.name)
        icon_row = QHBoxLayout()
        self.icon = PathPicker("open", "아이콘/이미지 (*.ico *.png *.jpg *.jpeg *.bmp *.webp)", "비우면 기본 아이콘")
        icon_row.addWidget(self.icon, 1)
        icon_row.addWidget(button("만들기", lambda: self.ctx.main.goto("icon"), tip="아이콘 만들기 페이지"))
        f1.addRow("아이콘", icon_row)
        self.outdir = PathPicker("dir", "", "비우면 스크립트 폴더\\dist")
        f1.addRow("출력 폴더", self.outdir)
        self.py_combo = InterpreterCombo(ctx)
        f1.addRow("Python", self.py_combo)
        l1.addLayout(f1)
        col.addWidget(c1)

        c2, l2 = card()
        l2.addWidget(label("⚙ 빌드 방식", "H2"))
        f2 = QFormLayout()
        f2.setSpacing(8)
        self.tool = QComboBox()
        self.tool.addItem("PyInstaller (빠르고 호환성 최고)", "pyinstaller")
        self.tool.addItem("Nuitka (C로 컴파일, 더 빠른 실행)", "nuitka")
        f2.addRow("빌드 도구", self.tool)
        self.mode = QComboBox()
        self.mode.addItem("파일 하나 (onefile) — 배포 편함", "onefile")
        self.mode.addItem("폴더 (onedir) — 실행 빠름, 대용량에 추천", "onedir")
        f2.addRow("결과물", self.mode)
        self.console = QComboBox()
        self.console.addItem("숨김 — GUI 프로그램", "hide")
        self.console.addItem("표시 — 콘솔 프로그램", "show")
        f2.addRow("콘솔 창", self.console)
        l2.addLayout(f2)
        grid = QGridLayout()
        self.opt_auto = QCheckBox("필요 패키지 자동 설치")
        self.opt_auto.setChecked(True)
        self.opt_clean = QCheckBox("이전 빌드 캐시 지우기")
        self.opt_clean.setChecked(True)
        self.opt_admin = QCheckBox("관리자 권한으로 실행 (UAC)")
        self.opt_upx = QCheckBox("UPX로 압축 (용량↓)")
        self.opt_open = QCheckBox("완료 후 폴더 열기")
        self.opt_open.setChecked(True)
        self.opt_noconfirm = QCheckBox("Nuitka: 컴파일러 자동 다운로드")
        self.opt_noconfirm.setChecked(True)
        for i, w in enumerate([self.opt_auto, self.opt_clean, self.opt_admin, self.opt_upx, self.opt_open,
                               self.opt_noconfirm]):
            grid.addWidget(w, i // 2, i % 2)
        l2.addLayout(grid)
        col.addWidget(c2)

        c3, l3 = card()
        l3.addWidget(label("🏷 버전 정보 (EXE 속성 > 자세히)", "H2"))
        f3 = QFormLayout()
        f3.setSpacing(8)
        self.v_version = QLineEdit("1.0.0")
        self.v_company = QLineEdit()
        self.v_desc = QLineEdit()
        self.v_product = QLineEdit()
        self.v_copy = QLineEdit()
        for w, t in [(self.v_version, "버전"), (self.v_company, "회사/제작자"), (self.v_desc, "설명"),
                     (self.v_product, "제품 이름"), (self.v_copy, "저작권")]:
            f3.addRow(t, w)
        self.v_enable = QCheckBox("버전 정보 넣기")
        self.v_enable.setChecked(True)
        f3.addRow("", self.v_enable)
        l3.addLayout(f3)
        col.addWidget(c3)

        c4, l4 = card()
        l4.addWidget(label("📦 추가 파일 & 고급", "H2"))
        l4.addWidget(label("EXE에 함께 넣을 파일/폴더 (이미지, 데이터 등)", "Sub"))
        self.data_list = QListWidget()
        self.data_list.setFixedHeight(90)
        l4.addWidget(self.data_list)
        l4.addLayout(self._row(button("+ 파일", self.add_data_file), button("+ 폴더", self.add_data_dir),
                               button("− 제거", self.remove_data)))
        f4 = QFormLayout()
        f4.setSpacing(8)
        self.hidden = QLineEdit()
        self.hidden.setPlaceholderText("쉼표로 구분 (예: pkg.module, other)")
        f4.addRow("숨은 import", self.hidden)
        self.collect = QLineEdit()
        self.collect.setPlaceholderText("통째로 넣을 패키지 (예: customtkinter)")
        f4.addRow("collect-all", self.collect)
        self.exclude = QLineEdit()
        self.exclude.setPlaceholderText("빼서 용량 줄일 모듈 (예: tkinter)")
        f4.addRow("제외 모듈", self.exclude)
        self.splash = PathPicker("open", "이미지 (*.png *.jpg)", "PyInstaller 시작 화면 이미지")
        f4.addRow("스플래시", self.splash)
        self.extra = QLineEdit()
        self.extra.setPlaceholderText("빌드 도구에 그대로 전달할 인자")
        f4.addRow("추가 인자", self.extra)
        l4.addLayout(f4)
        col.addWidget(c4)
        col.addStretch(1)

        # ------------------------------------------------ run & log (right)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(10, 0, 0, 0)
        rl.setSpacing(10)
        act = QHBoxLayout()
        self.build_btn = button("🔨  빌드 시작", self.start_build, accent=True)
        self.build_btn.setMinimumHeight(42)
        self.stop_btn = button("■ 중지", self.runner.kill)
        self.open_btn = button("📁 결과 폴더", self.open_output)
        self.run_btn = button("▶ EXE 실행", self.run_output)
        self.open_btn.setEnabled(False)
        self.run_btn.setEnabled(False)
        for b in (self.build_btn, self.stop_btn, self.open_btn, self.run_btn):
            act.addWidget(b)
        rl.addLayout(act)
        self.status = label("준비됨", "Sub")
        rl.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        rl.addWidget(self.progress)
        rl.addWidget(label("명령 미리보기", "Sub"))
        self.cmd_preview = QPlainTextEdit()
        self.cmd_preview.setReadOnly(True)
        self.cmd_preview.setFixedHeight(80)
        self.cmd_preview.setObjectName("Console")
        rl.addWidget(self.cmd_preview)
        self.log = LogConsole()
        rl.addWidget(self.log, 1)
        split.addWidget(right)
        split.setSizes([520, 600])

        self.runner.output.connect(self.log.append_text)
        self.runner.finished.connect(self._finished)
        for w in (self.name, self.hidden, self.collect, self.exclude, self.extra, self.v_version):
            w.textChanged.connect(self.update_preview)
        for w in (self.tool, self.mode, self.console):
            w.currentIndexChanged.connect(self.update_preview)
        for w in (self.opt_admin, self.opt_upx, self.opt_clean, self.v_enable):
            w.toggled.connect(self.update_preview)
        for w in (self.icon, self.outdir, self.splash):
            w.changed.connect(self.update_preview)
        self.update_preview()

    def _row(self, *ws):
        lay = QHBoxLayout()
        for w in ws:
            lay.addWidget(w)
        lay.addStretch(1)
        return lay

    # ------------------------------------------------ inputs
    def set_script(self, path, name=None, console=None):
        self.script.setText(path)
        if name:
            self.name.setText(safe_name(name))
        if console is not None:
            self.console.setCurrentIndex(1 if console else 0)

    def set_icon(self, path):
        self.icon.setText(path)

    def _script_changed(self, text):
        p = Path(text.strip().strip('"'))
        if p.suffix.lower() in (".py", ".pyw") and not self.name.text().strip():
            stem = p.parent.name if p.stem in ("main", "app", "__main__") else p.stem
            self.name.setText(safe_name(stem))
        if p.suffix.lower() == ".pyw":
            self.console.setCurrentIndex(0)
        self.update_preview()

    def add_data_file(self):
        for p in QFileDialog.getOpenFileNames(self, "함께 넣을 파일")[0]:
            self._add_data(p, ".")

    def add_data_dir(self):
        p = QFileDialog.getExistingDirectory(self, "함께 넣을 폴더")
        if p:
            self._add_data(p, os.path.basename(p))

    def _add_data(self, src, dest):
        item = QListWidgetItem(f"{src}  →  {dest}")
        item.setData(Qt.ItemDataRole.UserRole, (os.path.normpath(src), dest))
        self.data_list.addItem(item)
        self.update_preview()

    def remove_data(self):
        for it in self.data_list.selectedItems():
            self.data_list.takeItem(self.data_list.row(it))
        self.update_preview()

    # ------------------------------------------------ command construction
    def _paths(self):
        script = Path(self.script.text())
        name = safe_name(self.name.text() or script.stem)
        out = Path(self.outdir.text()) if self.outdir.text() else script.parent / "dist"
        work = script.parent / "build" / name
        return script, name, out, work

    def _icon_for_build(self, work):
        icon = self.icon.text()
        if not icon:
            return None
        if icon.lower().endswith(".ico"):
            return icon
        return str(work / "app_icon.ico")

    def _csv(self, edit):
        return [x.strip() for x in edit.text().split(",") if x.strip()]

    def build_command(self, python):
        script, name, out, work = self._paths()
        tool = self.tool.currentData()
        onefile = self.mode.currentData() == "onefile"
        console = self.console.currentData() == "show"
        icon = self._icon_for_build(work)
        data = [self.data_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.data_list.count())]
        if tool == "pyinstaller":
            cmd = [python, "-m", "PyInstaller", "--noconfirm", "--name", name,
                   "--onefile" if onefile else "--onedir", "--console" if console else "--windowed",
                   "--distpath", str(out), "--workpath", str(work), "--specpath", str(work)]
            if self.opt_clean.isChecked():
                cmd.append("--clean")
            if icon:
                cmd += ["--icon", icon]
            if self.opt_admin.isChecked():
                cmd.append("--uac-admin")
            if self.v_enable.isChecked():
                cmd += ["--version-file", str(work / "version_info.txt")]
            if self.opt_upx.isChecked():
                upx = toolchain.find_upx_dir()
                if upx:
                    cmd += ["--upx-dir", upx]
            else:
                cmd.append("--noupx")
            for src, dest in data:
                cmd += ["--add-data", f"{src}{os.pathsep}{dest}"]
            for m in self._csv(self.hidden):
                cmd += ["--hidden-import", m]
            for m in self._csv(self.collect):
                cmd += ["--collect-all", m]
            for m in self._csv(self.exclude):
                cmd += ["--exclude-module", m]
            if self.splash.text():
                cmd += ["--splash", self.splash.text()]
            cmd += self._extra_args()
            cmd.append(str(script))
        else:
            cmd = [python, "-m", "nuitka", "--onefile" if onefile else "--standalone",
                   f"--output-dir={out}", f"--output-filename={name}.exe",
                   f"--windows-console-mode={'force' if console else 'disable'}"]
            if self.opt_noconfirm.isChecked():
                cmd.append("--assume-yes-for-downloads")
            if icon:
                cmd.append(f"--windows-icon-from-ico={icon}")
            if self.opt_admin.isChecked():
                cmd.append("--windows-uac-admin")
            if self.v_enable.isChecked():
                ver = ".".join(map(str, version_tuple(self.v_version.text())))
                cmd += [f"--file-version={ver}", f"--product-version={ver}",
                        f"--product-name={self.v_product.text() or name}",
                        f"--file-description={self.v_desc.text() or name}"]
                if self.v_company.text():
                    cmd.append(f"--company-name={self.v_company.text()}")
                if self.v_copy.text():
                    cmd.append(f"--copyright={self.v_copy.text()}")
            for src, dest in data:
                if os.path.isdir(src):
                    cmd.append(f"--include-data-dir={src}={dest}")
                else:
                    cmd.append(f"--include-data-files={src}={dest}/{os.path.basename(src)}"
                               if dest != "." else f"--include-data-files={src}={os.path.basename(src)}")
            for m in self._csv(self.hidden):
                cmd.append(f"--include-module={m}")
            for m in self._csv(self.collect):
                cmd.append(f"--include-package={m}")
            for m in self._csv(self.exclude):
                cmd.append(f"--nofollow-import-to={m}")
            if self.opt_clean.isChecked():
                cmd.append("--remove-output")
            cmd += self._extra_args()
            cmd.append(str(script))
        return cmd

    def _extra_args(self):
        try:
            return shlex.split(self.extra.text(), posix=False)
        except ValueError:
            return self.extra.text().split()

    def update_preview(self, *_):
        if not self.script.text():
            self.cmd_preview.setPlainText("스크립트를 선택하면 실행될 명령이 여기에 보여요.")
            return
        cmd = self.build_command(self.ctx.python() or "python")
        self.cmd_preview.setPlainText(" ".join(f'"{a}"' if " " in str(a) else str(a) for a in cmd))

    def expected_output(self):
        script, name, out, work = self._paths()
        if self.mode.currentData() == "onefile":
            return out / f"{name}.exe"
        if self.tool.currentData() == "nuitka":
            return out / f"{script.stem}.dist" / f"{name}.exe"
        return out / name / f"{name}.exe"

    # ------------------------------------------------ build flow
    def start_build(self, python=None):
        script = Path(self.script.text())
        if not script.is_file():
            QMessageBox.warning(self, "스크립트 없음", "빌드할 .py 파일을 선택하세요.")
            return
        python = python or self.ctx.python()
        if not python:
            QMessageBox.warning(self, "Python 없음", "파이썬이 없습니다. '도구 설치'에서 먼저 설치하세요.")
            return
        if self.runner.running:
            return
        self.log.clear()
        self._busy(True, "빌드 도구와 필요한 패키지를 확인하는 중…")
        tool = self.tool.currentData()
        auto = self.opt_auto.isChecked()

        def check():
            dist = "pyinstaller" if tool == "pyinstaller" else "nuitka"
            have = toolchain.module_versions(python, [dist]).get(dist)
            missing = []
            if auto:
                missing = toolchain.missing_modules(python, toolchain.scan_imports(script))
            return have, missing

        run_async(check, lambda r: self._run_build(python, tool, *r),
                  lambda err: (self.log.append_text(err), self._busy(False, "확인 실패")))

    def _run_build(self, python, tool, have_tool, missing):
        script, name, out, work = self._paths()
        work.mkdir(parents=True, exist_ok=True)
        steps = []
        installs = []
        if not have_tool:
            installs.append("pyinstaller" if tool == "pyinstaller" else "nuitka")
            self.log.append_text(f"ℹ {installs[0]} 이(가) 없어서 자동으로 설치합니다.\n")
        if missing:
            pkgs = toolchain.pip_names(missing)
            self.log.append_text(f"ℹ 필요한 패키지 자동 설치: {', '.join(pkgs)}\n")
            installs += pkgs
        if tool == "nuitka" and "zstandard" not in installs:
            installs += ["zstandard", "ordered-set"]
        if installs:
            steps.append([python, "-m", "pip", "install", "--upgrade", *installs])

        icon = self.icon.text()
        if icon and not icon.lower().endswith(".ico"):
            dest = work / "app_icon.ico"
            steps.append(lambda: f"🖼 아이콘 변환: {to_ico(icon, dest)}")
        if tool == "pyinstaller" and self.v_enable.isChecked():
            vt = version_tuple(self.v_version.text())
            txt = VERSION_TEMPLATE.format(
                v=vt, ver=".".join(map(str, vt)), name=name, orig=f"{name}.exe",
                company=self.v_company.text(), desc=self.v_desc.text() or name,
                product=self.v_product.text() or name, copyright=self.v_copy.text())
            vf = work / "version_info.txt"
            steps.append(lambda: (vf.write_text(txt, encoding="utf-8"), "🏷 버전 정보 파일 생성")[1])
        steps.append(self.build_command(python))
        self.status.setText("빌드 중… (처음 빌드는 몇 분 걸릴 수 있어요)")
        self.started_at = time.time()
        self.runner.run(steps, cwd=str(script.parent), python=python)

    def _busy(self, on, text):
        self.status.setText(text)
        self.build_btn.setEnabled(not on)
        self.progress.setRange(0, 0 if on else 1)
        self.progress.setValue(0 if on else 1)

    def _finished(self, code):
        elapsed = time.time() - self.started_at
        exe = self.expected_output()
        follow_up, self.after_success = self.after_success, None
        if code == 0 and exe.exists() and follow_up is not None:
            self.opt_open.setChecked(False)
            QTimer.singleShot(0, lambda: follow_up(exe))
        if code == 0 and exe.exists():
            self.last_output = exe
            size = exe.stat().st_size if self.mode.currentData() == "onefile" else folder_size(exe.parent)
            msg = f"✔ 빌드 성공!  {exe.name}  ({human_size(size)}, {elapsed:.0f}초)"
            self._busy(False, msg)
            self.log.append_text(f"\n{msg}\n📁 {exe}\n")
            self.open_btn.setEnabled(True)
            self.run_btn.setEnabled(True)
            self.toast("EXE 빌드 완료 🎉")
            self.ctx.main.page("installer").set_source(exe, self.mode.currentData() == "onedir",
                                                       self.name.text(), self.v_version.text(), self.icon.text())
            if self.opt_open.isChecked():
                reveal(exe)
        elif code == 0:
            self._busy(False, "빌드는 끝났지만 EXE를 찾지 못했어요. 로그를 확인하세요.")
        elif code == -2:
            self._busy(False, "중지됨")
        else:
            self._busy(False, "✖ 빌드 실패 — 아래 로그의 마지막 부분을 확인하세요")

    def open_output(self):
        if self.last_output:
            reveal(self.last_output)

    def run_output(self):
        if self.last_output and self.last_output.exists():
            open_path(self.last_output)
