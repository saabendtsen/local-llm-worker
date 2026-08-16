@echo off
setlocal

rem Confirm the local worker runtime is up and can complete a chat request.

if not defined HOST set "HOST=127.0.0.1"
if not defined PORT set "PORT=8000"

set "BASE=http://%HOST%:%PORT%"

echo == health ==
curl.exe -s --max-time 10 "%BASE%/health"
if errorlevel 1 (
    echo.
    echo ERROR: no response from %BASE%. Is start-worker.cmd running?
    exit /b 1
)
echo.

echo.
echo == models ==
curl.exe -s --max-time 10 "%BASE%/v1/models"
echo.

echo.
echo == completion ==
rem max_tokens must be generous: this is a reasoning model, and the thinking trace is
rem spent from the same budget. A small limit returns an empty `content` with a full
rem token count, which looks like a broken server but is only a truncated thought.
curl.exe -s --max-time 300 "%BASE%/v1/chat/completions" ^
    -H "Content-Type: application/json" ^
    -d "{\"model\":\"local-worker\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with exactly: worker ready\"}],\"max_tokens\":512}"
echo.

endlocal
