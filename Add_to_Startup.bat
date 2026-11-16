@echo off
cd /d "%~dp0"
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Startup')+'\Jarvis.lnk'); $s.TargetPath='%~dp0Jarvis.bat'; $s.WorkingDirectory='%~dp0'; $s.WindowStyle=7; $s.Save()"
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\Jarvis.lnk'); $s.TargetPath='%~dp0Jarvis.bat'; $s.WorkingDirectory='%~dp0'; $s.IconLocation='%~dp0config\jarvis.ico'; $s.Save()"
echo Desktop shortcut and Startup entry created.
pause
