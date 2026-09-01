@echo off
echo Stopping Chrome Monitor...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*chrome_monitor.py*' } | ForEach-Object { Stop-Process $_.ProcessId -Force; Write-Host 'Stopped Chrome Monitor process with PID' $_.ProcessId }"
echo Chrome Monitor stopped.
pause
