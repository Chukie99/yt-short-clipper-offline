@echo off
REM ============================================================
REM  YT Short Clipper Pro - Installer
REM
REM  File ini hanya pembuka supaya user bisa klik dua kali.
REM  Logika ada di install.ps1 yang langsung dipanggil di bawah.
REM ============================================================
setlocal

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
set EXITCODE=%ERRORLEVEL%

echo.
if %EXITCODE% neq 0 (
    echo Installer berhenti dengan kode %EXITCODE%.
    echo Lihat log di %%LOCALAPPDATA%%\YTShortClipperPro
    echo.
    pause
    exit /b %EXITCODE%
)

echo Instalasi selesai.
pause
