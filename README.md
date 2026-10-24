# EXE Studio

파이썬으로 무엇이든 만들고 EXE로 빌드하는 올인원 스튜디오 (PySide6).
엔트리처럼 블록을 끌어다 프로그램을 만들고, GUI 디자이너로 화면을 꾸미고, 버튼 한 번으로 EXE까지.

## 📥 설치 (다른 PC)

[Releases](https://github.com/discordsanhee-cell/ExeStudio/releases/latest)에서
**`ExeStudio-<버전>-full.zip`** 을 받아 압축을 풀고 `ExeStudio\ExeStudio.exe`를 실행하세요.
파이썬을 따로 설치할 필요가 없어요 (내장 Python 3.12 + PyInstaller, Nuitka, PySide6 등 포함).

설치 후에는 **프로그램을 켤 때 자동으로 업데이트를 확인**하고, 새 버전이 있으면 아래에 업데이트 내용을
보여주며 업데이트할지 물어봐요.

## 기능

| 페이지 | 내용 |
|---|---|
| 🧩 블록 코딩 | 엔트리식 시작·이벤트 블록(시작/키/클릭/값 변경/~초마다/신호), 디자이너 위젯 조종 블록, 질문·대답(빈 칸 자동 채우기), 거북이 무대, 마우스·키보드 자동화 → 바로 EXE |
| ✨ 새 프로젝트 | 템플릿 10종 (커스텀 타이틀바 앱, 대시보드, CustomTkinter, 메모장, CLI, Pygame, pywebview, 트레이, Flask, 매크로) + 패키지 자동 설치 |
| 🎨 GUI 디자이너 | 위젯 14종 드래그&드롭, 한글 자동 이름, 스냅 그리드, 실행 취소, 레이어, 미리보기, `.py` 내보내기, 바로 EXE 빌드 |
| 🪟 타이틀바 꾸미기 | X ㅁ ㅡ 📌 버튼의 기호·색·호버색·모양·위치·순서, 그라데이션, 프리셋 8종 |
| 📝 코드 에디터 | 구문 강조, 줄 번호, 자동 들여쓰기, 주석 토글, 실행(F5) |
| 📦 패키지 관리 | pip 설치/업데이트/삭제, requirements, 인기 패키지 원클릭 |
| 🔨 EXE 빌드 | PyInstaller / Nuitka, onefile/onedir, 아이콘, 버전 정보, UAC, UPX, 필요 패키지 자동 설치 |
| 💿 설치파일 만들기 | Inno Setup으로 Setup.exe 제작 |
| 🖼 아이콘 만들기 | 이모지/글자/이미지로 다중 해상도 `.ico` |
| 🧰 도구 설치 | 파이썬 자동 설치, winget 검색·설치, 빌드 도구, 직접 명령 실행 |
| ⚙ 설정 | 테마 7종, 강조색, 파이썬 관리, 자동 업데이트 |

## 개발 / 빌드

```bat
:: 개발 모드로 실행
.venv\Scripts\python.exe main.py

:: EXE로 빌드 (결과: dist\ExeStudio\ExeStudio.exe, 내장 파이썬 runtime\ 포함)
.venv\Scripts\python.exe build_exe.py

:: 새 버전 배포: exestudio\config.py의 APP_VERSION을 올리고 release_notes.md에 내용을 적은 뒤
.venv\Scripts\python.exe build_exe.py --skip-runtime --full --upload discordsanhee-cell/ExeStudio
```

## 구조

- `exestudio/frameless.py` — 프레임 없는 창 + 커스텀 타이틀바 (생성되는 앱에 그대로 복사됨)
- `exestudio/block_runtime.py` — 블록 프로그램용 이벤트 런타임 (생성되는 앱에 그대로 복사됨)
- `exestudio/codegen.py` — 타이틀바·디자인·블록 → 독립 실행 PySide6 코드
- `exestudio/updater.py`, `update_ui.py` — 자동 업데이트 (GitHub Releases)
- `exestudio/toolchain.py` — 파이썬 탐색, pip, winget, import 스캔
- `exestudio/pages/` — 각 화면
- `assets/blockly/` — 블록 편집기 (Google Blockly 11, Apache-2.0)

## 📜 라이선스

**CC BY-NC 4.0** (크리에이티브 커먼즈 저작자표시-비영리) — [LICENSE](LICENSE) · [한국어 요약](LICENSE.ko.md)

- ✅ 자유롭게 사용·복사·배포·수정할 수 있어요
- 📌 원작자(discordsanhee-cell)와 이 저장소 주소를 밝혀야 하고, **수정했다면 무엇을 고쳤는지** 밝혀야 해요
- 🚫 **상업적 이용 금지** (상업적으로 쓰려면 따로 허락이 필요해요)
- EXE Studio로 **여러분이 만든 프로그램은 여러분의 것**이에요

함께 들어 있는 외부 구성 요소는 각자의 라이선스를 따릅니다 → [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
