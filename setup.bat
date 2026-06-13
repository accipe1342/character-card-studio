@echo off
title Character Card Studio — Setup
cd /d "%~dp0"

echo.
echo  ============================================
echo   Character Card Studio — First Time Setup
echo  ============================================
echo.

:: ── Check Python ─────────────────────────────────────────────────────────────
echo [1/5] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [!] Python not found.
    echo.
    echo  Please install Python 3.10 or later from:
    echo  https://www.python.org/downloads/
    echo.
    echo  IMPORTANT: During install, check the box that says
    echo  "Add Python to PATH" before clicking Install.
    echo.
    pause
    exit /b 1
)
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo  [OK] Python %PY_VER% found.

:: ── Check Node ────────────────────────────────────────────────────────────────
echo.
echo [2/5] Checking Node.js...
node --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [!] Node.js not found.
    echo.
    echo  Please install Node.js LTS from:
    echo  https://nodejs.org/
    echo.
    echo  After installing, close this window and run setup.bat again.
    echo.
    pause
    exit /b 1
)
for /f %%v in ('node --version') do set NODE_VER=%%v
echo  [OK] Node.js %NODE_VER% found.

:: ── Create Python venv ────────────────────────────────────────────────────────
echo.
echo [3/5] Creating Python virtual environment...
if exist .venv (
    echo  [OK] Virtual environment already exists, skipping.
) else (
    python -m venv .venv
    if errorlevel 1 (
        echo  [!] Failed to create virtual environment.
        echo      Try running: python -m pip install virtualenv
        pause
        exit /b 1
    )
    echo  [OK] Virtual environment created.
)

:: ── Install Python deps ───────────────────────────────────────────────────────
echo.
echo [4/5] Installing Python dependencies...
call .venv\Scripts\activate.bat
pip install -r requirements.txt -q
if errorlevel 1 (
    echo  [!] Failed to install Python dependencies.
    pause
    exit /b 1
)
:: Save hash so start.bat skips reinstall
for /f %%i in ('certutil -hashfile requirements.txt MD5 ^| findstr /v "MD5\|CertUtil"') do set REQ_HASH=%%i
set REQ_HASH=%REQ_HASH: =%
echo %REQ_HASH%> .venv\.req_hash
echo  [OK] Python dependencies installed.

:: ── Install Node deps ─────────────────────────────────────────────────────────
echo.
echo [5/5] Installing frontend dependencies...
cd frontend
call npm install
if errorlevel 1 (
    echo  [!] Failed to install frontend dependencies.
    cd ..
    pause
    exit /b 1
)
cd ..
echo  [OK] Frontend dependencies installed.

:: ── Create data dir ───────────────────────────────────────────────────────────
if not exist data mkdir data

:: ── Copy .env ─────────────────────────────────────────────────────────────────
if not exist .env (
    if exist _env.example (
        copy _env.example .env >nul
        echo.
        echo  [!] A .env file has been created from the example.
        echo      Open .env in a text editor and add your API keys
        echo      before launching the app.
    )
) else (
    echo.
    echo  [OK] .env already exists.
)

:: ── Make start.sh executable (for WSL users) ─────────────────────────────────
:: Not needed on Windows but harmless

:: ── Done ──────────────────────────────────────────────────────────────────────
echo.
echo  ============================================
echo   Setup complete!
echo  ============================================
echo.
echo  Next steps:
echo    1. Open .env and add your API keys
echo    2. Double-click start.bat to launch the app
echo.
pause
