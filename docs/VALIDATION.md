# Sori 0.2.0 검증

2026-10-09, Ubuntu/WSL2 및 실제 Windows 11 x64에서 확인했습니다.

| 항목 | 확인 내용 |
| --- | --- |
| 회귀 검사 | Linux와 실제 Windows에서 31개 통과 |
| Windows 실제 입력 | 별도 프로세스로 실행한 시험용 Qt 편집기에 한국어·이모지 입력. 중간 인식 수정, 최종 문장의 중복 없는 확정 확인 |
| 매핑 입력 | Windows SendInput으로 주입한 F24 이벤트를 전역 키로 받아 시작·중단. 앱 자체 입력 태그만 무시 |
| 길게 누르기 | 지정 키를 누르고 있는 동안 텍스트가 입력되고, 떼면 중단 |
| 포커스·패널 | 녹음 시작 시 패널이 나타나도 시험 편집기 포커스 유지. 중단 후 자동 숨김 |
| 실제 모델 전체 흐름 | 공개 영어 음성을 실제 재생 속도로 공급 → Qwen CPU 추론 → 중간 결과 입력 → 최종 입력과 기록 일치 |
| 소스 첫 입력 지연 | 모델 준비 후 음성 공급 시작부터 1.75초. Core Ultra 5 226V, Windows 11, CPU 실행 |
| 클립보드·보관 | 전체 흐름 중 누적 클립보드, SQLite 확정, 일별 Markdown·JSONL 작성 확인 |
| 오디오 회귀 | QtAudio 열거형, 정상 마이크 열기, 실제 OpenError, 연결 끊김, PCM 디코딩·음량 모니터 확인 |
| 음성 구간 | 발화 중 0.8초 간격 초안 요청, 0.45초 쉼 또는 최대 6초 확정. 최종 구간에서 샘플 유실 없는 분할 확인 |
| 추론 대기열 | 오래된 중간 요청을 교체하고 최종 요청 우선. 최종 기록의 순서 유지 |
| 기록 날짜 | 자정 경계, 지연된 결과의 녹음 날짜, 내보내기 실패 후 DB 유지·복구 확인 |
| UI | Windows 화면 플러그인에서 Malgun Gothic 렌더링, 310×174 논리 픽셀 패널, 스크롤 가능한 설정과 저장 버튼 확인 |
| 실행 관리 | uv 관리 Python 3.12.14, 잠금 파일, 소스 빌드. 실행 배포에는 Python 런타임 포함 |
| 정적 검사 | Python 컴파일 및 Unix 시작 스크립트 구문 검사 통과 |

## 최종 실행 파일 검사

Sori.exe 0.2.0에서 한국어·이모지의 실제 입력, 초안 수정, 주입된 전역 키, 길게 누르는 중 입력, 포커스 유지, 자동 숨김, 클립보드와 기록을 확인했습니다. 공개 영어 샘플의 실제 모델 추론은 별도로 실행해 **4.672초**에 완료했습니다. 당시 모델 로딩은 **6.015초**였으며 파일 캐시가 준비된 상태의 측정입니다. 마이크는 0.5초 동안 **7,969프레임**을 수신했고 오류가 없었습니다.

공개 음성과 실제 입력을 합친 전체 검사는 Windows 소스 실행에서 통과했습니다. 실행 파일로 같은 긴 검사를 시도했을 때 다른 작업 창이 활성화되어 입력 보호가 중단시켰습니다. 최종 실행 파일은 입력과 실제 모델 추론을 각각 검증했습니다. 사용자 문서로 입력을 강제하지 않았습니다.

두 번째 실행의 종료 코드 0, 첫 실행 유지, 설정 창 1개를 확인해 중복 실행 없이 기존 인스턴스에 연결됨을 검증했습니다. 수치와 검사 항목은 [배포 검사 자료](release-checks.json)에 있습니다.

## 설치·배포 검사

Inno Setup 6.7.3으로 사용자 계정용 `Sori-Setup-0.2.0.exe`를 만들었습니다. 별도 임시 폴더에 자동 실행·바로가기 없이 설치하고, 설치된 실행 파일의 SHA-256 일치, Windows UI 실행·정상 종료, Qt·PyTorch·Transformers 런타임 진단을 확인했습니다. 제거 후 실행 파일과 해당 임시 설치의 제거 등록이 사라지는 것도 확인했습니다. 기존 사용자 데이터는 별도 폴더에 보관합니다.

휴대용 ZIP은 360,871,784바이트, 15,996개 파일이며 전체 CRC 검사를 통과했습니다. 설치 파일과 실행 파일은 CPU용입니다. 배포 서명은 포함하지 않습니다. 이번 빌드를 위해 준비한 임시 설치 컴파일러는 검증 후 제거했습니다.

## 검증 방법

```bash
.venv-linux/bin/python -m unittest discover -s tests -v
.venv-linux/bin/python -m compileall -q sori tools tests
bash -n start-unix.sh
```

Windows에서는 uv로 만든 빌드 환경에서 같은 31개 회귀 검사를 실행했습니다. 이 검사에는 offscreen 화면 플러그인을 사용했습니다. 실제 입력·폰트·UI 검사는 Windows 기본 화면 플러그인을 별도로 사용했습니다.

```powershell
.\dist\Sori\Sori.exe --desktop-test input-check.json --audio-file public-sample.wav
.\dist\Sori\Sori.exe --diagnostics diagnostics.json --audio-file public-sample.wav --microphone-test
.\dist\Sori\Sori.exe --preview-dir preview
```

`--desktop-test`는 자체 시험 편집기에만 키와 텍스트를 전달하고, 임시 기록 폴더를 사용하며, 검사가 끝나면 기존 클립보드 내용을 복원합니다. 공개 샘플을 직접 실시간 속도로 공급하므로 마이크 캡처와 추론·입력의 전체 검사는 별개입니다. `--microphone-test`는 0.5초 동안 실제 마이크를 열고 음성을 저장·인식하지 않습니다. 설정의 5초 테스트도 음량만 확인합니다.

공개 음성은 [Qwen 공식 영어 샘플](https://qianwen-res.oss-cn-beijing.aliyuncs.com/Qwen3-ASR-Repo/asr_en.wav) 15.05초입니다. 첫 입력 시간에는 모델 로딩이 포함되지 않습니다. 샘플 한 개의 결과이며 한국어 정확도나 다른 PC의 지연을 보장하는 벤치마크는 아닙니다.

## 직접 확인이 남은 범위

- 사용자의 실제 물리 키·PowerToys/AutoHotkey 설정과 브라우저·메모장 등 개별 앱. 주입된 키 이벤트와 실제 다른 프로세스의 Qt 편집기를 검증했습니다.
- 장시간 한국어 받아쓰기 정확도, 다양한 오디오 드라이버, 특수 입력 편집기와 조합 중인 IME.
- Intel XPU·NVIDIA CUDA·Apple MPS에서 Qwen의 실제 성능. 이번 배포는 CPU용입니다.
- macOS 권한과 전체 입력 흐름, Linux X11·Wayland 전체 흐름. 중간 결과 실시간 입력은 현재 Windows 경로에 구현했습니다.

WSL에서 Linux 프로세스로 실행하면 Windows 전체 키와 입력창을 제어하지 못합니다. Windows에서 설치된 Sori를 실행해야 합니다. 모델·설정·기록은 `%LOCALAPPDATA%\Sori`에 보관합니다. [Microsoft 마이크 권한 안내](https://support.microsoft.com/en-us/windows/privacy/turn-on-app-permissions-for-your-microphone-in-windows)에 따라 데스크톱 앱의 마이크 접근 허용을 켭니다.
