"""Bottom banner that announces a new version, shows its notes and asks whether to update."""
import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QMessageBox, QProgressBar, QTextBrowser,
                               QVBoxLayout)

from . import updater
from .config import APP_VERSION
from .widgets import button, label, run_async


class UpdateBanner(QFrame):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.man = None
        self.setObjectName("UpdateBanner")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 12, 20, 14)
        lay.setSpacing(8)
        head = QHBoxLayout()
        self.title = label("", "H2")
        head.addWidget(self.title)
        head.addStretch(1)
        self.size_label = label("", "Sub")
        head.addWidget(self.size_label)
        lay.addLayout(head)
        self.notes = QTextBrowser()
        self.notes.setOpenExternalLinks(True)
        self.notes.setMinimumHeight(110)
        self.notes.setMaximumHeight(190)
        lay.addWidget(self.notes)
        row = QHBoxLayout()
        row.addWidget(label("지금 업데이트할까요? 받는 동안에도 계속 쓸 수 있고, 끝나면 자동으로 다시 켜져요.", "Sub"))
        row.addStretch(1)
        self.progress = QProgressBar()
        self.progress.setFixedWidth(200)
        self.progress.hide()
        row.addWidget(self.progress)
        self.btn_update = button("⬇ 지금 업데이트", self.start, accent=True)
        self.btn_later = button("나중에", self.hide)
        self.btn_skip = button("이 버전 건너뛰기", self.skip, flat=True)
        for b in (self.btn_update, self.btn_later, self.btn_skip):
            row.addWidget(b)
        lay.addLayout(row)
        self.hide()

    def show_update(self, man):
        self.man = man
        self.title.setText(f"🎉 새 버전 v{man.get('version')} 이(가) 나왔어요  (지금 v{APP_VERSION})")
        size = man.get("size")
        self.size_label.setText(f"{man.get('date', '')}  ·  {size / 1024 / 1024:.0f} MB" if size else man.get("date", ""))
        notes = man.get("notes") or "업데이트 내용이 없어요."
        self.notes.setMarkdown(notes)
        # the document is laid out after this call returns, so scroll back to the top once that has happened
        QTimer.singleShot(0, lambda: self.notes.verticalScrollBar().setValue(0))
        QTimer.singleShot(150, lambda: self.notes.verticalScrollBar().setValue(0))
        self.progress.hide()
        for b in (self.btn_update, self.btn_later, self.btn_skip):
            b.setEnabled(True)
        self.btn_update.setText("⬇ 지금 업데이트")
        self.show()

    def skip(self):
        if self.man:
            self.ctx.settings["skip_version"] = self.man.get("version")
            self.ctx.settings.save()
        self.hide()

    def start(self):
        if not updater.can_self_update():
            QMessageBox.information(self, "개발 모드", "개발 모드(파이썬으로 실행)에서는 자동 교체를 할 수 없어요.\n"
                                                    "EXE로 실행했을 때 업데이트가 적용돼요.")
            return
        for b in (self.btn_update, self.btn_later, self.btn_skip):
            b.setEnabled(False)
        self.btn_update.setText("받는 중…")
        self.progress.show()
        self.progress.setRange(0, 0)
        man = self.man

        def work(progress):
            z = updater.download(man, progress)
            return updater.prepare(z)

        run_async(work, self._ready, self._failed, on_progress=self._progress)

    def _progress(self, p):
        done, total = p
        if total:
            self.progress.setRange(0, 100)
            self.progress.setValue(int(done * 100 / total))

    def _failed(self, err):
        self.progress.hide()
        for b in (self.btn_update, self.btn_later, self.btn_skip):
            b.setEnabled(True)
        self.btn_update.setText("⬇ 다시 시도")
        QMessageBox.warning(self, "업데이트 실패", err.split("\n\n")[0])

    def _ready(self, new_dir):
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        main = self.ctx.main
        if not main.pages["editor"].maybe_save_all():
            self._failed("저장하지 않은 파일이 있어서 업데이트를 미뤘어요.\n\n")
            return
        updater.launch_swap(new_dir)
        main.skip_save_prompt = True
        main.close()
        QApplication.instance().quit()


def check_for_updates(ctx, manual=False):
    """Background check; shows the banner when a newer version exists."""
    source = os.environ.get("EXESTUDIO_UPDATE_SOURCE") or ctx.settings.get("update_source") or updater.default_source()
    if not source:
        if manual:
            QMessageBox.information(ctx.main, "업데이트", "업데이트 주소가 설정돼 있지 않아요.\n설정 → 업데이트에서 지정하세요.")
        return

    def done(result):
        man, newer = result
        if newer and (manual or man.get("version") != ctx.settings.get("skip_version")):
            ctx.main.update_banner.show_update(man)
        elif manual:
            ctx.toast(f"최신 버전이에요 (v{APP_VERSION})")

    def failed(err):
        if manual:
            QMessageBox.warning(ctx.main, "업데이트 확인 실패", err.split("\n\n")[0])

    run_async(lambda: updater.check(source), done, failed)
