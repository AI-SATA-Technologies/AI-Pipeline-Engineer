@echo off
echo Starting camera client...
echo Make sure the FastAPI server is running first.
echo.
call venv\Scripts\activate
python camera_client.py
