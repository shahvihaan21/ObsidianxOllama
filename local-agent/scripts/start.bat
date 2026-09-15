@echo off
echo ==========================================
echo Starting Local Agent
echo ==========================================

call venv\Scripts\activate.bat >nul 2>&1

python main.py
pause
