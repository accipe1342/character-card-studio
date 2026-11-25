@echo off
title Character Card Studio
cd /d "%~dp0"

echo.
echo  Character Card Studio
echo  =====================
echo.

:: -- Python venv -------------------------------------------------------------
:: The venv's own python.exe is used directly. Calling activate.bat would trust the
:: path baked into it when it was created, which breaks if the folder is renamed.
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" (
    echo [.] Creating Python virtual environment...
    python -m venv .venv
)
"%PY%" -c "import sys" >nul 2>&1
if errorlevel 1 (
    echo [!] The virtual environment in .venv does not work - building it again...
    rmdir /s /q .venv
    python -m venv .venv
    if errorlevel 1 (
        echo [!] Could not create a virtual environment. Is Python 3.10+ installed and on PATH?
        pause
        exit /b 1
    )
    del /q ".venv\.req_hash" >nul 2>&1
)

:: -- Python deps (only reinstall if requirements.txt changed) -----------------
set REQ_HASH_FILE=.venv\.req_hash
for /f %%i in ('certutil -hashfile requirements.txt MD5 ^| findstr /v "MD5\|CertUtil"') do set REQ_HASH=%%i
set REQ_HASH=%REQ_HASH: =%
set STORED_HASH=none
if exist "%REQ_HASH_FILE%" set /p STORED_HASH=<"%REQ_HASH_FILE%"
"%PY%" -c "import flask" >nul 2>&1
if errorlevel 1 set STORED_HASH=missing
if "%REQ_HASH%"=="%STORED_HASH%" (
    echo [OK] Python dependencies up to date.
) else (
    echo [.] Installing Python dependencies...
    "%PY%" -m pip install -r requirements.txt -q
    if errorlevel 1 (
        echo [!] Installing the Python dependencies failed. The message is above.
        pause
        exit /b 1
    )
    echo %REQ_HASH%> "%REQ_HASH_FILE%"
)

:: -- Node deps ---------------------------------------------------------------
set PKG_HASH_FILE=frontend\node_modules\.pkg_hash
for /f %%i in ('certutil -hashfile frontend\package.json MD5 ^| findstr /v "MD5\|CertUtil"') do set PKG_HASH=%%i
set PKG_HASH=%PKG_HASH: =%
set STORED_PKG=none
if exist "%PKG_HASH_FILE%" set /p STORED_PKG=<"%PKG_HASH_FILE%"
if not exist frontend\node_modules set STORED_PKG=missing
if "%PKG_HASH%"=="%STORED_PKG%" (
    echo [OK] Frontend dependencies up to date.
) else (
    echo [.] Installing frontend dependencies...
    cd frontend
    call npm install --silent
    cd ..
    echo %PKG_HASH%> "%PKG_HASH_FILE%"
)

:: -- Copy .env if missing ----------------------------------------------------
if not exist .env (
    if exist _env.example (
        copy _env.example .env >nul
        echo [.] Created .env - add your API keys!
    )
)

:: -- Ensure data/ exists -----------------------------------------------------
if not exist data mkdir data

:: -- Start Vite, then open the app window (OPEN_AS=tab in .env for a browser tab)
echo [.] Starting Vite dev server in background...
start /B "" cmd /c "cd frontend && npm run dev"
start /B "" powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\open_app_window.ps1" -Url "http://localhost:5173"

:: -- Start Flask in the foreground (logs visible here) ------------------------
echo [OK] Flask starting - logs will appear below.
echo      The app is at http://localhost:5173 if no window opens by itself.
echo      (Close this window to stop everything)
echo.
"%PY%" backend\app.py
if errorlevel 1 (
    echo.
    echo [!] The app stopped with an error. The message is above.
    pause
)
