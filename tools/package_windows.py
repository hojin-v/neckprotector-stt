"""Zip the complete portable executable folder; omit build environments and models."""
import argparse
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

parser = argparse.ArgumentParser()
parser.add_argument("folder", type=Path)
parser.add_argument("output", type=Path)
args = parser.parse_args()
if not (args.folder / "Sori.exe").is_file() or not (args.folder / "_internal").is_dir():
    parser.error("Expected a complete PyInstaller Sori directory")
instructions = """소리 · Sori 0.2.0 — Windows x64

1. ZIP 전체를 Windows 로컬 폴더에 풀어주세요.
2. 기존 소리 프로그램이 실행 중이면 트레이 메뉴에서 종료하세요.
3. Sori.exe를 더블클릭하세요. Python이나 uv를 설치할 필요 없습니다.
4. 기존 모델은 백그라운드에서 자동으로 불러옵니다. 처음 사용이라면 기록 화면에서 '모델 준비하기'를 누르세요.
5. 입력할 곳에 커서를 놓고 CapsLock을 누르고 말한 뒤 다시 눌러 마칩니다. 말하는 도중에도 중간 결과가 입력됩니다.
6. 녹음할 때 작은 패널이 나타나고, 마치면 자동으로 사라집니다. 기록·설정은 트레이 메뉴에서 여세요.

설정에서 사용할 키, 누르기/길게 누르기, 마이크를 변경할 수 있습니다.
PowerToys 등으로 매핑한 키도 받습니다. 매핑 결과가 F13이라면 Sori 지정 키도 F13으로 선택하세요.
입력 전달은 기본적으로 붙여넣기입니다. 붙여넣기를 받지 않는 앱은 설정에서 직접 입력을 선택하세요.
'마이크 테스트 · 5초'로 입력 음량을 확인할 수 있습니다. 테스트 음성은 저장하지 않습니다.
Windows 설정 → 개인정보 및 보안 → 마이크에서 '데스크톱 앱에서 마이크에 액세스하도록 허용'을 켜주세요.
데스크톱 앱은 앱별 마이크 권한 스위치가 표시되지 않을 수 있습니다.

Sori.exe와 _internal 폴더는 함께 두어야 합니다. Sori.exe만 옮기면 실행되지 않습니다.
이 배포본은 CPU용입니다. 모델은 배포 ZIP에 포함되지 않습니다.
기존 모델, 설정, 기록은 %LOCALAPPDATA%\\Sori에 있으므로 업데이트해도 유지됩니다.
기록 폴더: %LOCALAPPDATA%\\Sori\\history (설정에서 바꿀 수 있습니다.)
설치를 원하면 별도로 제공하는 Sori-Setup-0.2.0.exe를 실행하세요. 설치 후에는 시작 메뉴의 Sori로 실행합니다.
"""
(args.folder / "사용 방법.txt").write_text(instructions, encoding="utf-8-sig")
args.output.parent.mkdir(parents=True, exist_ok=True)
files = sorted(path for path in args.folder.rglob("*") if path.is_file())
with ZipFile(args.output, "w", ZIP_DEFLATED, compresslevel=6) as archive:
    for path in files:
        archive.write(path, Path("Sori") / path.relative_to(args.folder))
print(f"{args.output}: {len(files)} files, {args.output.stat().st_size:,} bytes", flush=True)
