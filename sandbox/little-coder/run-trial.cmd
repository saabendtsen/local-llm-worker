@echo off
setlocal

rem Run one little-coder trial against an isolated worktree.
rem
rem   run-trial.cmd <worktree-path> "<task text>"
rem
rem Uses the locally installed little-coder in .\node_modules -- never a global
rem install -- and this directory's models.json, so the working setup's Pi
rem 0.84.2 and ~/.pi/agent/models.json are untouched.
rem
rem The model server is shared and runs with a single slot, so do NOT start a
rem trial while an evaluation run is in flight. See README.md.

if "%~2"=="" (
    echo Usage: run-trial.cmd ^<worktree-path^> "^<task text^>"
    echo.
    echo Refusing to run without an explicit worktree. Pointing a trial at the
    echo main checkout is how two agents end up editing one tree.
    exit /b 2
)

set "WORKTREE=%~1"
set "TASK=%~2"
set "HERE=%~dp0"

if not exist "%WORKTREE%\.git" (
    echo ERROR: "%WORKTREE%" is not a Git worktree.
    echo Create one first - see README.md.
    exit /b 2
)

set "LAUNCHER=%HERE%node_modules\little-coder\bin\little-coder.mjs"
if not exist "%LAUNCHER%" (
    echo ERROR: little-coder is not installed here.
    echo Run: npm install
    exit /b 2
)

rem Point it at this directory's model config, not the user-level one.
set "LITTLE_CODER_MODELS_FILE=%HERE%models.json"

if not defined MODEL set "MODEL=local-worker/local-worker"

rem Fail on HTTP errors, not just on connection failure: the server returns 503
rem while the model is still loading, and curl without -f exits 0 for that.
curl.exe -sf --max-time 5 http://127.0.0.1:8000/health >nul 2>&1
if errorlevel 1 (
    echo ERROR: the model server is not ready at http://127.0.0.1:8000.
    echo Start it with scripts\start-worker.cmd and wait for it to load.
    exit /b 1
)

echo little-coder trial
echo   worktree : %WORKTREE%
echo   models   : %LITTLE_CODER_MODELS_FILE%
echo   model    : %MODEL%
echo.

pushd "%WORKTREE%"
node "%LAUNCHER%" -p "%TASK%" ^
    --mode json ^
    --model %MODEL% ^
    --no-session ^
    --exclude-tools ask_question
popd

endlocal
