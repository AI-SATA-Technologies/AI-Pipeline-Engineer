@echo off
echo ================================
echo  Restarting Attendance Server
echo ================================
echo.

for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
    echo Killing old process on port 8000 (PID %%p)
    taskkill /F /PID %%p >nul 2>&1
)

echo.
echo Your local network IP:
ipconfig | findstr /i "IPv4"
echo.
echo Server starting on http://0.0.0.0:8000
echo Press Ctrl+C to stop the server.
echo.

call "D:\AI Pipeline Engineer\school_attendance\venv\Scripts\activate.bat"
uvicorn main:app --host 0.0.0.0 --port 8000
