@echo off
title Novel Mill
cd /d "%~dp0"
py -3 "%~dp0wn-local-mill.py"
if errorlevel 1 python "%~dp0wn-local-mill.py"
pause
