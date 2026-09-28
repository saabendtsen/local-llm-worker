@echo off
setlocal
python "%~dp0chatbot_status.py"
exit /b %ERRORLEVEL%
