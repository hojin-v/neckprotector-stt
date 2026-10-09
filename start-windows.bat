@echo off
setlocal
pushd "%~dp0"
if errorlevel 1 (
    echo Could not open the project folder. Copy it to a local Windows folder.
    pause
    exit /b 1
)
rem Resolve the executable directly, including fresh installs missing from PATH.
set "SORI_UV_EXE="
for /f "delims=" %%U in ('where uv.exe 2^>nul') do call :try_uv "%%U"
call :try_uv "%USERPROFILE%\.local\bin\uv.exe"
call :try_uv "%LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe"
call :try_uv "%USERPROFILE%\scoop\shims\uv.exe"
call :try_uv "%~dp0tools\uv\uv.exe"
if not defined SORI_UV_EXE (
    echo Preparing Windows uv inside the project folder...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\bootstrap-uv.ps1"
    if errorlevel 1 goto uv_missing
    call :try_uv "%~dp0tools\uv\uv.exe"
)
if not defined SORI_UV_EXE goto uv_missing
set "UV_PROJECT_ENVIRONMENT=.venv-win"
if not defined SORI_ASR_EXTRA set "SORI_ASR_EXTRA=asr"
if not "%SORI_ASR_EXTRA%"=="asr" if not "%SORI_ASR_EXTRA%"=="asr-cuda" (
    echo SORI_ASR_EXTRA must be asr or asr-cuda.
    goto failed
)
"%SORI_UV_EXE%" sync --locked --managed-python --extra "%SORI_ASR_EXTRA%"
if errorlevel 1 goto failed
"%SORI_UV_EXE%" run --no-sync python -m sori %*
if errorlevel 1 goto failed
exit /b 0
:failed
echo Sori could not start. Please check the error above.
pause
exit /b 1

:uv_missing
echo Windows uv.exe could not be found or started.
echo Linux uv installed in WSL cannot be used by this Windows launcher.
echo Open Windows PowerShell and run:
echo   winget install --id astral-sh.uv -e
echo Then close and reopen your terminal and run this launcher again.
echo Alternative official installer:
echo   powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"
echo No separate Python installation is needed.
pause
exit /b 1

:try_uv
if defined SORI_UV_EXE exit /b 0
if not exist "%~1" exit /b 0
"%~1" --version >nul 2>nul
if errorlevel 1 exit /b 0
set "SORI_UV_EXE=%~1"
exit /b 0
