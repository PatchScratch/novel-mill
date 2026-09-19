@echo off
title WN Raw Split
cd /d "%~dp0"
py -3 "%~dp0wn-raw-split.py"
if errorlevel 1 python "%~dp0wn-raw-split.py"
pause
