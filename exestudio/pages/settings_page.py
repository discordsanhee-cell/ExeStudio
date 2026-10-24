import os

from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout,
                               QHeaderView, QLineEdit, QSpinBox, QTableWidget, QTableWidgetItem)

import sys

from PySide6.QtWidgets import QMessageBox

from .. import pathenv, updater
from ..config import FROZEN
from ..update_ui import check_for_updates

from ..config import APP_NAME, APP_VERSION, BUNDLED_PYTHON, DATA_DIR, install_dir
from ..theme import THEMES
from ..widgets import ColorButton, Page, PathPicker, button, card, label, open_path


class SettingsPage(Page):
    TITLE = "설정"

    def __init__(self, ctx):
        super().__init__(ctx, scroll=True)
        s = ctx.settings

        c, cl = card()
        cl.addWidget(label("🎨 모양", "H2"))
        f = QFormLayout()
        f.setSpacing(8)
        self.theme = QComboBox()
        self.theme.addItems(list(THEMES))
        self.theme.setCurrentText(s["theme"])
        self.theme.currentTextChanged.connect(self._theme)
        f.addRow("테마", self.theme)
        acc_row = QHBoxLayout()
        self.accent = ColorButton(s.get("accent") or ctx.theme["accent"], allow_alpha=False)
        self.accent.colorChanged.connect(self._accent)
        acc_row.addWidget(self.accent)
        acc_row.addWidget(button("테마 기본색", self._accent_reset))
        acc_row.addStretch(1)
        f.addRow("강조색", acc_row)
        self.font = QSpinBox()
        self.font.setRange(8, 16)
        self.font.setValue(int(s.get("font_size", 10)))
        self.font.valueChanged.connect(self._font)
        f.addRow("글자 크기", self.font)
        self.follow = QCheckBox("EXE Studio 타이틀바를 테마에 맞추기")
        self.follow.setChecked(s.get("app_titlebar_mode") == "theme")
        self.follow.toggled.connect(lambda on: ctx.set_app_titlebar(None) if on else ctx.main.goto("titlebar"))
        f.addRow("", self.follow)
        cl.addLayout(f)
        self.root.addWidget(c)

        c2, cl2 = card()
        cl2.addWidget(label("🐍 파이썬 인터프리터", "H2"))
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["종류", "버전", "경로"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setMinimumHeight(170)
        self.table.doubleClicked.connect(self._use_selected)
        cl2.addWidget(self.table)
        row = QHBoxLayout()
        row.addWidget(button("✔ 선택한 것 사용", self._use_selected, accent=True))
        row.addWidget(button("+ python.exe 직접 추가", self._add))
        row.addWidget(button("− 직접 추가한 것 제거", self._remove))
        row.addWidget(button("🔄 다시 찾기", lambda: ctx.refresh_interpreters()))
        row.addStretch(1)
        cl2.addLayout(row)
        self.root.addWidget(c2)

        c3, cl3 = card()
        cl3.addWidget(label("📁 폴더", "H2"))
        f3 = QFormLayout()
        self.projects = PathPicker("dir")
        self.projects.setText(s["projects_dir"])
        self.projects.changed.connect(self._projects)
        f3.addRow("프로젝트 기본 위치", self.projects)
        cl3.addLayout(f3)
        row3 = QHBoxLayout()
        row3.addWidget(button("설정/데이터 폴더 열기", lambda: open_path(DATA_DIR)))
        row3.addWidget(button("프로젝트 폴더 열기", lambda: (os.makedirs(s["projects_dir"], exist_ok=True),
                                                         open_path(s["projects_dir"]))))
        row3.addStretch(1)
        cl3.addLayout(row3)
        self.root.addWidget(c3)

        cp, cpl = card()
        cpl.addWidget(label("🧭 PATH에 추가 (명령 프롬프트에서 바로 쓰기)", "H2"))
        cpl.addWidget(label("내 계정 PATH에만 추가돼요 (관리자 권한 필요 없음). 새로 여는 명령창부터 적용되고, 끄면 깔끔하게 빠져요.",
                            "Sub", wrap=True))
        runtime_dir = BUNDLED_PYTHON.parent
        self.path_items = [
            (QCheckBox("EXE Studio  →  명령창에서 ExeStudio 로 실행"), [install_dir()],
             FROZEN and (install_dir() / "ExeStudio.exe").exists()),
            (QCheckBox("내장 파이썬  →  python, pip, pyinstaller 명령 (이미 깔린 파이썬이 있으면 그쪽이 먼저)"),
             [runtime_dir, runtime_dir / "Scripts"], BUNDLED_PYTHON.exists()),
        ]
        for box, dirs, available in self.path_items:
            box.setEnabled(bool(available) and sys.platform == "win32")
            if not available:
                box.setToolTip("EXE로 실행했을 때만 쓸 수 있어요")
            box.toggled.connect(lambda on, d=dirs: self._set_path(d, on))
            cpl.addWidget(box)
        self.root.addWidget(cp)
        self._refresh_path_boxes()

        cu, cul = card()
        cul.addWidget(label("🔄 업데이트", "H2"))
        fu = QFormLayout()
        fu.setSpacing(8)
        self.up_source = QLineEdit(s.get("update_source", ""))
        self.up_source.setPlaceholderText(f"기본값: {updater.default_source() or '(없음)'}  ·  예) 아이디/저장소 또는 https://…/manifest.json")
        self.up_source.editingFinished.connect(self._save_update_source)
        fu.addRow("받을 곳", self.up_source)
        self.up_auto = QCheckBox("프로그램을 켤 때 업데이트 확인하기")
        self.up_auto.setChecked(s.get("auto_update", True))
        self.up_auto.toggled.connect(lambda on: (s.__setitem__("auto_update", on), s.save()))
        fu.addRow("", self.up_auto)
        cul.addLayout(fu)
        rowu = QHBoxLayout()
        rowu.addWidget(label(f"지금 버전: v{APP_VERSION}", "Sub"))
        rowu.addStretch(1)
        rowu.addWidget(button("🔄 지금 업데이트 확인", lambda: (self._save_update_source(),
                                                          check_for_updates(ctx, manual=True)), accent=True))
        cul.addLayout(rowu)
        self.root.addWidget(cu)

        c4, cl4 = card()
        cl4.addWidget(label(f"ℹ {APP_NAME} {APP_VERSION}", "H2"))
        cl4.addWidget(label(f"내장 파이썬: {BUNDLED_PYTHON if BUNDLED_PYTHON.exists() else '없음 (개발 모드)'}\n"
                            f"데이터 폴더: {DATA_DIR}", "Sub", wrap=True))
        cl4.addWidget(label("© 2026 discordsanhee-cell · CC BY-NC 4.0 (상업적 이용 금지, 수정하면 수정 내용 표시)\n"
                            "EXE Studio로 만든 여러분의 프로그램은 여러분의 것이에요.", "Sub", wrap=True))
        lic_row = QHBoxLayout()
        lic_row.addWidget(button("📜 라이선스 보기", lambda: open_path(install_dir() / "LICENSE.ko.md")
                                 if (install_dir() / "LICENSE.ko.md").exists() else open_path(
                                     "https://github.com/discordsanhee-cell/ExeStudio/blob/main/LICENSE.ko.md")))
        lic_row.addWidget(button("🌐 GitHub", lambda: open_path("https://github.com/discordsanhee-cell/ExeStudio")))
        lic_row.addStretch(1)
        cl4.addLayout(lic_row)
        self.root.addWidget(c4)
        self.root.addStretch(1)
        ctx.interpreters_changed.connect(self._fill)
        ctx.python_changed.connect(lambda *_: self._fill())
        self._fill()

    def _refresh_path_boxes(self):
        if sys.platform != "win32":
            return
        for box, dirs, available in self.path_items:
            box.blockSignals(True)
            box.setChecked(bool(available) and all(pathenv.contains(d) for d in dirs))
            box.blockSignals(False)

    def _set_path(self, dirs, on):
        try:
            if on:
                pathenv.add(dirs)
                self.toast("PATH에 추가했어요. 새로 여는 명령창부터 적용돼요")
            else:
                pathenv.remove(dirs)
                self.toast("PATH에서 뺐어요")
        except OSError as e:
            QMessageBox.warning(self, "PATH 변경 실패", str(e))
        self._refresh_path_boxes()

    def on_show(self):
        self._refresh_path_boxes()

    def _save_update_source(self):
        self.ctx.settings["update_source"] = self.up_source.text().strip()
        self.ctx.settings["skip_version"] = ""
        self.ctx.settings.save()

    def _theme(self, name):
        self.ctx.settings["theme"] = name
        self.ctx.apply_theme()

    def _accent(self, color):
        self.ctx.settings["accent"] = color
        self.ctx.apply_theme()

    def _accent_reset(self):
        self.ctx.settings["accent"] = ""
        self.ctx.apply_theme()
        self.accent.setColor(self.ctx.theme["accent"])

    def _font(self, v):
        self.ctx.settings["font_size"] = v
        self.ctx.apply_theme()

    def _projects(self, p):
        if p:
            self.ctx.settings["projects_dir"] = p
            self.ctx.settings.save()

    def _fill(self):
        cur = self.ctx.python()
        items = self.ctx.interpreters
        self.table.setRowCount(len(items))
        for i, it in enumerate(items):
            mark = "✔ " if it["path"] == cur else ""
            for j, v in enumerate((mark + it["source"], it["version"], it["path"])):
                self.table.setItem(i, j, QTableWidgetItem(v))

    def _selected_path(self):
        rows = {i.row() for i in self.table.selectedIndexes()}
        return self.table.item(min(rows), 2).text() if rows else None

    def _use_selected(self, *_):
        p = self._selected_path()
        if p:
            self.ctx.set_python(p)
            self.toast("사용할 파이썬을 바꿨어요")

    def _add(self):
        p, _ = QFileDialog.getOpenFileName(self, "python.exe 선택", "C:\\", "python.exe (python.exe)")
        if p:
            lst = self.ctx.settings.get("custom_pythons", [])
            lst.append(os.path.normpath(p))
            self.ctx.settings["custom_pythons"] = sorted(set(lst))
            self.ctx.settings.save()
            self.ctx.refresh_interpreters()

    def _remove(self):
        p = self._selected_path()
        lst = self.ctx.settings.get("custom_pythons", [])
        if p in lst:
            lst.remove(p)
            self.ctx.settings.save()
            self.ctx.refresh_interpreters()
