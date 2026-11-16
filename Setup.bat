@echo off
title Jarvis Setup
cd /d "%~dp0"
echo Installing Jarvis with Python 3.12 ...
py -3.12 setup.py
echo.
echo Done. Now run Jarvis.bat
pause
