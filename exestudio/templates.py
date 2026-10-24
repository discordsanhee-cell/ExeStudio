"""Project templates for the "새 프로젝트" page."""
from . import codegen
from .frameless import merge_config


def _pyside_titlebar(name, cfg):
    return {"main.py": codegen.titlebar_app_code(cfg, title=name)}


def _pyside_dashboard(name, cfg):
    cfg = merge_config(cfg)
    cfg["title"] = name
    body = f'''

# ============================== 대시보드 앱 ==============================
from pprint import pformat
from PySide6.QtWidgets import (QFrame, QGridLayout, QListWidget, QProgressBar, QPushButton, QStackedWidget,
                               QTableWidget, QTableWidgetItem)

TITLEBAR_CONFIG = {cfg!r}

STYLE = """
#FramelessContent {{ background: #14151c; }}
QLabel {{ color: #e7e8f0; }}
QLabel#H1 {{ font-size: 20pt; font-weight: 800; }}
QLabel#Num {{ font-size: 24pt; font-weight: 800; color: #7c6cff; }}
QListWidget {{ background: #1c1d27; border: none; color: #c9cbe0; font-size: 11pt; padding: 8px; outline: 0; }}
QListWidget::item {{ padding: 10px; border-radius: 8px; }}
QListWidget::item:selected {{ background: #7c6cff; color: white; }}
QFrame#Card {{ background: #1c1d27; border-radius: 14px; }}
QPushButton {{ background: #7c6cff; color: white; border: none; border-radius: 8px; padding: 8px 16px; }}
QTableWidget {{ background: #1c1d27; color: #e7e8f0; border: none; gridline-color: #2e3044; }}
QHeaderView::section {{ background: #252635; color: #8f92ab; border: none; padding: 6px; }}
QProgressBar {{ background: #252635; border: none; border-radius: 6px; height: 12px; color: white; }}
QProgressBar::chunk {{ background: #7c6cff; border-radius: 6px; }}
"""


def stat_card(title, value):
    card = QFrame()
    card.setObjectName("Card")
    lay = QVBoxLayout(card)
    lay.setContentsMargins(18, 16, 18, 16)
    lay.addWidget(QLabel(title))
    num = QLabel(value)
    num.setObjectName("Num")
    lay.addWidget(num)
    return card


class MainWindow(FramelessWindow):
    def __init__(self):
        super().__init__(TITLEBAR_CONFIG)
        self.resize(1080, 680)
        self.content.setStyleSheet(STYLE)
        row = QHBoxLayout(self.content)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self.menu = QListWidget()
        self.menu.setFixedWidth(200)
        self.menu.addItems(["📊  대시보드", "📋  데이터", "⚙  설정"])
        row.addWidget(self.menu)
        self.pages = QStackedWidget()
        row.addWidget(self.pages, 1)
        self.pages.addWidget(self.dashboard_page())
        self.pages.addWidget(self.table_page())
        self.pages.addWidget(self.settings_page())
        self.menu.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.menu.setCurrentRow(0)

    def dashboard_page(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(28, 24, 28, 24)
        h = QLabel("대시보드")
        h.setObjectName("H1")
        lay.addWidget(h)
        grid = QGridLayout()
        grid.setSpacing(14)
        for i, (t, v) in enumerate([("방문자", "12,480"), ("매출", "₩3.2M"), ("신규 가입", "342"), ("만족도", "97%")]):
            grid.addWidget(stat_card(t, v), 0, i)
        lay.addLayout(grid)
        for t, v in [("목표 달성률", 72), ("서버 사용량", 41)]:
            lay.addWidget(QLabel(t))
            bar = QProgressBar()
            bar.setValue(v)
            lay.addWidget(bar)
        lay.addStretch(1)
        return w

    def table_page(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(28, 24, 28, 24)
        table = QTableWidget(8, 3)
        table.setHorizontalHeaderLabels(["이름", "부서", "점수"])
        for r in range(8):
            for c, val in enumerate([f"사용자 {{r + 1}}", ["개발", "디자인", "영업"][r % 3], str(60 + r * 5)]):
                table.setItem(r, c, QTableWidgetItem(val))
        table.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(table)
        return w

    def settings_page(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.addWidget(QLabel("설정 페이지 — 원하는 옵션을 추가하세요."))
        lay.addStretch(1)
        return w


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
'''
    return {"main.py": codegen.HEADER + codegen.frameless_source() + body}


