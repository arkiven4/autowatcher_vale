@echo off
REM Change directory to where your script is located
cd /d "%~dp0"

REM Run the Python script with arguments
REM dev prod
set AUTOWATCH_ENV=dev
set ROOT_PROJECT=D:\\ITSTeam\\NewGen
set GITHUB_TOKEN=
python autowatch_gui.py --dataset CustomAWGN30ES15 --model "" --Device cpu --test

pause