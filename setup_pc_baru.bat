@echo off
echo ==========================================
echo   YT Short Clipper - Auto Installer
echo ==========================================
echo.
echo [1/3] Mengecek Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Python tidak ditemukan! Silakan instal Python 3.10+ terlebih dahulu.
    pause
    exit
)

echo [2/3] Menginstal library Python (ini butuh waktu)...
pip install -r requirements.txt

echo.
echo [3/3] Mengecek Node.js (untuk yt-dlp)...
node -v >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Node.js tidak ditemukan! yt-dlp mungkin akan lambat atau gagal.
    echo     Sangat disarankan instal Node.js dari https://nodejs.org/
)

echo.
echo ==========================================
echo   SELESAI! Silakan jalankan aplikasi:
echo   python clipper_gui_modern.py
echo ==========================================
pause