@echo off
title SmartExpenseAgent
echo ============================================
echo   SmartExpenseAgent - Starting...
echo ============================================
echo.

cd /d C:\Agent_IA
call venv\Scripts\activate

echo Agent is running. Press Ctrl+C to stop.
echo Logs available in app.log
echo.

python main.py

echo.
echo Agent stopped.
pause