@echo off
title WN Scene Mill
cd /d "%~dp0"
py -3 "%~dp0wn-scene-mill.py"
if errorlevel 1 python "%~dp0wn-scene-mill.py"
pause