CTK = '''import customtkinter as ctk

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(__TITLE_LIT__)
        self.geometry("760x520")
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        side = ctk.CTkFrame(self, width=180, corner_radius=0)
        side.grid(row=0, column=0, sticky="nsw")
        ctk.CTkLabel(side, text=__TITLE_LIT__, font=ctk.CTkFont(size=20, weight="bold")).pack(padx=20, pady=(24, 16))
        ctk.CTkButton(side, text="홈", command=lambda: self.tabs.set("홈")).pack(padx=20, pady=6)
        ctk.CTkButton(side, text="도구", command=lambda: self.tabs.set("도구")).pack(padx=20, pady=6)
        self.mode = ctk.CTkOptionMenu(side, values=["dark", "light", "system"], command=ctk.set_appearance_mode)
        self.mode.pack(side="bottom", padx=20, pady=20)

        self.tabs = ctk.CTkTabview(self)
        self.tabs.grid(row=0, column=1, sticky="nsew", padx=16, pady=16)
        home = self.tabs.add("홈")
        tools = self.tabs.add("도구")

        self.entry = ctk.CTkEntry(home, placeholder_text="이름을 입력하세요", width=260)
        self.entry.pack(pady=(30, 10))
        ctk.CTkButton(home, text="인사하기", command=self.hello).pack()
        self.result = ctk.CTkLabel(home, text="", font=ctk.CTkFont(size=16))
        self.result.pack(pady=20)

        self.slider = ctk.CTkSlider(tools, from_=0, to=100, command=self.on_slide)
        self.slider.pack(pady=(30, 10), fill="x", padx=40)
        self.progress = ctk.CTkProgressBar(tools)
        self.progress.pack(fill="x", padx=40)
        self.switch = ctk.CTkSwitch(tools, text="알림 켜기")
        self.switch.pack(pady=20)

    def hello(self):
        self.result.configure(text=f"안녕하세요, {self.entry.get() or '친구'}님! 👋")

    def on_slide(self, value):
        self.progress.set(value / 100)


if __name__ == "__main__":
    App().mainloop()
'''

TK = '''import tkinter as tk
from tkinter import filedialog, messagebox


class Notepad(tk.Tk):
    def __init__(self):
        super().__init__()
        self.path = None
        self.title(__TITLE_LIT__)
        self.geometry("800x560")
        self.text = tk.Text(self, wrap="word", undo=True, font=("Malgun Gothic", 11), bg="#1e1f29", fg="#e6e6e6",
                            insertbackground="white", relief="flat", padx=12, pady=12)
        self.text.pack(fill="both", expand=True)
        menu = tk.Menu(self)
        file = tk.Menu(menu, tearoff=False)
        file.add_command(label="새로 만들기", command=self.new, accelerator="Ctrl+N")
        file.add_command(label="열기…", command=self.open, accelerator="Ctrl+O")
        file.add_command(label="저장", command=self.save, accelerator="Ctrl+S")
        file.add_separator()
        file.add_command(label="종료", command=self.destroy)
        menu.add_cascade(label="파일", menu=file)
        menu.add_command(label="정보", command=lambda: messagebox.showinfo("정보", "EXE Studio로 만든 메모장"))
        self.config(menu=menu)
        self.bind("<Control-n>", lambda e: self.new())
        self.bind("<Control-o>", lambda e: self.open())
        self.bind("<Control-s>", lambda e: self.save())

    def new(self):
        self.text.delete("1.0", "end")
        self.path = None

    def open(self):
        p = filedialog.askopenfilename(filetypes=[("텍스트", "*.txt"), ("모든 파일", "*.*")])
        if p:
            with open(p, encoding="utf-8", errors="replace") as f:
                self.text.delete("1.0", "end")
                self.text.insert("1.0", f.read())
            self.path = p

    def save(self):
        if not self.path:
            self.path = filedialog.asksaveasfilename(defaultextension=".txt")
        if self.path:
            with open(self.path, "w", encoding="utf-8") as f:
                f.write(self.text.get("1.0", "end-1c"))


if __name__ == "__main__":
    Notepad().mainloop()
'''

