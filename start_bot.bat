@echo off
REM ============================================================
REM  Tawwat Chess News Bot - Windows launcher
REM  NOTE: keep this file ASCII only (Arabic in .bat breaks).
REM ============================================================
chcp 65001 >nul
title Tawwat Chess News Bot

echo.
echo  == Tawwat Chess :: News Bot ==
echo.

REM --- check python ---
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Install Python 3.10+ from https://www.python.org/downloads/
    pause
    exit /b 1
)

REM --- ask for port (default 8080) ---
set "PORT=8080"
set /p PORT=Enter status-page port [default 8080]: 
if "%PORT%"=="" set "PORT=8080"
echo Using port %PORT%

REM --- check .env ---
if not exist ".env" (
    echo [WARN] .env file not found.
    echo Copy .env.example to .env and fill your keys first.
    pause
    exit /b 1
)

REM --- install requirements ---
echo [1/2] Installing requirements...
python -m pip install -r requirements.txt --quiet

REM --- run bot ---
echo [2/2] Starting bot...
python bot.py

pause
