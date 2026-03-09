@echo off
title FootballGPT - Starting...
color 0A

echo.
echo  ======================================
echo   FootballGPT - AI Prediction Engine
echo  ======================================
echo.

:: Check venv exists
if not exist "backend\venv\Scripts\activate.bat" (
    echo  [SETUP] Virtual environment not found. Creating one...
    cd backend
    py -3.12 -m venv venv
    call venv\Scripts\activate.bat
    echo  [SETUP] Installing dependencies...
    pip install -r requirements.txt
    cd ..
)

:: Start backend in a new window
echo  [1/2] Starting backend server...
start "FootballGPT Backend" cmd /k "cd backend && venv\Scripts\activate.bat && uvicorn main:app --port 8000"

:: Wait for backend to boot
echo  [2/2] Waiting for backend to start...
timeout /t 4 /nobreak >nul

:: Start frontend server in a new window
start "FootballGPT Frontend" cmd /k "cd frontend && python -m http.server 3000"

:: Wait for frontend to boot
timeout /t 2 /nobreak >nul

:: Open browser
echo  Opening FootballGPT in your browser...
start http://localhost:3000

echo.
echo  ======================================
echo   FootballGPT is running!
echo   Backend:  http://localhost:8000
echo   Frontend: http://localhost:3000
echo  ======================================
echo.
echo  Close the Backend and Frontend windows to shut down.
echo  Press any key to close this window...
pause >nul