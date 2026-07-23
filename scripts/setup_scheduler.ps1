# setup_scheduler.ps1 — Create Windows Task Scheduler job for daily 8AM report updates
# Run as Administrator: Right-click PowerShell → Run as Administrator
# Then: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
# Then: .\scripts\setup_scheduler.ps1

$TaskName = "AI_Investment_Daily_Update"
$ScriptPath = "D:\AI_Investment_System\scripts\schedule_daily.cmd"
$WorkingDir = "D:\AI_Investment_System"

# Remove existing task if present
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# Create trigger: Daily at 8:00 AM
$Trigger = New-ScheduledTaskTrigger -Daily -At 8:00AM

# Create action: Run the batch script
$Action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$ScriptPath`"" -WorkingDirectory $WorkingDir

# Settings: don't run if missed, stop after 2 hours, wake computer to run
$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -WakeToRun `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries

# Run as current user
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

# Register the task
Register-ScheduledTask -TaskName $TaskName `
    -Trigger $Trigger `
    -Action $Action `
    -Settings $Settings `
    -Principal $Principal `
    -Description "Daily 8AM batch update of AI investment research reports — updates 5 oldest companies, rebuilds portal, pushes to GitHub" `
    -Force

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Daily scheduler installed!" -ForegroundColor Green
Write-Host "  Task: $TaskName" -ForegroundColor Green
Write-Host "  Time: Every day at 8:00 AM" -ForegroundColor Green
Write-Host "  Script: $ScriptPath" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "To test: schtasks /run /tn '$TaskName'"
Write-Host "To check: schtasks /query /tn '$TaskName' /v"
Write-Host "To remove: Unregister-ScheduledTask -TaskName '$TaskName'"
Write-Host ""
