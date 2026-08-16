@echo off
setlocal

rem Measure prompt-processing and generation throughput for the worker model.
rem Stop start-worker.cmd first: this loads the model itself and needs the same memory.
rem Record the result in ..\evaluation\results.md.

if not defined LLAMA_BENCH set "LLAMA_BENCH=C:\Tools\llama.cpp-cuda\llama-bench.exe"
if not defined MODEL       set "MODEL=C:\models\Qwen3.6-35B-A3B-UD-Q4_K_M.gguf"
if not defined NCMOE       set "NCMOE=99"
if not defined THREADS     set "THREADS=6"

if not exist "%LLAMA_BENCH%" (
    echo ERROR: llama-bench not found at "%LLAMA_BENCH%".
    exit /b 1
)

echo Benchmarking %MODEL%
echo   cpu-moe layers: %NCMOE%   threads: %THREADS%
echo.

"%LLAMA_BENCH%" ^
    -m "%MODEL%" ^
    -ngl 999 ^
    -ncmoe %NCMOE% ^
    -fa on ^
    -t %THREADS% ^
    -p 512 ^
    -n 128

endlocal
