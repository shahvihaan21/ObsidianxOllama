@echo off
echo ==========================================
echo Local Agent Diagnostics
echo ==========================================

call venv\Scripts\activate.bat >nul 2>&1

echo.
echo [1] Checking Python...
python --version

echo.
echo [2] Checking Ollama...
ollama --version

echo.
echo [3] Running Smoke Tests...
python tests\smoke_ollama.py

echo.
echo [4] Running Agent Loop Smoke Test...
python tests\smoke_agent_loop.py

echo.
echo Diagnostics complete.
pause
