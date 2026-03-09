@echo off
title FootballGPT - Stopping...
color 0C

echo.
echo  Stopping FootballGPT servers...
echo.

:: Kill uvicorn (backend)
taskkill /FI "WINDOWTITLE eq FootballGPT Backend*" /T /F >nul 2>&1

:: Kill python http server (frontend)
taskkill /FI "WINDOWTITLE eq FootballGPT Frontend*" /T /F >nul 2>&1

echo  All servers stopped.
echo  Press any key to close...
pause >nul