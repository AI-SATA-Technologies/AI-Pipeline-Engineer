@echo off
cd /d "%~dp0.."
echo ================================
echo  Starting Camera Viewer (testing)
echo ================================
echo.
echo Make sure the server is running first.
echo Press Q in the viewer window to quit.
echo.
if not exist "%~dp0..\venv\Scripts\activate.bat" (
    echo ERROR: venv not found at "%~dp0..\venv".
    echo Create it with:  python -m venv venv  ^&^&  venv\Scripts\pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)
call "%~dp0..\venv\Scripts\activate.bat"
python viewer.py
echo.
echo Viewer closed.
pause
