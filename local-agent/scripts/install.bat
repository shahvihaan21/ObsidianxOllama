@echo off
echo ==========================================
echo Local Agent Installer
echo ==========================================

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [FAIL] Python is not installed or not in PATH.
    pause
    exit /b 1
)
echo [OK] Python is installed.

REM Check Ollama
ollama --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [FAIL] Ollama is not installed or not in PATH.
    pause
    exit /b 1
)
echo [OK] Ollama is installed.

REM Create virtual environment
if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
)
echo [OK] Virtual environment exists.

REM Install dependencies
echo Installing dependencies...
call venv\Scripts\activate.bat
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [FAIL] Failed to install dependencies.
    pause
    exit /b 1
)
echo [OK] Dependencies installed.

echo.
echo Installation complete.
echo You can now run "start.bat" to launch the agent.
pause
