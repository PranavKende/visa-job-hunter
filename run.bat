@echo off
REM Windows Task Scheduler launcher for job-hunter
REM Schedule this task to run daily at 7:00 AM IST (1:30 AM UTC, adjust for your timezone)
REM
REM To add to Task Scheduler:
REM   1. Open Task Scheduler → Create Basic Task
REM   2. Trigger: Daily, start time 07:00
REM   3. Action: Start a program → browse to this .bat file
REM   4. Check "Run whether user is logged on or not"

cd /d "%~dp0"

REM Activate venv if it exists
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

REM Load .env and run
python -m src.main >> logs\run.log 2>&1

if %ERRORLEVEL% NEQ 0 (
    echo Job hunter failed with exit code %ERRORLEVEL% >> logs\run.log
)
