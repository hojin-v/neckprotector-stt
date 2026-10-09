"""Keep the embedded Python SSL ABI even when PATH contains another OpenSSL."""
import argparse
import shutil
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("folder", type=Path)
args = parser.parse_args()
if sys.platform != "win32":
    parser.error("Run this using the Windows build interpreter")
for name in ("libssl-3-x64.dll", "libcrypto-3-x64.dll"):
    source = Path(sys.base_prefix) / "DLLs" / name
    if not source.is_file():
        raise RuntimeError(f"Python runtime library is missing: {source}")
    destination = args.folder / "_internal" / name
    shutil.copy2(source, destination)
    print(f"Embedded matching Python runtime: {name}", flush=True)
