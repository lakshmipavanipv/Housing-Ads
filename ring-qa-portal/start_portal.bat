@echo off
cd /d "%~dp0"
echo Installing / checking Python packages...
python -m pip install -q -r requirements.txt
if errorlevel 1 (echo Python or pip not found. Install Python from python.org and tick "Add Python to PATH". & pause & exit /b 1)
start "" cmd /c "timeout /t 5 >nul & start http://localhost:8000"
echo Starting Ring QA Portal with the USB ESP32 boards. Keep this window open.
python server.py --backend dongles
pause
