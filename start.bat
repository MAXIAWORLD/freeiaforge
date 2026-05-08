@echo off
setlocal

if not exist "backend\.env" (
    copy "backend\.env.example" "backend\.env" >nul
    echo.
    echo Created backend\.env from .env.example.
    echo.
    echo NEXT STEPS:
    echo   1. Open backend\.env in Notepad
    echo   2. Paste at least one API key after the = sign
    echo      Easiest: free Cerebras key at https://cloud.cerebras.ai
    echo   3. Save and close Notepad
    echo.
    echo Opening backend\.env now...
    start "" notepad "backend\.env"
    echo.
    pause
)

docker compose up --build
