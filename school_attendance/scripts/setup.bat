@echo off
setlocal EnableExtensions
title School Face Attendance - Setup
rem ===========================================================================
rem  One-click setup for a new PC.
rem
rem    Double-click this file, or run:   scripts\setup.bat [--dev] [--no-prompt]
rem      --dev        also install test/lint tools and run the test suite
rem      --no-prompt  never open Notepad or ask questions (unattended setup)
rem
rem  Safe to run again at any time: every step skips what is already done.
rem  Works from any folder - all paths are relative to this script.
rem ===========================================================================

cd /d "%~dp0.."
set "APP_DIR=%CD%"
set "DEV="
set "NO_PROMPT="
for %%A in (%*) do (
    if /i "%%~A"=="--dev" set "DEV=1"
    if /i "%%~A"=="--no-prompt" set "NO_PROMPT=1"
)

echo ===========================================================
echo   School Face Attendance - Setup
echo ===========================================================
echo   Project folder: %APP_DIR%
echo.

rem ---- 1. Python -------------------------------------------------------------
echo [1/7] Looking for Python 3.11 - 3.14, 64-bit ...
rem First pass skips the Microsoft Store Python: it runs sandboxed and can fail
rem to create virtual environments. It is used only if nothing else is installed.
set "PY="
set "SETUP_ALLOW_STORE="
for %%C in ("py -3.13" "py -3.12" "py -3.11" "py -3.14" "python") do (
    if not defined PY call :try_python %%~C
)
if not defined PY (
    set "SETUP_ALLOW_STORE=1"
    for %%C in ("py -3.13" "py -3.12" "py -3.11" "py -3.14" "python") do (
        if not defined PY call :try_python %%~C
    )
)
if not defined PY goto :no_python
for /f "delims=" %%v in ('%PY% -c "import sys; print(sys.version.split()[0])"') do set "PYVER=%%v"
echo   using %PY%  - Python %PYVER%
if defined SETUP_ALLOW_STORE (
    echo   WARNING: this is the Microsoft Store Python. If creating the venv fails,
    echo   install Python from https://www.python.org/downloads/windows/ instead.
)
%PY% scripts\setup_helper.py check-path
if errorlevel 1 goto :fail
echo.

rem ---- 2. Virtual environment --------------------------------------------------
echo [2/7] Virtual environment ...
if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" -c "import sys" >nul 2>&1
    if errorlevel 1 (
        echo   existing venv does not work here - probably copied from another PC. Recreating ...
        rmdir /s /q "venv"
    ) else (
        echo   venv already exists - reusing it
    )
)
if not exist "venv\Scripts\python.exe" (
    echo   creating venv ...
    %PY% -m venv venv
    if errorlevel 1 goto :venv_failed
)
set "VPY=%APP_DIR%\venv\Scripts\python.exe"
echo.

rem ---- 3. Python packages ------------------------------------------------------
echo [3/7] Installing Python packages - first run takes a few minutes ...
"%VPY%" -m pip install --upgrade pip --disable-pip-version-check -q
if errorlevel 1 goto :pip_failed
set "REQ=requirements.txt"
if defined DEV set "REQ=requirements-dev.txt"
"%VPY%" -m pip install -r "%REQ%" --disable-pip-version-check
if errorlevel 1 goto :pip_failed
echo.

rem ---- 4. Configuration (.env) -------------------------------------------------
echo [4/7] Configuration file .env ...
if exist ".env" (
    echo   .env already exists - keeping your settings
    goto :check_env
)
"%VPY%" scripts\setup_helper.py init-env
if errorlevel 1 goto :fail
if defined NO_PROMPT goto :check_env
echo.
echo   Notepad will now open .env. Fill in at least:
echo     DB_USER and DB_PASS  - your PostgreSQL login
echo     LMS_API_URL          - where attendance is sent
echo     ATTENDANCE_TZ        - the school's timezone, e.g. Asia/Karachi
echo     CAMERA_URL           - optional: rtsp://admin:PASSWORD@CAMERA-IP:554/Streaming/Channels/101
echo   Then SAVE and CLOSE Notepad to continue.
start "" /wait notepad ".env"
:check_env
"%VPY%" scripts\setup_helper.py check-env
if errorlevel 1 (
    echo   Fix .env and run setup.bat again.
    goto :fail
)
echo.

