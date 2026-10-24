@echo off
setlocal
title Build BlackboardAutomate.exe for Windows

cd /d "%~dp0"

echo ===============================================================
echo   Building Standalone BlackboardAutomate.exe for Windows
echo ===============================================================

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [!] Python is required to build the .exe.
    echo Install Python from https://www.python.org/downloads/
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [*] Creating build virtual environment...
    python -m venv .venv
)

echo [*] Installing dependencies and PyInstaller...
call ".venv\Scripts\pip.exe" install --upgrade pip
call ".venv\Scripts\pip.exe" install -r requirements.txt pyinstaller pywebview

echo [*] Packaging BlackboardAutomate.exe...
call ".venv\Scripts\python.exe" build_windows.py

echo.
echo ===============================================================
echo   Done! Share 'dist\BlackboardAutomate.exe' with your friends!
echo ===============================================================
pause
