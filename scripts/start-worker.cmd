@echo off
setlocal

rem Start the local LLM worker runtime: llama-server with an OpenAI-compatible API.
rem Every setting below can be overridden by setting the environment variable first.
rem See ..\docs\runtime.md for what the flags do and how to tune NCMOE.

if not defined LLAMA_BIN  set "LLAMA_BIN=C:\Tools\llama.cpp-cuda\llama-server.exe"
if not defined MODEL      set "MODEL=C:\models\Qwen3.6-35B-A3B-UD-Q4_K_M.gguf"
if not defined ALIAS      set "ALIAS=local-worker"
if not defined HOST       set "HOST=127.0.0.1"
if not defined PORT       set "PORT=8000"
if not defined CTX        set "CTX=32768"
if not defined NCMOE      set "NCMOE=99"
if not defined THREADS    set "THREADS=6"

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
echo   binary  : %LLAMA_BIN%
echo   model   : %MODEL%
echo   endpoint: http://%HOST%:%PORT%/v1  (model name: %ALIAS%)
echo   context : %CTX%   cpu-moe layers: %NCMOE%   threads: %THREADS%
echo.

"%LLAMA_BIN%" ^
    -m "%MODEL%" ^
    --alias "%ALIAS%" ^
    --host %HOST% ^
    --port %PORT% ^
    -c %CTX% ^
    -ngl 999 ^
    -ncmoe %NCMOE% ^
    -fa on ^
    -ctk q8_0 ^
    -ctv q8_0 ^
    -t %THREADS% ^
    -np 1 ^
    --jinja

endlocal
