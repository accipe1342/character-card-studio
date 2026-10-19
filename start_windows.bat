@echo off
rem Old launcher kept for people who still double-click it. It used to run "python app.py" from the
rem wrong folder. start.bat is the real launcher (venv, dependencies, backend + frontend).
cd /d "%~dp0"
echo This launcher is outdated - starting start.bat instead...
call start.bat
