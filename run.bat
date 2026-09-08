@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

if "%PORT%"=="" set PORT=8000

if not exist .env (
    if exist .env.example (
        echo Creating .env from .env.example...
        copy .env.example .env >nul
    ) else (
        echo Creating empty .env...
        type nul > .env
    )
    echo [!] Please configure your API key in .env (OpenAI, Google, or Anthropic).
)

set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" (
    echo Creating virtualenv...
    python -m venv .venv
    if not exist "%PY%" (
        echo Error: Python is not installed or not in PATH.
        exit /b 1
    )
)

"%PY%" -m pip install -q -r requirements.txt

rem Free the port if it is already in use
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":%PORT%" ^| findstr "LISTENING" 2^>nul') do (
    echo Stopping stale server on port %PORT% (PID %%a)...
    taskkill /f /pid %%a >nul 2>&1
)

"%PY%" app.py
