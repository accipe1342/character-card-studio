@echo off
title Character Card Studio
cd /d "%~dp0"

echo.
echo  Character Card Studio
echo  =====================
echo.

if not exist data mkdir data
if not exist .env if exist .env.example copy .env.example .env >nul

if not exist "python\python.exe" (
    echo  [!] python\python.exe is missing. Unzip the whole folder, not just the .bat.
    pause
    exit /b 1
)

echo  [.] Starting - your browser will open at http://localhost:5000
echo      Keep this window open while you use the app. Close it to stop.
echo.

set CCS_OPEN_BROWSER=1
python\python.exe backend\app.py
if errorlevel 1 (
    echo.
    echo  [!] The app stopped with an error. The message is above.
    pause
)
