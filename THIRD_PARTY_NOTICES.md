# 외부 구성 요소 라이선스 (Third-Party Notices)

EXE Studio 자체 코드는 CC BY-NC 4.0이지만, 함께 들어 있는 아래 구성 요소들은 **각자의 원래 라이선스**를 따릅니다.

| 구성 요소 | 용도 | 라이선스 |
|---|---|---|
| [Python](https://www.python.org/) 3.12 (내장 `runtime/`) | 실행·빌드용 파이썬 | PSF License |
| [Qt 6](https://www.qt.io/) / [PySide6](https://doc.qt.io/qtforpython/) | 화면(GUI), 블록 편집기 웹뷰 | LGPL v3 |
| [Blockly](https://github.com/google/blockly) 11.2.1 (`assets/blockly/`) | 블록 코딩 편집기 | Apache License 2.0 (`assets/blockly/LICENSE-blockly.txt`) |
| [PyInstaller](https://pyinstaller.org/) | EXE 빌드 | GPL v2 + bootloader 예외 (만든 EXE에는 제약 없음) |
| [Nuitka](https://nuitka.net/) | EXE 빌드 (선택) | Apache License 2.0 |
| [Pillow](https://python-pillow.org/) | 아이콘 변환 | MIT-CMU (HPND) |
| 내장 runtime의 기타 pip 패키지 (customtkinter, pygame, pywebview, pystray, requests, flask, numpy, pyautogui 등) | 템플릿·예제 | 각 패키지의 라이선스 (`runtime/Lib/site-packages/*/LICENSE*`) |

각 라이선스 원문은 해당 프로젝트 홈페이지 또는 설치된 패키지 폴더에서 확인할 수 있어요.
