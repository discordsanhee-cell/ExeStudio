import io
import os

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFormLayout, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QSlider, QVBoxLayout, QWidget)

from ..config import DATA_DIR
from ..widgets import ColorButton, Page, PathPicker, button, card, label

QUICK = ["🚀", "⚡", "🎮", "📝", "🎵", "📊", "🛠", "💎", "🔥", "🌙", "🐍", "🤖", "★", "A", "EX"]


def render_icon(size, text, fg, bg1, bg2, shape, text_scale, image_path=None):
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing
                     | QPainter.RenderHint.SmoothPixmapTransform)
    rect = QRectF(0, 0, size, size)
    path = QPainterPath()
    if shape == "circle":
        path.addEllipse(rect)
    elif shape == "rounded":
        path.addRoundedRect(rect, size * 0.22, size * 0.22)
    elif shape == "square":
        path.addRect(rect)
    if image_path:
        src = QImage(image_path)
        if not src.isNull():
            if shape != "none":
                p.setClipPath(path)
            scaled = src.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                Qt.TransformationMode.SmoothTransformation)
            p.drawImage(int((size - scaled.width()) / 2), int((size - scaled.height()) / 2), scaled)
    else:
        if shape != "none":
            g = QLinearGradient(0, 0, size, size)
            g.setColorAt(0, QColor(bg1))
            g.setColorAt(1, QColor(bg2 or bg1))
            p.fillPath(path, g)
        if text:
            f = QFont(["Segoe UI Emoji", "Segoe UI", "Malgun Gothic"])
            f.setBold(True)
            f.setPixelSize(max(4, int(size * text_scale / (1 if len(text) <= 1 else 0.6 + 0.4 * len(text)))))
            p.setFont(f)
            p.setPen(QColor(fg))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
    p.end()
    return img


def qimage_to_pil(img):
    from PIL import Image
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return Image.open(io.BytesIO(bytes(buf.data())))


class IconPage(Page):
    TITLE = "아이콘 만들기"
    SUBTITLE = "이모지·글자·이미지로 EXE 아이콘(.ico, 16~256px 전부 포함)을 만듭니다."

    def __init__(self, ctx):
        super().__init__(ctx)
        body = QHBoxLayout()
        body.setSpacing(16)
        self.root.addLayout(body, 1)

        c, cl = card()
        cl.addWidget(label("디자인", "H2"))
        f = QFormLayout()
        f.setSpacing(8)
        self.text = QLineEdit("🚀")
        f.addRow("글자 / 이모지", self.text)
        quick = QGridLayout()
        quick.setSpacing(3)
        for i, q in enumerate(QUICK):
            b = QPushButton(q)
            b.setFixedSize(36, 30)
            b.setStyleSheet("padding:0; font-size:12pt;")
            b.clicked.connect(lambda _=False, t=q: self.text.setText(t))
            quick.addWidget(b, i // 8, i % 8)
        quick.setColumnStretch(8, 1)
        f.addRow("", quick)
        self.image = PathPicker("open", "이미지 (*.png *.jpg *.jpeg *.bmp *.webp *.gif)", "이미지를 쓰려면 선택 (글자 대신)")
        f.addRow("이미지", self.image)
        self.shape = QComboBox()
        for key, name in [("rounded", "둥근 사각형"), ("circle", "원"), ("square", "사각형"), ("none", "배경 없음")]:
            self.shape.addItem(name, key)
        f.addRow("모양", self.shape)
        self.bg1 = ColorButton("#7c6cff", allow_alpha=False)
        self.bg2 = ColorButton("#5ad1ff", allow_alpha=False, allow_none=True)
        self.fg = ColorButton("#ffffff", allow_alpha=False)
        f.addRow("배경색", self.bg1)
        f.addRow("그라데이션", self.bg2)
        f.addRow("글자색", self.fg)
        self.scale = QSlider(Qt.Orientation.Horizontal)
        self.scale.setRange(20, 95)
        self.scale.setValue(60)
        f.addRow("글자 크기", self.scale)
        cl.addLayout(f)
        cl.addStretch(1)
        c.setFixedWidth(460)
        body.addWidget(c)

        pc, pl = card()
        pl.addWidget(label("미리보기", "H2"))
        self.big = QLabel()
        self.big.setFixedSize(256, 256)
        self.big.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pl.addWidget(self.big, 0, Qt.AlignmentFlag.AlignHCenter)
        smalls = QHBoxLayout()
        self.smalls = []
        for s in (16, 24, 32, 48, 64, 128):
            lb = QLabel()
            lb.setFixedSize(s, s)
            self.smalls.append((s, lb))
            smalls.addWidget(lb, 0, Qt.AlignmentFlag.AlignBottom)
        smalls.addStretch(1)
        pl.addLayout(smalls)
        pl.addStretch(1)
        row = QHBoxLayout()
        row.addWidget(button("💾 .ico 저장", self.save_ico, accent=True))
        row.addWidget(button("🖼 .png 저장", self.save_png))
        row.addWidget(button("🔨 EXE 빌드 아이콘으로 사용", self.use_for_build))
        pl.addLayout(row)
        body.addWidget(pc, 1)

        for w in (self.text, ):
            w.textChanged.connect(self.render)
        for w in (self.bg1, self.bg2, self.fg):
            w.colorChanged.connect(self.render)
        self.image.changed.connect(self.render)
        self.shape.currentIndexChanged.connect(self.render)
        self.scale.valueChanged.connect(self.render)
        self.render()

    def image_at(self, size):
        return render_icon(size, self.text.text(), self.fg.color(), self.bg1.color(), self.bg2.color(),
                           self.shape.currentData(), self.scale.value() / 100, self.image.text() or None)

    def render(self, *_):
        self.big.setPixmap(QPixmap.fromImage(self.image_at(256)))
        for s, lb in self.smalls:
            lb.setPixmap(QPixmap.fromImage(self.image_at(s)))

    def _write_ico(self, path):
        img = qimage_to_pil(self.image_at(256))
        img.save(path, format="ICO", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
        return path

    def save_ico(self):
        p, _ = QFileDialog.getSaveFileName(self, "아이콘 저장", "app.ico", "Icon (*.ico)")
        if p:
            self._write_ico(p)
            self.toast("아이콘 저장 완료")

    def save_png(self):
        p, _ = QFileDialog.getSaveFileName(self, "PNG 저장", "icon.png", "PNG (*.png)")
        if p:
            self.image_at(512).save(p, "PNG")
            self.toast("PNG 저장 완료")

    def use_for_build(self):
        os.makedirs(DATA_DIR / "icons", exist_ok=True)
        p = str(DATA_DIR / "icons" / f"icon_{abs(hash((self.text.text(), self.bg1.color(), self.image.text())))}.ico")
        self._write_ico(p)
        self.ctx.main.page("build").set_icon(p)
        self.ctx.main.goto("build")
        self.toast("빌드 아이콘으로 설정했어요")
