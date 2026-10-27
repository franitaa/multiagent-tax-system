@echo off
cd /d "%~dp0"
python start.py
if errorlevel 1 (
  echo.
  echo Startup failed. Read the message above.
  pause
)
