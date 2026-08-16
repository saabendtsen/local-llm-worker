@echo off
setlocal

rem Start the local LLM worker runtime: llama-server with an OpenAI-compatible API.
rem Every setting below can be overridden by setting the environment variable first.
rem See ..\docs\runtime.md for what the flags do, how they relate to the deployment
rem guide this is based on, and how to tune NCMOE / CTX / UBATCH for this machine.

if not defined LLAMA_BIN  set "LLAMA_BIN=C:\Tools\llama.cpp-cuda\llama-server.exe"
if not defined MODEL      set "MODEL=C:\models\Qwen3.6-35B-A3B-UD-Q4_K_M.gguf"
if not defined ALIAS      set "ALIAS=local-worker"
if not defined HOST       set "HOST=127.0.0.1"
if not defined PORT       set "PORT=8000"
if not defined CTX        set "CTX=120000"
if not defined NCMOE      set "NCMOE=38"
if not defined THREADS    set "THREADS=6"
if not defined BATCH      set "BATCH=4096"
if not defined UBATCH     set "UBATCH=2048"
if not defined LOADMODE   set "LOADMODE=mmap+mlock"
if not defined CORS       set "CORS=localhost"
if not defined EFFORT     set "EFFORT=default"

if not exist "%LLAMA_BIN%" (
    echo ERROR: llama-server not found at "%LLAMA_BIN%".
    echo Install the CUDA build as described in docs\runtime.md.
    exit /b 1
)

if not exist "%MODEL%" (
    echo ERROR: model not found at "%MODEL%".
    echo Download it as described in docs\runtime.md.
    exit /b 1
)

echo Starting local worker runtime
echo   binary   : %LLAMA_BIN%
echo   model    : %MODEL%
echo   endpoint : http://%HOST%:%PORT%/v1  (model name: %ALIAS%)
echo   context  : %CTX%    cpu-moe layers: %NCMOE%    threads: %THREADS%
echo   batch    : %BATCH% / %UBATCH%    load mode: %LOADMODE%
echo.

"%LLAMA_BIN%" ^
    -m "%MODEL%" ^
    --alias "%ALIAS%" ^
    --host %HOST% ^
    --port %PORT% ^
    -c %CTX% ^
    -ngl 999 ^
    -ncmoe %NCMOE% ^
    -t %THREADS% ^
    -b %BATCH% ^
    -ub %UBATCH% ^
    -fa on ^
    -ctk q8_0 ^
    -ctv q8_0 ^
    --load-mode %LOADMODE% ^
    --cors-origins %CORS% ^
    --reasoning-effort %EFFORT% ^
    -np 1 ^
    --jinja

endlocal
