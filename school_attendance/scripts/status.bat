@echo off
echo ================================
echo  Attendance Server Status Check
echo ================================
echo.
powershell -NoProfile -Command "try { $r = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/status' -TimeoutSec 5; Write-Host 'SERVER IS RUNNING' -ForegroundColor Green; Write-Host ('  status           : ' + $r.status); Write-Host ('  mode             : ' + $r.mode); Write-Host ('  students_pending : ' + $r.students_pending); Write-Host ''; $ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.PrefixOrigin -eq 'Dhcp' } | Select-Object -Expand IPAddress) -join ', '; Write-Host ('  LAN address      : http://' + $ip + ':8000') } catch { Write-Host 'SERVER IS NOT RUNNING (no response on port 8000)' -ForegroundColor Red }"
echo.
pause
