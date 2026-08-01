@echo off
cd /d "%~dp0"
echo Starting ValueHunt server...
start http://127.0.0.1:8100
.venv\Scripts\python.exe start_webui.py
pause
