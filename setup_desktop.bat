@echo off
REM Mutagenesis Intelligence System - Desktop Setup Script
REM This script sets up the environment for the desktop app

echo ========================================
echo Mutagenesis Intelligence System
echo Desktop Setup
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo.
    echo Please install Python 3.8+ from https://www.python.org/
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

echo Python found:
python --version
echo.

REM Check if pip is available
python -m pip --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: pip is not available
    pause
    exit /b 1
)

echo Installing required packages...
echo This may take a few minutes...
echo.

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo ERROR: Failed to install some packages
    echo You may need to install them manually.
    pause
    exit /b 1
)

echo.
echo ========================================
echo Setup complete!
echo ========================================
echo.
echo You can now run the app using:
echo   launch_app.bat
echo.
echo Or double-click launch_app.bat to start.
echo.
pause

