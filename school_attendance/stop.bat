@echo off
echo ================================
echo  Stopping Attendance Server
echo ================================
echo.

set FOUND=0
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
    echo Killing process on port 8000 (PID %%p)
    taskkill /F /PID %%p >nul 2>&1
    set FOUND=1
)

if "%FOUND%"=="0" (
    echo No server running on port 8000.
) else (
    echo Server stopped.
)
echo.
pause
