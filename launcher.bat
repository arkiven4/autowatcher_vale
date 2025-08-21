@echo off
cd /d "%~dp0"

:loop
python autowatch_gui.py
if %errorlevel% == 10 (
    echo Restarting application...
    goto loop
)

echo Application exited with code %errorlevel%.
