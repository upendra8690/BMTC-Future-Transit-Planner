@echo off
rem Makes a verified backup of the planner database. Default folder: BACKUP_DIR from .env, or data\backups.
rem To choose another folder:  scripts\backup_windows.bat --out "D:\BMTC-backups"
setlocal
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
  echo Run scripts\setup_windows.bat first.
  exit /b 1
)

call ".venv\Scripts\activate.bat"
python scripts\backup_database.py %*
if errorlevel 1 (
  echo The backup failed. Read the message above.
  exit /b 1
)
echo Backup written and checked.
exit /b 0
