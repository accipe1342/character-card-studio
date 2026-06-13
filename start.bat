@echo off
title Character Card Studio
cd /d "%~dp0"

echo.
echo  Character Card Studio
echo  =====================
echo.

:: ── Python venv ──────────────────────────────────────────────────────────────
if not exist .venv (
    echo [.] Creating Python virtual environment...
    python -m venv .venv
)
call .venv\Scripts\activate.bat

:: ── Python deps (only reinstall if requirements.txt changed) ─────────────────
set REQ_HASH_FILE=.venv\.req_hash
for /f %%i in ('certutil -hashfile requirements.txt MD5 ^| findstr /v "MD5\|CertUtil"') do set REQ_HASH=%%i
set REQ_HASH=%REQ_HASH: =%
set STORED_HASH=none
if exist "%REQ_HASH_FILE%" set /p STORED_HASH=<"%REQ_HASH_FILE%"
if "%REQ_HASH%"=="%STORED_HASH%" (
    echo [OK] Python dependencies up to date.
) else (
    echo [.] Installing Python dependencies...
    pip install -r requirements.txt -q
    echo %REQ_HASH%> "%REQ_HASH_FILE%"
)

:: ── Node deps ─────────────────────────────────────────────────────────────────
if not exist frontend\node_modules (
    echo [.] Installing frontend dependencies...
    cd frontend
    call npm install --silent
    cd ..
)

:: ── Copy .env if missing ──────────────────────────────────────────────────────
if not exist .env (
    if exist _env.example (
        copy _env.example .env >nul
        echo [.] Created .env - add your API keys!
    )
)

:: ── Ensure data/ exists ───────────────────────────────────────────────────────
if not exist data mkdir data

:: ── Start Vite in background, opens browser automatically ────────────────────
echo [.] Starting Vite dev server in background...
start /B "" cmd /c "cd frontend && npm run dev -- --open"
timeout /t 3 /nobreak >nul

:: ── Start Flask in foreground (logs visible here) ────────────────────────────
echo [OK] Flask starting - logs will appear below.
echo      (Close this window to stop everything)
echo.
python backend\app.py