rem ---- 5. Face models ----------------------------------------------------------
echo [5/7] Face recognition models - about 300 MB download the first time ...
"%VPY%" download_models.py
if errorlevel 1 goto :fail
echo.

rem ---- 6. Database -------------------------------------------------------------
echo [6/7] PostgreSQL database ...
set "DB_WARN="
"%VPY%" scripts\setup_helper.py db
if errorlevel 1 set "DB_WARN=1"
echo.

rem ---- 7. Self-check -----------------------------------------------------------
echo [7/7] Checking that the face pipeline loads ...
"%VPY%" scripts\setup_helper.py smoke
if errorlevel 1 goto :fail
if not defined DEV goto :shortcuts
echo   running the test suite ...
"%VPY%" -m pytest
if errorlevel 1 goto :fail

:shortcuts
echo.
if defined NO_PROMPT goto :summary
choice /c YN /n /m "Create desktop shortcuts for Start / Stop / Status / Viewer? [Y/N] "
if errorlevel 2 goto :summary
powershell -NoProfile -Command "$d=[Environment]::GetFolderPath('Desktop'); $w=New-Object -ComObject WScript.Shell; foreach($n in 'start','stop','status','viewer'){ $l=$w.CreateShortcut((Join-Path $d ('Attendance - ' + $n + '.lnk'))); $l.TargetPath=(Join-Path $env:APP_DIR ('scripts\' + $n + '.bat')); $l.WorkingDirectory=$env:APP_DIR; $l.Save() }; Write-Host '  shortcuts created on the desktop'"

:summary
echo.
echo ===========================================================
if defined DB_WARN (
    echo   SETUP FINISHED WITH A WARNING
    echo   The database is not ready - see step 6 above. Install or start
    echo   PostgreSQL, check DB_USER / DB_PASS in .env, then run setup.bat again.
) else (
    echo   SETUP COMPLETE
)
echo ===========================================================
echo   Start the server :  scripts\start.bat
echo   Check status     :  scripts\status.bat
echo   API docs         :  http://localhost:8000/docs
echo   Settings         :  %APP_DIR%\.env
echo.
echo   For the LMS on other PCs to reach this server, allow port 8000 once.
echo   Run this in a terminal opened "as Administrator":
echo     netsh advfirewall firewall add rule name="School Attendance API" dir=in action=allow protocol=TCP localport=8000
echo.
if not defined NO_PROMPT pause
exit /b 0

rem ---- helpers -----------------------------------------------------------------
:try_python
rem Usable if it runs, is 3.11-3.14, is 64-bit and (first pass) is not the Store Python.
%* -c "import os, sys, struct; v = sys.version_info[:2]; store = 'WindowsApps' in sys.executable; sys.exit(0 if (3, 11) <= v <= (3, 14) and struct.calcsize('P') == 8 and (not store or os.environ.get('SETUP_ALLOW_STORE')) else 1)" >nul 2>&1
if not errorlevel 1 set "PY=%*"
exit /b 0

:venv_failed
echo   ERROR: creating the virtual environment failed.
if exist "venv" rmdir /s /q "venv"
echo   The half-created venv folder was removed. If you use the Microsoft Store
echo   Python, install Python from https://www.python.org/downloads/windows/ instead.
goto :fail

:no_python
echo   ERROR: no 64-bit Python 3.11 - 3.14 found.
echo   Install Python 3.13 from https://www.python.org/downloads/windows/
echo   and tick "Add python.exe to PATH" in the installer,
echo   or run:  winget install -e --id Python.Python.3.13
echo   Then run setup.bat again.
goto :fail

:pip_failed
echo   ERROR: installing packages failed. Check the internet connection or proxy
echo   settings and run setup.bat again. If the error says "filename or extension
echo   is too long", move the project to a shorter folder such as C:\Attendance.
goto :fail

:fail
echo.
echo ===========================================================
echo   SETUP STOPPED - fix the problem above and run setup.bat again.
echo ===========================================================
if not defined NO_PROMPT pause
exit /b 1
