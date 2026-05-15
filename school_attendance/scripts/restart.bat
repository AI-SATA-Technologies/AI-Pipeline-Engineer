@echo off
cd /d "D:\API ai pipeline engineer\school_attendance"
echo ================================
echo  Restarting Attendance Server
echo ================================
echo.

echo Freeing port 8000 ...
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Write-Host ('  killing PID ' + $_.OwningProcess); Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"

echo.
echo Your local network IP:
powershell -NoProfile -Command "Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.PrefixOrigin -eq 'Dhcp' } | ForEach-Object { Write-Host ('  ' + $_.IPAddress) }"
echo.
echo Server starting on http://0.0.0.0:8000
echo Press Ctrl+C to stop the server.
echo.

call "D:\AI Pipeline Engineer\school_attendance\venv\Scripts\activate.bat"
uvicorn main:app --host 0.0.0.0 --port 8000
pause
