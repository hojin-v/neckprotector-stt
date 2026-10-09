param([string]$Stage = (Join-Path $env:TEMP "Sori-build"))
$ErrorActionPreference = "Stop"
$SourceRoot = Split-Path $PSScriptRoot -Parent
if (Test-Path -LiteralPath $Stage) { throw "Choose a new staging directory; this one already exists: $Stage" }
New-Item -ItemType Directory -Path $Stage | Out-Null
Expand-Archive -LiteralPath (Join-Path $SourceRoot "dist\Sori-source.zip") -DestinationPath $Stage
$Project = Join-Path $Stage "Sori"
$LocalUv = Join-Path $SourceRoot "tools\uv\uv.exe"
if (Test-Path -LiteralPath $LocalUv) {
    New-Item -ItemType Directory -Path (Join-Path $Project "tools\uv") -Force | Out-Null
    Copy-Item -LiteralPath $LocalUv -Destination (Join-Path $Project "tools\uv\uv.exe")
}
Write-Host "Native Windows build directory: $Project"
& (Join-Path $Project "build-windows.ps1")
if ($LASTEXITCODE -ne 0) { throw "Native Windows build failed." }
Write-Host "Executable ready: $Project\dist\Sori\Sori.exe"
