@echo off
setlocal
title Blackboard Automate Launcher

cd /d "%~dp0"

:: Check if standalone exe was already built locally
if exist "%~dp0dist\BlackboardAutomate.exe" (
    start "" "%~dp0dist\BlackboardAutomate.exe"
    exit /b 0
)

:: Locate Python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [!] Python was not found on your system.
    echo Please install Python 3.10+ from https://www.python.org/downloads/
    echo ^(Make sure to check "Add Python to PATH" during installation^)
    pause
    exit /b 1
)

:: Create virtual environment on first run
if not exist ".venv\Scripts\python.exe" (
    echo [*] Setting up Blackboard Automate environment for first run...
    python -m venv .venv
    call ".venv\Scripts\pip.exe" install --upgrade pip
    call ".venv\Scripts\pip.exe" install -r requirements.txt
)

echo [*] Launching Blackboard Automate...
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" run.py --app-window
) else (
    ".venv\Scripts\python.exe" run.py --app-window
)
