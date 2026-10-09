param(
    [string]$BuildDirectory = (Split-Path $PSScriptRoot -Parent),
    [string]$CopyTo = "",
    [string]$Compiler = (Join-Path $env:TEMP "Sori-inno-compiler\ISCC.exe"),
    [switch]$LiveAudio
)
$ErrorActionPreference = "Stop"
$SourceRoot = Split-Path $PSScriptRoot -Parent
$Runtime = Join-Path $BuildDirectory "dist\Sori"
$Executable = Join-Path $Runtime "Sori.exe"
$Python = Join-Path $BuildDirectory ".venv-win\Scripts\python.exe"
$Report = Join-Path $SourceRoot ".test-data\windows-exe-diagnostics.json"
$Sample = Join-Path $SourceRoot ".test-data\qwen-official-english.wav"
if (-not (Test-Path -LiteralPath $Executable)) { throw "Build Sori.exe first." }
if ($CopyTo -and (Test-Path -LiteralPath $CopyTo)) { throw "Copy destination already exists: $CopyTo" }
function Invoke-SoriCheck([string[]]$SoriArguments, [string]$Program = $Executable) {
    $Quoted = ($SoriArguments | ForEach-Object { '"' + $_ + '"' }) -join ' '
    $Process = Start-Process -FilePath $Program -ArgumentList $Quoted -PassThru
    while (-not $Process.WaitForExit(10000)) { Write-Host "Checking the final Sori.exe..." }
    if ($Process.ExitCode -ne 0) { throw "Executable check failed with code $($Process.ExitCode)." }
}
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
$DesktopReport = Join-Path $SourceRoot ".test-data\windows-exe-live-input.json"
$DesktopArguments = @("--desktop-test", $DesktopReport)
if ($LiveAudio) { $DesktopArguments += @("--audio-file", $Sample, "--cache-dir", (Join-Path $env:LOCALAPPDATA "Sori\models")) }
Invoke-SoriCheck $DesktopArguments
$DesktopResult = Get-Content -LiteralPath $DesktopReport -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $DesktopResult.ok -or -not $DesktopResult.frozen) { throw "Final executable desktop input check failed." }
Write-Host "Actual desktop input passed."
if ($LiveAudio) { Write-Host "First public-audio text: $($DesktopResult.public_audio_first_text_seconds) seconds." }
Invoke-SoriCheck @("--diagnostics", $Report, "--audio-file", $Sample, "--cache-dir", (Join-Path $env:LOCALAPPDATA "Sori\models"), "--microphone-test")
$Result = Get-Content -LiteralPath $Report -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $Result.ok) { throw "Executable diagnostics did not pass." }
Write-Host "Microphone frames: $($Result.capture.frames_received); ASR seconds: $($Result.inference_seconds)"
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
Invoke-SoriCheck @("--preview-dir", (Join-Path $SourceRoot "docs\windows-preview"))
Write-Host "Windows executable UI and clean shutdown passed."
$Zip = Join-Path $BuildDirectory "dist\Sori-Windows-x64.zip"
& $Python (Join-Path $SourceRoot "tools\package_windows.py") $Runtime $Zip
if ($LASTEXITCODE -ne 0) { throw "Release archive creation failed." }
Copy-Item -LiteralPath $Zip -Destination (Join-Path $SourceRoot "dist\Sori-Windows-x64.zip")
if (-not (Test-Path -LiteralPath $Compiler)) { throw "Installer compiler was not prepared." }
$CompileLog = Join-Path $BuildDirectory "dist\installer-build.log"
& $Compiler ("/DRuntimeDir=" + $Runtime) ("/DReleaseDir=" + (Join-Path $BuildDirectory "dist")) (Join-Path $SourceRoot "tools\sori-setup.iss") *> $CompileLog
if ($LASTEXITCODE -ne 0) { Get-Content -LiteralPath $CompileLog -Tail 20; throw "Installer compilation failed." }
$Installer = Join-Path $BuildDirectory "dist\Sori-Setup-0.2.0.exe"
if (-not (Test-Path -LiteralPath $Installer)) { throw "Installer output is missing." }
Write-Host "Installer compiled. Verifying installation and removal in an isolated folder..."
$UninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{DF8F76D4-0884-43F6-A63E-BE681523F049}_is1"
if (Test-Path $UninstallKey) { throw "An installed Sori already exists; isolated installer verification would change its uninstall registration." }
$InstallCheck = Join-Path $env:TEMP ("Sori-install-check-" + [guid]::NewGuid().ToString("N"))
$InstallLog = Join-Path $BuildDirectory "dist\installer-check.log"
$InstallArguments = '/VERYSILENT /SUPPRESSMSGBOXES /SP- /NORESTART /NOICONS /TASKS="" /DIR="' + $InstallCheck + '" /LOG="' + $InstallLog + '"'
$InstallProcess = Start-Process -FilePath $Installer -ArgumentList $InstallArguments -PassThru
while (-not $InstallProcess.WaitForExit(10000)) { Write-Host "Checking isolated installation..." }
if ($InstallProcess.ExitCode -ne 0) { throw "Installer check failed: $($InstallProcess.ExitCode)" }
$InstalledExecutable = Join-Path $InstallCheck "Sori.exe"
$InstallReport = [ordered]@{ installed = $false; runtime_identical = $false; preview = $false; uninstalled = $false }
try {
    $InstallReport.installed = Test-Path -LiteralPath $InstalledExecutable
    $InstallReport.runtime_identical = (Get-FileHash -LiteralPath $InstalledExecutable).Hash -eq (Get-FileHash -LiteralPath $Executable).Hash
    if (-not $InstallReport.runtime_identical) { throw "Installed executable does not match the verified release." }
    Invoke-SoriCheck @("--preview-dir", (Join-Path $BuildDirectory "dist\installed-preview")) $InstalledExecutable
    Invoke-SoriCheck @("--diagnostics", (Join-Path $BuildDirectory "dist\installed-diagnostics.json")) $InstalledExecutable
    $InstalledDiagnostics = Get-Content (Join-Path $BuildDirectory "dist\installed-diagnostics.json") -Raw | ConvertFrom-Json
    if (-not $InstalledDiagnostics.ok) { throw "Installed runtime check failed." }
    $InstallReport.preview = $true
} finally {
    $Uninstaller = Join-Path $InstallCheck "unins000.exe"
    if (Test-Path -LiteralPath $Uninstaller) {
        $RemoveProcess = Start-Process -FilePath $Uninstaller -ArgumentList "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART" -PassThru
        while (-not $RemoveProcess.WaitForExit(10000)) { Write-Host "Removing the isolated installation..." }
        $InstallReport.uninstalled = $RemoveProcess.ExitCode -eq 0 -and -not (Test-Path -LiteralPath $InstalledExecutable) -and -not (Test-Path $UninstallKey)
    }
    $InstallReport | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $SourceRoot ".test-data\windows-installer.json") -Encoding UTF8
}
if (-not $InstallReport.uninstalled) { throw "Isolated installer removal did not pass." }
Copy-Item -LiteralPath $Installer -Destination (Join-Path $SourceRoot "dist\Sori-Setup-0.2.0.exe")
if ($CopyTo) {
    Copy-Item -LiteralPath $Runtime -Destination $CopyTo -Recurse
    Write-Host "Ready to run: $CopyTo\Sori.exe"
}
Write-Host "Ready to install: $SourceRoot\dist\Sori-Setup-0.2.0.exe"
