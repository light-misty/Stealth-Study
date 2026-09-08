@echo off
chcp 65001 >nul
title HIU WorkSpace Launcher

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
cd /d "%ROOT%"

echo =============================================
echo   HIU WorkSpace Startup
echo =============================================
echo.

if not exist "%ROOT%\.venv\Scripts\hiu-workspace-server.exe" (
    echo [ERROR] .venv not found, run: bash packaging/setup_dev_env.sh
    pause
    exit /b 1
)

echo [1/2] Starting backend hiu-workspace-server on port 8765...
start "OW Backend" cmd /k %ROOT%\.venv\Scripts\hiu-workspace-server.exe --cwd %ROOT% --port 8765

echo [2/2] Starting frontend Tauri GUI...
if exist "%ROOT%\surfaces\gui\node_modules\@tauri-apps\cli" (
    cd /d "%ROOT%\surfaces\gui"
    start "OW GUI" cmd /k npx tauri dev
) else (
    echo [WARN] Frontend deps missing, run: cd surfaces/gui ^&^& npm install
)

echo.
echo Services starting, check new windows for output.
echo Backend port: 8765
echo Frontend port: 1420
echo.