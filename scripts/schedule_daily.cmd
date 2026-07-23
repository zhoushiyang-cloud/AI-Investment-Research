@echo off
REM Daily batch update — runs every morning to keep reports fresh
REM Schedule: Windows Task Scheduler, daily at 8:00 AM
REM
REM To set up: run scripts/setup_scheduler.ps1 as Administrator
REM Or manually: Task Scheduler > Create Task > Trigger: Daily 8:00 AM
REM              > Action: Start a program > This file

cd /d D:\AI_Investment_System

echo ============================================================
echo  AI Investment System — Daily Batch Update
echo  Started: %date% %time%
echo ============================================================

REM Activate venv and run batch update
call .venv\Scripts\activate.bat
python scripts\batch_update_reports.py --count 5

echo.
echo ============================================================
echo  Daily update complete: %date% %time%
echo ============================================================
