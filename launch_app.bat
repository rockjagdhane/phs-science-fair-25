@echo off
REM Mutagenesis Intelligence System - Desktop Launcher
REM This script launches the Streamlit app in your default browser

echo ========================================
echo Mutagenesis Intelligence System
echo Desktop Launcher
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://www.python.org/
    pause
    exit /b 1
)

REM Check if streamlit is installed
python -c "import streamlit" >nul 2>&1
if errorlevel 1 (
    echo Streamlit not found. Installing dependencies...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo ERROR: Failed to install dependencies
        pause
        exit /b 1
    )
)

REM Change to scripts directory
cd /d "%~dp0scripts"

REM Launch Streamlit app
echo Starting Mutagenesis Intelligence System...
echo The app will open in your default browser.
echo.
echo To stop the app, press Ctrl+C in this window.
echo.

streamlit run app.py --server.headless true

pause

