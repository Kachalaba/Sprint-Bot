@echo off
REM ————————————————————————————————
REM  SprintBot launcher «бантик»
REM ————————————————————————————————
pushd "%~dp0"

REM если не хочешь держать переменную в системе — раскомментируй строку ниже
REM set "SPRINT_BOT_TOKEN=8175208212:AAE_r5Qnb5p29mr0aYpvWdldtSnoehHdix4"

call venv\Scripts\activate.bat
python bot.py

pause
popd
