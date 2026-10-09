# 개발·배포 안내

## 구성

| 경로 | 역할 |
| --- | --- |
| `sori/app.py` | 트레이·녹음·추론·입력·기록 작업 연결 |
| `sori/audio.py` | Qt 마이크 캡처와 음성 구간·중간 요청 생성 |
| `sori/engine.py` | Qwen Transformers 추론과 장치 선택 |
| `sori/realtime.py` | 추론 대기열과 초안 수정 계산 |
| `sori/hotkeys.py`, `keybindings.py` | 전역 키·누르기 방식·키 이름 |
| `sori/platform_input.py` | 현재 창 확인과 입력 전달 |
| `sori/storage.py` | 설정·SQLite·일별 Markdown/JSONL |
| `sori/ui.py` | 대시보드·플로팅 패널·설정 |
| `tests/` | 모델 다운로드 없는 회귀 검사 |
| `tools/` | 진단·미리보기·Windows 빌드와 패키징 |

## 환경과 검사

Python은 uv가 관리하는 3.12를 사용합니다. 일반 회귀 검사에는 ASR 의존성이 필요하지 않습니다.

```bash
uv sync --locked --managed-python
QT_QPA_PLATFORM=offscreen uv run --no-sync python -m unittest discover -s tests -v
uv run --no-sync python -m compileall -q sori tools tests
bash -n start-unix.sh
```

Windows PowerShell에서 화면 없이 검사하려면 `$env:QT_QPA_PLATFORM = "offscreen"`을 설정하고 같은 `uv run` 명령을 사용합니다. 실제 UI·입력 검사를 실행할 때는 `Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue`로 해제합니다.

음성 인식까지 실행하려면 `uv sync --locked --managed-python --extra asr`로 CPU용 의존성을 준비합니다. NVIDIA용 `asr-cuda`와 동시에 선택할 수 없습니다. 시작 스크립트는 OS별 `.venv-win`·`.venv-linux`·`.venv-macos`를 사용합니다. 직접 uv 명령을 사용할 때에는 `UV_PROJECT_ENVIRONMENT`를 해당 폴더로 설정하거나 기본 `.venv`를 사용합니다.

GitHub Actions의 `Tests` 워크플로우는 Windows·Linux에서 일반 회귀 검사를 수행합니다. 실제 마이크·물리 키·다른 앱과의 호환성·ASR 정확도는 CI 검사 범위에 포함되지 않습니다.

## Windows 실행 파일

Windows에서 저장소 루트의 다음 명령을 실행합니다. 시스템에 uv가 없으면 빌드 스크립트가 프로젝트 폴더에 준비합니다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File build-windows.ps1
```

결과는 `dist\Sori\Sori.exe`와 `_internal` 폴더입니다. 전체 폴더를 함께 배포해야 합니다. Python 런타임은 포함하며 모델은 첫 사용에 사용자 데이터 폴더에 받습니다.

`tools/fix_windows_runtime.py`는 빌드 Python과 일치하는 OpenSSL DLL을 포함합니다. 다른 프로그램이 PATH에 추가한 DLL이 수집되는 문제를 방지하므로 이 단계를 생략하지 않습니다.

Windows 파일 시스템의 별도 폴더에 빌드하려면 먼저 소스 ZIP을 만듭니다.

```powershell
uv run python tools/package_source.py
powershell -NoProfile -ExecutionPolicy Bypass -File tools/build-release.ps1 -Stage "$env:TEMP\Sori-build"
```

기존 스테이징 폴더는 덮어쓰지 않습니다. 새 폴더 이름을 지정하세요. 소스 ZIP에는 다운로드한 uv·가상환경·캐시·모델이 포함되지 않습니다.

## 설치 파일과 휴대용 ZIP

[Inno Setup 공식 다운로드](https://jrsoftware.org/isdl.php)에서 컴파일러를 준비합니다. 임시 폴더에 준비할 때는 서명을 검사하는 `tools/prepare_installer_compiler.ps1 -Installer <공식 설치 파일>`을 사용할 수 있습니다. `tools/sori-setup.iss`가 설치 정의입니다.

```powershell
# 휴대용 ZIP
$env:UV_PROJECT_ENVIRONMENT = ".venv-win"
uv run --no-sync python tools/package_windows.py dist/Sori dist/Sori-Windows-x64.zip

# 설치 파일: 실제 ISCC.exe 위치를 사용하세요.
& "$env:TEMP\Sori-inno-compiler\ISCC.exe" tools/sori-setup.iss
```

결과 파일은 `dist\Sori-Setup-0.2.0.exe`입니다. 버전을 바꿀 때에는 `pyproject.toml`, `sori/__init__.py`, `tools/windows-version.txt`, `tools/sori-setup.iss`, 안내 문구를 함께 갱신하고 `uv lock`을 실행합니다.

## 로컬 배포 검증

`tools/finalize-release.ps1`은 실제 Windows 데스크톱과 마이크가 있는 개발 PC에서 실행합니다. 공개 샘플을 `.test-data/qwen-official-english.wav`에 준비하고, Inno 컴파일러와 빌드 환경을 준비해야 합니다. 샘플 URL과 기존 검증 결과는 [VALIDATION.md](VALIDATION.md)에 있습니다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/finalize-release.ps1
# 별도 스테이징 빌드를 사용한 경우
powershell -NoProfile -ExecutionPolicy Bypass -File tools/finalize-release.ps1 -BuildDirectory "$env:TEMP\Sori-build\Sori"
```

검사는 자체 시험 편집기에만 텍스트를 전달합니다. 검사 중 다른 창으로 포커스가 옮겨지면 입력을 중단합니다. `-LiveAudio`를 추가하면 공개 음성을 실제 속도로 공급하는 긴 입력 검사도 수행합니다. 설치 검사는 별도 임시 폴더에서 실행하며, 기존 Sori 설치 등록이 있으면 덮어쓰지 않고 중단합니다.

대용량 배포 파일은 소스 Git 이력에 추가하지 않고 GitHub Releases 등에 첨부합니다. `docs/release-checks.json`의 수치는 2026-10-09 로컬 검증 자료이며, 다시 빌드한 파일의 해시와 성능을 대신하지 않습니다.
