@echo off
title Novel Mill EPUB
cd /d "%~dp0"
py -3 "%~dp0wn-epub-extract.py"
if errorlevel 1 python "%~dp0wn-epub-extract.py"
pause
