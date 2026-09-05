@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "OPEN_WEBUI_DIR=D:\OpenWebUI"
set "OPEN_WEBUI_EXE=%LOCALAPPDATA%\Programs\open-webui\open-webui.exe"

if /i "%~1"=="--dry-run" (
    echo Would install OpenWebUI.OpenWebUI version 0.0.20 with winget.
    echo Would run "%SCRIPT_DIR%configure_chatbot.py" for loopback-only port 8080 and disabled extra tools.
    echo Would launch Open WebUI with data, temporary files, and package cache on D:.
    echo Would run tailscale serve --bg --yes 8080 for the UI only.
    exit /b 0
)

winget install --id OpenWebUI.OpenWebUI --version 0.0.20 --exact --accept-package-agreements --accept-source-agreements
if errorlevel 1 exit /b %errorlevel%

python "%SCRIPT_DIR%configure_chatbot.py" --install-dir "%OPEN_WEBUI_DIR%"
if errorlevel 1 exit /b %errorlevel%

set "UV_CACHE_DIR=%OPEN_WEBUI_DIR%\uv-cache"
set "TEMP=%OPEN_WEBUI_DIR%\tmp"
set "TMP=%OPEN_WEBUI_DIR%\tmp"
start "" "%OPEN_WEBUI_EXE%"

tailscale.exe serve --bg --yes 8080
if errorlevel 1 exit /b %errorlevel%

echo Initial setup requested. Open the Tailscale HTTPS URL and create the first local account.
exit /b 0
