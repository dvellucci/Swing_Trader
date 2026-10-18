@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Creating Python virtual environment...
    py -3 -m venv .venv
    if errorlevel 1 (echo Python 3.10 or newer is required. & pause & exit /b 1)
)
".venv\Scripts\python.exe" -c "import sys; assert sys.version_info >= (3,10), 'Python 3.10+ required'"
if errorlevel 1 (echo Python 3.10 or newer is required. & pause & exit /b 1)
".venv\Scripts\python.exe" -c "import customtkinter, pandas, numpy, yfinance, exchange_calendars, tzdata"
if errorlevel 1 (
    echo Installing GUI and strategy dependencies...
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (echo Dependency installation failed. Check your internet connection. & pause & exit /b 1)
)
".venv\Scripts\python.exe" -m trading_gui
if errorlevel 1 pause
