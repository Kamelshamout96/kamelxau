@echo off
echo Installing dependencies...
py -m pip install -r requirements.txt

echo.
echo Starting XAUUSD Signal Tool...
echo Open your browser to: http://127.0.0.1:8000/run-signal
echo.
py -m uvicorn app:app --reload
pause
