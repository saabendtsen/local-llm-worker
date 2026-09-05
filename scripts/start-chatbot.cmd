@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
if not defined OPEN_WEBUI_EXE set "OPEN_WEBUI_EXE=%LOCALAPPDATA%\Programs\open-webui\open-webui.exe"
if not defined OPEN_WEBUI_DIR set "OPEN_WEBUI_DIR=D:\OpenWebUI"

if /i "%~1"=="--dry-run" (
    echo Would start "%SCRIPT_DIR%start-worker.cmd" in its own terminal if local-worker is unavailable.
    echo Would launch "%OPEN_WEBUI_EXE%" with its local server on loopback.
    echo Phone access is configured separately with Tailscale Serve for the Open WebUI port only.
    exit /b 0
)

powershell.exe -NoProfile -Command "try { $m=Invoke-RestMethod 'http://127.0.0.1:8000/v1/models' -TimeoutSec 2; if ($m.data.id -contains 'local-worker') { exit 0 }; exit 1 } catch { exit 1 }"
if errorlevel 1 start "Local LLM runtime" cmd.exe /k call "%SCRIPT_DIR%start-worker.cmd"

if not exist "%OPEN_WEBUI_EXE%" (
    echo ERROR: Open WebUI Desktop was not found at "%OPEN_WEBUI_EXE%".
    echo Install OpenWebUI.OpenWebUI or set OPEN_WEBUI_EXE to its executable path.
    exit /b 1
)

python "%SCRIPT_DIR%configure_chatbot.py" --install-dir "%OPEN_WEBUI_DIR%"
if errorlevel 1 exit /b %errorlevel%

set "UV_CACHE_DIR=%OPEN_WEBUI_DIR%\uv-cache"
set "TEMP=%OPEN_WEBUI_DIR%\tmp"
set "TMP=%OPEN_WEBUI_DIR%\tmp"
start "" "%OPEN_WEBUI_EXE%"
echo Chatbot startup requested. Run scripts\check-chatbot.cmd after both services finish loading.
exit /b 0
