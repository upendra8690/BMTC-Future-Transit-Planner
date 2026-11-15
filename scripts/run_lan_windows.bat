@echo off
rem Starts the planner so that phones on the SAME Wi-Fi network can open it. Read the warning before you confirm.
setlocal
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
  echo Run scripts\setup_windows.bat first.
  exit /b 1
)

echo.
echo WARNING: this makes the planner reachable by every device on the Wi-Fi network this PC is on.
echo - Traffic is plain HTTP. Other devices on the same network can read it, including any admin key you type.
echo - Use this only on a network you trust, such as your own home Wi-Fi. Never on public Wi-Fi.
echo - Phones cannot use "near me" over plain HTTP. docs\PHONE_ACCESS.md explains the HTTPS option.
echo - Windows may ask whether to allow Python through the firewall. Allow it on private networks only.
echo.
set "CONFIRM="
set /p "CONFIRM=Type YES to start the planner for this network, or press Enter to cancel: "
if /i not "%CONFIRM%"=="YES" (
  echo Cancelled. Nothing was started.
  exit /b 0
)

call ".venv\Scripts\activate.bat"
echo.
echo On this PC, open http://127.0.0.1:8000/
echo On a phone on the same Wi-Fi, open http://THIS-PC-ADDRESS:8000/  (find the address with ipconfig)
echo Press Ctrl+C in this window to stop.
python -m uvicorn app.main:create_app --factory --app-dir backend --host 0.0.0.0 --port 8000
