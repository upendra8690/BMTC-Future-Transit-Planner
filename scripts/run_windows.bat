@echo off
rem Starts the planner for this PC only, at http://127.0.0.1:8000/. Press Ctrl+C in this window to stop it.
setlocal
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
  echo Run scripts\setup_windows.bat first.
  exit /b 1
)

call ".venv\Scripts\activate.bat"
echo Open http://127.0.0.1:8000/ in your browser. Press Ctrl+C here to stop.
python -m uvicorn app.main:create_app --factory --app-dir backend --host 127.0.0.1 --port 8000
