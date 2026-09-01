@echo off
title SIHA & SIMRS Analytics Dashboard
color 0A
cd /d "%~dp0"
echo ================================================================
echo    MEMULAI SIHA & SIMRS INTELLIGENCE DASHBOARD
echo ================================================================
echo Direktori Kerja: %CD%
echo.
python run_dashboard.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Terjadi kesalahan saat menjalankan dashboard.
    echo Pastikan Python dan dependensi telah terpasang dengan benar.
)
pause
