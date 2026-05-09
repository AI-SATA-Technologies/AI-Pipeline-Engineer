@echo off
echo Starting MySQL Server...
tasklist /FI "IMAGENAME eq mysqld.exe" 2>NUL | find /I "mysqld.exe" >NUL
if "%ERRORLEVEL%"=="0" (
    echo MySQL is already running.
    goto done
)
start /B "" "C:\Program Files\MySQL\MySQL Server 8.4\bin\mysqld.exe" --defaults-file="C:\ProgramData\MySQL\my.ini"
timeout /t 5 /nobreak >NUL
netstat -an | find ":3306" >NUL
if "%ERRORLEVEL%"=="0" (
    echo MySQL started successfully on port 3306.
) else (
    echo MySQL may not be running. Check the logs.
)
:done
