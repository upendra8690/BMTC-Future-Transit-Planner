@echo off
rem One-time setup for Windows. Creates .venv in the project folder, installs the Python packages,
rem creates .env if it is missing, then creates or upgrades the database and checks it.
rem Needs Python 3.11 or newer. Tick "Add python.exe to PATH" when you install it from python.org.
setlocal
cd /d "%~dp0.."

set "PYEXE="
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if not errorlevel 1 set "PYEXE=python"
if defined PYEXE goto :have_python
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if not errorlevel 1 set "PYEXE=py -3"
if defined PYEXE goto :have_python
echo Python 3.11 or newer was not found.
echo Install Python 3.13 from python.org, tick "Add python.exe to PATH", then run this script again.
exit /b 1

:have_python
echo Using Python through: %PYEXE%

if not exist ".venv\Scripts\python.exe" (
  echo Creating the virtual environment in .venv ...
  %PYEXE% -m venv .venv
  if errorlevel 1 goto :failed
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 goto :failed
python -m pip install --upgrade pip
if errorlevel 1 goto :failed
python -m pip install -r requirements-dev.txt
if errorlevel 1 goto :failed

if not exist ".env" (
  copy /y ".env.example" ".env" >nul
  echo Created .env from .env.example. Open it and set ADMIN_API_KEY before using admin features.
)

echo Preparing the database ...
python scripts\migrate_database.py
if errorlevel 1 goto :failed
python scripts\check_database.py
if errorlevel 1 goto :failed

echo.
echo Setup finished. Next: run scripts\run_tests_windows.bat, then scripts\run_windows.bat
exit /b 0

:failed
echo.
echo Setup stopped with an error. Read the messages above, fix the cause, then run this script again.
exit /b 1
