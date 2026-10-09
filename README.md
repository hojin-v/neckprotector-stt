# Sori · 소리

Windows를 우선으로 만든 로컬 음성 입력 프로그램입니다. 설정 키로 받아쓰기를 시작하면 작은 패널이 나타나고, 현재 입력창·누적 클립보드·시간이 포함된 일별 기록에 텍스트를 남깁니다. Qwen3-ASR-0.6B를 사용하며 API 키가 필요하지 않습니다.

![음성 입력 패널](docs/windows-preview/floating-panel-listening.png)

**현재 버전은 0.2.0입니다. Windows 배포는 CPU용이며 실사용 지연·한국어 정확도 개선이 필요합니다.** GPU를 선택하는 것만으로 CPU 배포본이 GPU를 사용하지는 않습니다. Linux/macOS의 전체 데스크톱 입력 흐름은 아직 검증하지 않았습니다.

## 주요 기능

- 트레이에서 대기하고 녹음 중에만 작은 패널을 표시한 뒤 자동으로 숨깁니다.
- 기본 키는 **CapsLock**입니다. 원하는 단일 키로 바꾸고, 누르기/다시 누르기 또는 길게 누르기를 선택합니다.
- Windows 입력창에 중간 결과를 입력하고 인식이 바뀌면 초안을 수정합니다. 기본 붙여넣기와 직접 입력을 선택할 수 있습니다.
- 창 전환·직접 키 입력·외부 클릭 시 자동 수정을 멈추고 받아쓴 내용은 기록과 클립보드에 보관합니다.
- 오늘 받아쓴 모든 문장을 클립보드에 누적합니다. 일별 Markdown·JSONL과 SQLite에 시간을 포함해 저장합니다.
- 마이크 선택과 음량 테스트, 기록 검색, 언어·저장 폴더 설정을 제공합니다.

## 실행

Windows 설치 파일은 `Sori-Setup-0.2.0.exe`, 휴대용 배포는 `Sori-Windows-x64.zip`입니다. 설치 후에는 **시작 메뉴 → Sori**로 실행합니다. Python·uv의 별도 설치는 필요 없습니다. 휴대용 ZIP은 전체를 풀고 `Sori.exe`와 `_internal` 폴더를 함께 유지합니다.

소스에서 실행하려면 저장소를 내려받은 뒤 Windows에서는 `start-windows.bat`, Linux/macOS에서는 `bash start-unix.sh`를 사용합니다. Windows 시작 스크립트는 uv가 없으면 프로젝트 폴더에 준비합니다. Linux/macOS는 [uv](https://docs.astral.sh/uv/getting-started/installation/)를 먼저 설치합니다. uv가 Python 3.12와 잠금 파일의 패키지를 관리하므로 전역 Python 설치는 필요 없습니다.

```bash
git clone git@github.com:hojin-v/neckprotector-stt.git
cd neckprotector-stt
```

처음에는 모델을 다운로드합니다. 이후에는 캐시를 자동으로 불러옵니다. 입력창에 커서를 놓고 설정 키를 눌러 말한 뒤 다시 눌러 마칩니다. 마이크 권한·키 변경·길게 누르기·GPU 환경·WSL 안내는 [사용 안내](docs/USAGE.md)에 있습니다.

설정·모델·기록은 Windows에서 `%LOCALAPPDATA%\Sori`에 저장합니다. 프로그램 설치 폴더 밖에 있으므로 업데이트와 제거 후에도 유지됩니다.

## 성능과 지원 범위

현재 Windows 중간 입력은 약 0.8초 간격으로 같은 구간을 길이를 늘려가며 반복 인식합니다. 약 0.45초의 쉼 또는 최대 6초에 구간을 확정합니다. Qwen의 vLLM 기반 스트리밍 API를 사용하는 방식은 아닙니다.

로컬 검증에서 공개 영어 샘플의 첫 입력은 모델 준비 후 **1.75초**, 15.05초 전체 음성의 CPU 추론은 **4.672초**였습니다. 샘플 한 개의 수치이며 한국어 실사용의 지연이나 정확도를 보장하지 않습니다. [검증 기록과 확인이 남은 범위](docs/VALIDATION.md)를 참고하세요.

| 환경 | 상태 |
| --- | --- |
| Windows x64 CPU | 실제 입력·마이크·설치·제거 검증 |
| NVIDIA CUDA | 소스용 별도 의존성 구성 제공, 실측 미완료 |
| Intel XPU | 장치 선택 경로만 구현, XPU 배포·실측 미완료 |
| macOS MPS | 실험적 장치 선택, 전체 흐름 미검증 |
| Linux X11 / Wayland | 최종 구간 입력 경로, 실제 전체 흐름 미검증·Wayland 제한 |
| WSL → Windows 앱 입력 | Linux 프로세스에서는 지원하지 않음. Windows에서 실행 필요 |

GPU로 같은 모델을 실행하는 것은 주로 속도 개선을 위한 선택입니다. 현재 CPU/GPU의 한국어 정확도를 직접 비교한 결과는 없습니다. GPU 가속, 음성 분할 개선, 한국어 오류율·지연 측정이 후속 개선 항목입니다.

## 개발과 빌드

```bash
uv sync --locked --managed-python
QT_QPA_PLATFORM=offscreen uv run --no-sync python -m unittest discover -s tests -v
uv run --no-sync python -m compileall -q sori tools tests
uv run --no-sync python tools/package_source.py
```

31개 회귀 검사가 있으며 GitHub Actions에서 Windows·Linux 검사를 수행합니다. 검사에는 모델 다운로드나 실제 사용자 입력이 필요하지 않습니다. Windows 프로그램과 설치 파일을 만드는 방법은 [빌드 안내](docs/DEVELOPMENT.md), 변경 사항은 [CHANGELOG](CHANGELOG.md)에 있습니다.

가상환경·모델 캐시·사용자 기록·로그·빌드 결과는 Git에 포함하지 않습니다. 실행 배포 파일은 GitHub Releases 또는 별도 배포 파일로 관리합니다.
