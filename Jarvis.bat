@echo off
title Jarvis
cd /d "%~dp0"
py -3.12 main.py
if errorlevel 1 pause
