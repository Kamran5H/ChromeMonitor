@echo off
echo Installing Chrome Monitor to Windows Startup...

:: Use PowerShell to create a shortcut in the Startup folder pointing to start_monitor.vbs
powershell -NoProfile -Command "$s = (New-Object -ComObject WScript.Shell).CreateShortcut(\"$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\ChromeMonitor.lnk\"); $s.TargetPath = \"%~dp0start_monitor.vbs\"; $s.WorkingDirectory = \"%~dp0\"; $s.Save();"

echo Chrome Monitor has been successfully configured to run at startup.
echo Starting the monitor in the background...

:: Launch the monitor immediately using wscript (silently)
wscript.exe "%~dp0start_monitor.vbs"

echo Chrome Monitor is now running.
pause
