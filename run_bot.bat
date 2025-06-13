@echo off
cd /d %~dp0
call venv311\Scripts\activate
python bot.py
pause
