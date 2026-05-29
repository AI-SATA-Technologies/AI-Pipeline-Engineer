@echo off
cd /d "D:\API ai pipeline engineer\school_attendance"
echo ================================
echo  Starting Camera Viewer (testing)
echo ================================
echo.
echo Make sure the server is running first.
echo Press Q in the viewer window to quit.
echo.
call "D:\AI Pipeline Engineer\school_attendance\venv\Scripts\activate.bat"
python viewer.py
echo.
echo Viewer closed.
pause