CLI = '''"""__TITLE__ — 명령줄 도구.  사용법:  __EXE__ --help"""
import argparse
import os
import sys
import time

os.system("")  # 윈도우 콘솔에서 색상(ANSI) 켜기
C = {"g": "\\033[92m", "y": "\\033[93m", "c": "\\033[96m", "r": "\\033[91m", "x": "\\033[0m"}


def cmd_hello(args):
    print(f"{C['g']}안녕하세요, {args.name}님!{C['x']}")


def cmd_count(args):
    for i in range(1, args.n + 1):
        bar = "█" * i + "░" * (args.n - i)
        print(f"\\r{C['c']}{bar}{C['x']} {i}/{args.n}", end="", flush=True)
        time.sleep(0.1)
    print()


def cmd_files(args):
    total = 0
    for root, _, files in os.walk(args.path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    print(f"{C['y']}{args.path}{C['x']} 전체 크기: {total / 1024 / 1024:.2f} MB")


def main():
    p = argparse.ArgumentParser(description="__TITLE__")
    sub = p.add_subparsers(dest="cmd")
    a = sub.add_parser("hello", help="인사하기")
    a.add_argument("name", nargs="?", default="친구")
    a.set_defaults(func=cmd_hello)
    b = sub.add_parser("count", help="진행 바 보여주기")
    b.add_argument("-n", type=int, default=20)
    b.set_defaults(func=cmd_count)
    c = sub.add_parser("size", help="폴더 크기 계산")
    c.add_argument("path", nargs="?", default=".")
    c.set_defaults(func=cmd_files)
    args = p.parse_args()
    if not args.cmd:
        p.print_help()
        if getattr(sys, "frozen", False):
            input("\\n엔터를 누르면 종료합니다…")
        return
    args.func(args)


if __name__ == "__main__":
    main()
'''

PYGAME = '''import random
import sys

import pygame

W, H = 800, 600
pygame.init()
screen = pygame.display.set_mode((W, H))
pygame.display.set_caption(__TITLE_LIT__)
clock = pygame.time.Clock()
font = pygame.font.SysFont("malgungothic", 28, bold=True)

player = pygame.Rect(W // 2 - 25, H - 80, 50, 50)
coins, enemies = [], []
score, lives, tick = 0, 3, 0

while True:
    for e in pygame.event.get():
        if e.type == pygame.QUIT:
            pygame.quit()
            sys.exit()
    keys = pygame.key.get_pressed()
    speed = 7
    if keys[pygame.K_LEFT] or keys[pygame.K_a]:
        player.x -= speed
    if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
        player.x += speed
    player.clamp_ip(screen.get_rect())

    tick += 1
    if tick % 30 == 0:
        coins.append(pygame.Rect(random.randint(0, W - 20), -20, 20, 20))
    if tick % 45 == 0:
        enemies.append(pygame.Rect(random.randint(0, W - 30), -30, 30, 30))
    for c in coins[:]:
        c.y += 5
        if c.colliderect(player):
            coins.remove(c)
            score += 10
        elif c.y > H:
            coins.remove(c)
    for en in enemies[:]:
        en.y += 6 + score // 200
        if en.colliderect(player):
            enemies.remove(en)
            lives -= 1
        elif en.y > H:
            enemies.remove(en)
    if lives <= 0:
        score, lives, coins, enemies = 0, 3, [], []

    screen.fill((20, 21, 28))
    pygame.draw.rect(screen, (124, 108, 255), player, border_radius=10)
    for c in coins:
        pygame.draw.ellipse(screen, (255, 210, 60), c)
    for en in enemies:
        pygame.draw.rect(screen, (230, 70, 80), en, border_radius=6)
    screen.blit(font.render(f"점수 {score}   목숨 {'♥' * lives}", True, (230, 230, 240)), (16, 12))
    pygame.display.flip()
    clock.tick(60)
'''

