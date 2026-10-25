"""screen.png 실시간 뷰어 — 0.5초마다 파일이 바뀌었는지 확인하고 바뀌면 바로 다시 보여줘요.

사용법:  python screen_viewer.py [보여줄 png 경로]
경로를 안 주면 EXE Studio ▶실행 때 캡처가 저장되는 곳의 screen.png를 봐요.

조작: 마우스 휠 = 확대/축소 (마우스 위치 기준) · 드래그 = 이동 · 더블클릭 = 창 맞춤 ↔ 100%
      키보드 + / - = 확대/축소 · 0 = 창 맞춤 · 1 = 원본 크기(100%)
"""
import os
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QImageReader, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QFileDialog, QGraphicsPixmapItem, QGraphicsScene, QGraphicsView,
                               QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget)

DEFAULT = os.path.join(os.environ.get("LOCALAPPDATA", ""), "ExeStudio", "blocks_run", "screen.png")
PIXEL_SHARP_FROM = 3.0  # 300% 넘게 확대하면 픽셀이 뭉개지지 않고 또렷한 네모로 보이게


class ImageView(QGraphicsView):
    def __init__(self, on_zoom):
        super().__init__()
        self.on_zoom = on_zoom
        self.scene_ = QGraphicsScene(self)
        self.setScene(self.scene_)
        self.item = QGraphicsPixmapItem()
        self.item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.scene_.addItem(self.item)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setBackgroundBrush(QColor("#1c1d27"))
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.fit_mode = True

    def set_pixmap(self, pix):
        self.item.setPixmap(pix)
        self.scene_.setSceneRect(self.item.boundingRect())
        if self.fit_mode:
            self.fit()
        else:
            self._update_quality()

    def scale_now(self):
        return self.transform().m11()

    def _update_quality(self):
        sharp = self.scale_now() >= PIXEL_SHARP_FROM
        self.item.setTransformationMode(Qt.TransformationMode.FastTransformation if sharp
                                        else Qt.TransformationMode.SmoothTransformation)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, not sharp)
        self.on_zoom(self.scale_now())

    def fit(self):
        if self.item.pixmap().isNull():
            return
        self.fit_mode = True
        self.resetTransform()
        self.fitInView(self.item, Qt.AspectRatioMode.KeepAspectRatio)
        self._update_quality()

    def set_zoom(self, z, anchor_mouse=False):
        z = max(0.02, min(40.0, z))
        self.fit_mode = False
        if not anchor_mouse:
            self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        factor = z / self.scale_now()
        self.scale(factor, factor)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._update_quality()

    def zoom_by(self, k, anchor_mouse=False):
        self.set_zoom(self.scale_now() * k, anchor_mouse)

    def wheelEvent(self, e):
        steps = e.angleDelta().y() / 120
        if steps:
            self.zoom_by(1.25 ** steps, anchor_mouse=True)

    def mouseDoubleClickEvent(self, e):
        if self.fit_mode:
            self.set_zoom(1.0, anchor_mouse=True)
        else:
            self.fit()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.fit_mode:
            self.fit()


class Viewer(QWidget):
    def __init__(self, path):
        super().__init__()
        self.path, self.stamp = path, None
        self.setWindowTitle("사진 뷰어")
        self.resize(1000, 720)
        self.info = QLabel()
        self.zoom_label = QLabel("맞춤")
        self.zoom_label.setMinimumWidth(70)
        self.view = ImageView(self._zoom_changed)
        bar = QHBoxLayout()
        bar.addWidget(self.info, 1)
        for text, slot in [("－", lambda: self.view.zoom_by(1 / 1.25)), ("＋", lambda: self.view.zoom_by(1.25)),
                           ("창 맞춤", self.view.fit), ("100%", lambda: self.view.set_zoom(1.0)),
                           ("파일 선택", self.choose)]:
            b = QPushButton(text)
            b.clicked.connect(slot)
            bar.addWidget(b)
        bar.insertWidget(1, self.zoom_label)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.addLayout(bar)
        lay.addWidget(self.view, 1)
        self.timer = QTimer(self, interval=500, timeout=self.check)  # 0.5초마다 확인
        self.timer.start()
        self.check()

    def _zoom_changed(self, z):
        self.zoom_label.setText("맞춤 " + f"{z * 100:.0f}%" if self.view.fit_mode else f"{z * 100:.0f}%")

    def keyPressEvent(self, e):
        k = e.key()
        if k in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.view.zoom_by(1.25)
        elif k == Qt.Key.Key_Minus:
            self.view.zoom_by(1 / 1.25)
        elif k == Qt.Key.Key_0:
            self.view.fit()
        elif k == Qt.Key.Key_1:
            self.view.set_zoom(1.0)
        else:
            super().keyPressEvent(e)

    def choose(self):
        p, _ = QFileDialog.getOpenFileName(self, "보여줄 그림", os.path.dirname(self.path),
                                           "그림 (*.png *.jpg *.jpeg *.bmp *.gif *.webp)")
        if p:
            self.path, self.stamp = p, None
            self.view.fit_mode = True
            self.check()

    def check(self):
        try:
            st = os.stat(self.path)
            stamp = (st.st_mtime_ns, st.st_size)
        except OSError:
            self.info.setText(f"파일 없음: {self.path}")
            return
        if stamp == self.stamp:
            return
        reader = QImageReader(self.path)
        reader.setAutoTransform(True)
        img = reader.read()
        if img.isNull():  # 아직 저장 중이면 다음 확인 때 다시 읽기
            return
        self.stamp = stamp
        self.info.setText(f"{self.path}  ·  {img.width()}×{img.height()}")
        self.view.set_pixmap(QPixmap.fromImage(img))  # 원본 해상도 그대로 (줄이거나 압축하지 않음)


if __name__ == "__main__":
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    w = Viewer(sys.argv[1] if len(sys.argv) > 1 else DEFAULT)
    w.show()
    sys.exit(app.exec())
