@echo off
setlocal

rem Run one delegated task through the local worker and record the result.
rem
rem   scripts\run-task.cmd evaluation\tasks\0001-example.md
rem
rem The runtime must already be up (scripts\start-worker.cmd). See
rem ..\evaluation\README.md for the task format and how runs are scored.

if "%~1"=="" (
    echo Usage: run-task.cmd ^<task-file^> [extra run_task.py arguments]
    exit /b 2
)

python "%~dp0run_task.py" %*

endlocal