WEBVIEW = '''import webview

HTML = """
<!doctype html><html><head><meta charset="utf-8">
<style>
  body { margin:0; font-family: 'Segoe UI', 'Malgun Gothic'; background: linear-gradient(135deg,#1e1b4b,#0f172a);
         color:#e2e8f0; height:100vh; display:flex; align-items:center; justify-content:center; }
  .card { background: rgba(255,255,255,.06); padding: 36px 44px; border-radius: 20px; text-align:center;
          box-shadow: 0 20px 60px rgba(0,0,0,.4); }
  h1 { margin: 0 0 8px; } input { padding:10px 14px; border-radius:10px; border:none; width:220px; }
  button { padding:10px 20px; border:none; border-radius:10px; background:#7c6cff; color:white; font-weight:700;
           cursor:pointer; margin-left:6px; }
  #out { margin-top: 18px; font-size: 18px; min-height: 24px; }
</style></head><body>
<div class="card">
  <h1>__TITLE__</h1><p>HTML/CSS/JS로 만든 UI + 파이썬 기능</p>
  <input id="name" placeholder="이름"><button onclick="go()">파이썬 호출</button>
  <div id="out"></div>
</div>
<script>
async function go() {
  const r = await window.pywebview.api.greet(document.getElementById('name').value);
  document.getElementById('out').innerText = r;
}
</script></body></html>
"""


class Api:
    def greet(self, name):
        import platform
        return f"안녕하세요 {name or '친구'}님! (파이썬 {platform.python_version()}에서 응답)"


if __name__ == "__main__":
    webview.create_window(__TITLE_LIT__, html=HTML, js_api=Api(), width=760, height=520)
    webview.start()
'''

TRAY = '''import threading
import time

import pystray
from PIL import Image, ImageDraw


def make_icon():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((4, 4, 60, 60), 14, fill=(124, 108, 255))
    d.text((22, 18), "✓", fill="white")
    return img


running = True


def worker(icon):
    n = 0
    while running:
        time.sleep(60)
        n += 1
        icon.title = f"__TITLE__ — {n}분 실행 중"


def on_hello(icon, item):
    icon.notify("트레이 앱이 잘 동작하고 있어요!", __TITLE_LIT__)


def on_quit(icon, item):
    global running
    running = False
    icon.stop()


icon = pystray.Icon("app", make_icon(), __TITLE_LIT__,
                    menu=pystray.Menu(pystray.MenuItem("알림 보내기", on_hello),
                                      pystray.MenuItem("종료", on_quit)))
threading.Thread(target=worker, args=(icon,), daemon=True).start()
icon.run()
'''

FLASK = '''import threading
import webbrowser

from flask import Flask, jsonify, request

app = Flask(__name__)
NOTES = []

PAGE = """
<!doctype html><meta charset="utf-8"><title>__TITLE__</title>
<style>body{font-family:'Malgun Gothic';max-width:640px;margin:40px auto;background:#f5f6fa}
input{padding:8px;width:70%}button{padding:8px 14px}li{background:white;margin:6px 0;padding:10px;border-radius:8px}</style>
<h1>__TITLE__</h1><input id=t placeholder="메모"><button onclick=add()>추가</button><ul id=l></ul>
<script>
async function load(){const r=await fetch('/api/notes');const d=await r.json();
 l.innerHTML=d.map(x=>'<li>'+x+'</li>').join('')}
async function add(){await fetch('/api/notes',{method:'POST',headers:{'Content-Type':'application/json'},
 body:JSON.stringify({text:t.value})});t.value='';load()}
load()
</script>
"""


@app.get("/")
def index():
    return PAGE


@app.route("/api/notes", methods=["GET", "POST"])
def notes():
    if request.method == "POST":
        NOTES.append(request.json.get("text", ""))
    return jsonify(NOTES)


if __name__ == "__main__":
    threading.Timer(1.0, lambda: webbrowser.open("http://127.0.0.1:5000")).start()
    app.run(port=5000)
'''

