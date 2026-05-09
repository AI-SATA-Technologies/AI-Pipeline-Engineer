@echo off
echo ===================================
echo  School Face Attendance System
echo ===================================

if not exist ".env" (
    echo WARNING: .env file not found.
    echo Copy .env.example to .env and fill in your MySQL credentials.
    echo.
    pause
    exit /b 1
)

echo [1/2] Starting MySQL...
call "%~dp0start_mysql.bat"

echo [2/2] Starting FastAPI server on http://localhost:8000 ...
echo.
echo  Open in browser:
echo    http://localhost:8000/static/register.html    (Register students)
echo    http://localhost:8000/static/dashboard.html   (Attendance dashboard)
echo    http://localhost:8000/docs                    (API docs)
echo.
echo Press Ctrl+C to stop.
echo.

call venv\Scripts\activate
uvicorn main:app --host 0.0.0.0 --port 8000
