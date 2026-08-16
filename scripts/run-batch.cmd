@echo off
setlocal

rem Run a batch of atomic tasks through the local worker on one branch.
rem
rem   scripts\run-batch.cmd --id refactor-01 evaluation\tasks\a.md evaluation\tasks\b.md
rem
rem The runtime must already be up (scripts\start-worker.cmd). The batch halts
rem on the first step whose acceptance command fails; see ..\evaluation\README.md.

if "%~1"=="" (
    echo Usage: run-batch.cmd --id ^<batch-id^> ^<task-file^> [task-file ...]
    exit /b 2
)

python "%~dp0run_batch.py" %*

endlocal
