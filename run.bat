@echo off
REM Change directory to where your script is located
cd /d "%~dp0"

REM Run the Python script with arguments
set ROOT_PROJECT=D:\\ITSTeam\\NewGen\\autowatcher_vale
set GITHUB_TOKEN=
python autowatch_gui.py --dataset CustomAWGN30ES15 --model "" --Device cpu --test

pause