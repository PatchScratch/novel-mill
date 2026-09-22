@echo off
title Novel Mill OCR
cd /d "%~dp0"
py -3 "%~dp0wn-ocr.py"
if errorlevel 1 python "%~dp0wn-ocr.py"
pause
