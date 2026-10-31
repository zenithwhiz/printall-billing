@echo off
cd /d "%~dp0"
if not exist .venv (
  echo Creating a local Python environment...
  py -m venv .venv
)
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo Installation failed. Check that Python is installed and internet is available for first-time setup.
  pause
  exit /b 1
)
start "" http://127.0.0.1:5000
python app.py
pause
