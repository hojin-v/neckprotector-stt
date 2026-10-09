$ErrorActionPreference = "Stop"
$SoriUvDirectory = Join-Path $PSScriptRoot "uv"
$SoriUvExecutable = Join-Path $SoriUvDirectory "uv.exe"
$SoriPreviousInstall = $env:UV_UNMANAGED_INSTALL
$SoriPreviousProtocol = [Net.ServicePointManager]::SecurityProtocol

try {
    if (Test-Path -LiteralPath $SoriUvExecutable -PathType Leaf) {
        & $SoriUvExecutable --version
        if ($LASTEXITCODE -eq 0) { return }
    }
    New-Item -ItemType Directory -Path $SoriUvDirectory -Force | Out-Null
    # Official unmanaged installation: no global PATH or shell-profile changes.
    $env:UV_UNMANAGED_INSTALL = $SoriUvDirectory
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-RestMethod -Uri "https://astral.sh/uv/install.ps1" | Invoke-Expression
    if (-not (Test-Path -LiteralPath $SoriUvExecutable -PathType Leaf)) {
        throw "The uv installer did not create tools\uv\uv.exe."
    }
    & $SoriUvExecutable --version
    if ($LASTEXITCODE -ne 0) { throw "The downloaded Windows uv.exe could not run." }
}
finally {
    $env:UV_UNMANAGED_INSTALL = $SoriPreviousInstall
    [Net.ServicePointManager]::SecurityProtocol = $SoriPreviousProtocol
}
