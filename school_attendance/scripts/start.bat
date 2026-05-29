@echo off
cd /d "%~dp0.."
echo ================================
echo  School Face Attendance Server
echo ================================
echo.

if not exist ".env" (
    echo ERROR: .env file not found.
    echo Copy .env.example to .env and fill in your credentials.
    echo.
    pause
    exit /b 1
)

echo Your local network IP:
ipconfig | findstr /i "IPv4"
echo.
echo Server starting on http://0.0.0.0:8000
echo Use the IPv4 address above to access from other devices.
echo.
echo Press Ctrl+C to stop the server.
echo.

if not exist "%~dp0..\venv\Scripts\activate.bat" (
    echo ERROR: venv not found at "%~dp0..\venv".
    echo Create it with:  python -m venv venv  ^&^&  venv\Scripts\pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)
call "%~dp0..\venv\Scripts\activate.bat"
uvicorn main:app --host 0.0.0.0 --port 8000
