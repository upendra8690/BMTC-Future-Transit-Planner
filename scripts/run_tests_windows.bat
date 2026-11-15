@echo off
rem Runs the automated test suite. Prints the number of passed and failed tests at the end.
setlocal
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
  echo Run scripts\setup_windows.bat first.
  exit /b 1
)

call ".venv\Scripts\activate.bat"
python -m pytest
