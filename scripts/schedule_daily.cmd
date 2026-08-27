@echo off
REM Daily batch update — runs every morning to keep reports fresh
REM Schedule: Windows Task Scheduler, daily at 8:00 AM
REM
REM To set up: run scripts/setup_scheduler.ps1 as Administrator
REM Or manually: Task Scheduler > Create Task > Trigger: Daily 8:00 AM
REM              > Action: Start a program > This file

cd /d D:\AI_Investment_System

REM Windows console may be GBK; force UTF-8 so Chinese output doesn't garble/crash
set PYTHONIOENCODING=utf-8

echo ============================================================
echo  AI Investment System — Daily Batch Update
echo  Started: %date% %time%
echo ============================================================

REM Activate venv
call .venv\Scripts\activate.bat

echo.
echo [1/2] Generating company catalyst calendar (earnings + 8-K events)...
python scripts\catalyst_calendar.py --forward 60 --lookback 14

echo.
echo [2/2] Updating oldest company reports...
python scripts\batch_update_reports.py --count 5

echo.
echo ============================================================
echo  Daily update complete: %date% %time%
echo ============================================================
