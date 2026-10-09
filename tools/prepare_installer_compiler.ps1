param([string]$Installer, [string]$Destination = (Join-Path $env:TEMP "Sori-inno-compiler"))
$ErrorActionPreference = "Stop"
$Signature = Get-AuthenticodeSignature -LiteralPath $Installer
if ($Signature.Status -ne "Valid") { throw "The official compiler installer signature is not valid: $($Signature.Status)" }
Write-Host "Verified compiler publisher: $($Signature.SignerCertificate.Subject)"
$NativeInstaller = Join-Path $env:TEMP "Sori-inno-compiler-setup.exe"
Copy-Item -LiteralPath $Installer -Destination $NativeInstaller
$Arguments = '/VERYSILENT /SUPPRESSMSGBOXES /SP- /CURRENTUSER /NORESTART /NOICONS /TASKS="" /DIR="' + $Destination + '"'
$Process = Start-Process -FilePath $NativeInstaller -ArgumentList $Arguments -PassThru
while (-not $Process.WaitForExit(10000)) { Write-Host "Preparing the temporary packaging compiler..." }
if ($Process.ExitCode -ne 0) { throw "Compiler preparation failed: $($Process.ExitCode)" }
if (-not (Test-Path -LiteralPath (Join-Path $Destination "ISCC.exe"))) { throw "Compiler was not installed." }
Write-Host "Compiler ready: $Destination\ISCC.exe"
