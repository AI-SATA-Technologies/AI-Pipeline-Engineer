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
echo Closing camera viewer (viewer.py) if running...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*viewer.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host ('Viewer closed (PID ' + $_.ProcessId + ')') }"

echo.
pause
