@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python scripts\04_run_webui.py --port 7860
pause

