param([switch]$Incremental)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$SoriUvCommand = Get-Command uv.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
$SoriUvCandidates = @(
    $(if ($SoriUvCommand) { $SoriUvCommand.Source }),
    "$env:USERPROFILE\.local\bin\uv.exe",
    "$env:LOCALAPPDATA\Microsoft\WinGet\Links\uv.exe",
    "$env:USERPROFILE\scoop\shims\uv.exe",
    "$PSScriptRoot\tools\uv\uv.exe"
)
$SoriUv = $null
foreach ($Candidate in $SoriUvCandidates) {
    if ($Candidate -and (Test-Path -LiteralPath $Candidate -PathType Leaf)) {
        & $Candidate --version *> $null
        if ($LASTEXITCODE -eq 0) { $SoriUv = $Candidate; break }
    }
}
if (-not $SoriUv) {
    & (Join-Path $PSScriptRoot "tools\bootstrap-uv.ps1")
    $SoriUv = Join-Path $PSScriptRoot "tools\uv\uv.exe"
    if (-not (Test-Path -LiteralPath $SoriUv -PathType Leaf)) {
        throw "Windows uv.exe was not found after local installation."
    }
}
$env:UV_PROJECT_ENVIRONMENT = ".venv-win"
$SoriExtra = if ($env:SORI_ASR_EXTRA) { $env:SORI_ASR_EXTRA } else { "asr" }
if ($SoriExtra -notin @("asr", "asr-cuda")) { throw "SORI_ASR_EXTRA must be asr or asr-cuda." }
& $SoriUv sync --locked --managed-python --extra $SoriExtra --extra build
if ($LASTEXITCODE -ne 0) { throw "Build environment installation failed." }
$SoriClean = if ($Incremental) { @() } else { @("--clean") }
& $SoriUv run --no-sync python -m PyInstaller --noconfirm @SoriClean --windowed --onedir --name Sori `
    --paths . `
    --icon sori/assets/sori.ico --version-file tools/windows-version.txt `
    --additional-hooks-dir tools/pyinstaller-hooks --runtime-hook tools/pyinstaller-runtime.py `
    --add-data "sori/assets:sori/assets" --collect-all librosa --collect-all soundfile `
    --collect-all accelerate --collect-data torch `
    --hidden-import pynput.keyboard._win32 --hidden-import pynput.mouse._win32 `
    --hidden-import PySide6.QtMultimedia `
    tools/windows-entry.py
if ($LASTEXITCODE -ne 0) { throw "Application build failed." }
& $SoriUv run --no-sync python tools/fix_windows_runtime.py dist/Sori
if ($LASTEXITCODE -ne 0) { throw "Matching SSL runtime could not be embedded." }
Write-Host "Built: dist\Sori\Sori.exe. Copy the entire Sori folder to distribute it."