MACRO = '''import threading
import time
import tkinter as tk

import keyboard
import pyautogui


class Clicker(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(__TITLE_LIT__)
        self.geometry("340x230")
        self.configure(bg="#1c1d27")
        self.running = False
        tk.Label(self, text="자동 클릭 매크로", fg="white", bg="#1c1d27", font=("Malgun Gothic", 16, "bold")).pack(pady=12)
        row = tk.Frame(self, bg="#1c1d27")
        row.pack()
        tk.Label(row, text="간격(초)", fg="#ccc", bg="#1c1d27").pack(side="left")
        self.interval = tk.DoubleVar(value=0.5)
        tk.Entry(row, textvariable=self.interval, width=6).pack(side="left", padx=6)
        self.status = tk.Label(self, text="F6: 시작/정지", fg="#8f92ab", bg="#1c1d27")
        self.status.pack(pady=10)
        tk.Button(self, text="시작 / 정지 (F6)", command=self.toggle, bg="#7c6cff", fg="white",
                  relief="flat", padx=14, pady=6).pack()
        keyboard.add_hotkey("f6", lambda: self.after(0, self.toggle))

    def toggle(self):
        self.running = not self.running
        self.status.config(text="실행 중…" if self.running else "정지됨", fg="#30a46c" if self.running else "#e5484d")
        if self.running:
            threading.Thread(target=self.loop, daemon=True).start()

    def loop(self):
        while self.running:
            pyautogui.click()
            time.sleep(max(0.01, self.interval.get()))


if __name__ == "__main__":
    Clicker().mainloop()
'''


def _fill(src, name):
    safe = "".join(ch for ch in name if ch not in "\\\"'\r\n")
    exe = "".join(ch for ch in safe if ch.isalnum() or ch in "-_") or "app"
    return (src.replace("__TITLE_LIT__", repr(safe)).replace("__TITLE__", safe)
            .replace("__EXE__", exe + ".exe"))


def _tpl(src):
    return lambda name, cfg: {"main.py": _fill(src, name)}


TEMPLATES = [
    {"id": "pyside_titlebar", "emoji": "🪟", "name": "커스텀 타이틀바 앱 (PySide6)",
     "desc": "타이틀바 꾸미기에서 만든 X ㅁ ㅡ 버튼이 그대로 들어간 예쁜 앱", "reqs": ["PySide6"],
     "make": _pyside_titlebar},
    {"id": "pyside_dashboard", "emoji": "📊", "name": "대시보드 앱 (PySide6)",
     "desc": "사이드 메뉴 + 통계 카드 + 표가 있는 관리 프로그램", "reqs": ["PySide6"], "make": _pyside_dashboard},
    {"id": "ctk", "emoji": "🎛", "name": "모던 앱 (CustomTkinter)",
     "desc": "다크/라이트 모드, 탭, 슬라이더, 스위치가 있는 깔끔한 앱", "reqs": ["customtkinter"], "make": _tpl(CTK)},
    {"id": "tk", "emoji": "📝", "name": "메모장 (Tkinter)",
     "desc": "설치 없이 동작하는 기본 GUI. 열기/저장 메뉴 포함", "reqs": [], "make": _tpl(TK)},
    {"id": "cli", "emoji": "⌨", "name": "콘솔 명령줄 도구",
     "desc": "argparse 서브커맨드 + 색상 출력. 콘솔 EXE로 빌드하세요", "reqs": [], "make": _tpl(CLI), "console": True},
    {"id": "pygame", "emoji": "🎮", "name": "2D 게임 (Pygame)",
     "desc": "코인을 먹고 장애물을 피하는 미니 게임", "reqs": ["pygame"], "make": _tpl(PYGAME)},
    {"id": "webview", "emoji": "🌐", "name": "웹 UI 앱 (pywebview)",
     "desc": "HTML/CSS/JS로 화면을 만들고 파이썬과 통신", "reqs": ["pywebview"], "make": _tpl(WEBVIEW)},
    {"id": "tray", "emoji": "🔔", "name": "시스템 트레이 앱",
     "desc": "작업 표시줄 트레이에 상주하며 알림을 보내는 앱", "reqs": ["pystray", "pillow"], "make": _tpl(TRAY)},
    {"id": "flask", "emoji": "🖥", "name": "로컬 웹 서버 (Flask)",
     "desc": "실행하면 브라우저가 열리는 메모 웹앱", "reqs": ["flask"], "make": _tpl(FLASK), "console": True},
    {"id": "macro", "emoji": "🖱", "name": "자동 클릭 매크로",
     "desc": "F6 단축키로 켜고 끄는 오토 클릭커", "reqs": ["pyautogui", "keyboard"], "make": _tpl(MACRO)},
]
