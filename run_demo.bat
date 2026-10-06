@echo off
cd /d %~dp0
pip install -r requirements.txt
if exist smartrx.db del smartrx.db
python seed.py
start "" cmd /c "timeout /t 4 >nul & start http://localhost:8000"
python -m uvicorn app.main:app
