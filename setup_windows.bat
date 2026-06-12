@echo off
cd /d "%~dp0"

echo [1/4] Creating Python virtual environment...
py -m venv .venv
call .venv\Scripts\activate.bat

echo [2/4] Installing Python dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt

echo [3/4] Installing Node dependencies...
cd frontend
npm install
cd ..

echo [4/4] Setting up environment...
if not exist .env copy _env.example .env

echo.
echo Setup complete! Run start_windows.bat to launch the app.
pause