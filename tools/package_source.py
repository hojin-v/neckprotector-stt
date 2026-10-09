"""Package source and launchers without models, caches, or virtual environments."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

root = Path(__file__).resolve().parents[1]
files = [root / name for name in (
    "pyproject.toml", "uv.lock", ".python-version", ".gitignore", ".gitattributes", "README.md", "CHANGELOG.md",
    "start-windows.bat", "start-unix.sh", "build-windows.ps1",
)]
for folder in ("sori", "tools", "tests", "docs", ".github"):
    files.extend(path for path in (root / folder).rglob("*")
                 if path.is_file() and "__pycache__" not in path.parts
                 and not path.is_relative_to(root / "tools" / "uv"))
output = root / "dist" / "Sori-source.zip"
output.parent.mkdir(exist_ok=True)
with ZipFile(output, "w", ZIP_DEFLATED) as archive:
    for path in sorted(files):
        archive.write(path, Path("Sori") / path.relative_to(root))
    assert archive.testzip() is None
print(f"{output}: {len(files)} files, {output.stat().st_size:,} bytes")
