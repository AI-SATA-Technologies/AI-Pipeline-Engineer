@echo off
echo Stopping FastAPI server and MySQL...
taskkill /F /IM uvicorn.exe /T 2>NUL
taskkill /F /IM python.exe /FI "WINDOWTITLE eq uvicorn*" /T 2>NUL
"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysqladmin.exe" -u root -pschool2024 shutdown 2>NUL
echo Done.
