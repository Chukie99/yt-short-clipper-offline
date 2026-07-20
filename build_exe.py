import subprocess
import sys
import os
from pathlib import Path

def build():
    # Pastikan PyInstaller terinstall
    try:
        import PyInstaller
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    script_name = "clipper_gui_modern.py"
    exe_name = "YTShortClipper"
    
    # Path folder penting
    base_path = Path(__file__).parent.absolute()
    fonts_path = base_path / "fonts"
    bin_path = base_path / "bin"
    
    # Kumpulkan parameter build
    params = [
        'pyinstaller',
        '--noconfirm',
        '--onedir', # Berubah ke folder agar jauh lebih cepat dan stabil
        '--windowed',
        f'--name={exe_name}',
        f'--add-data={str(fonts_path)};fonts',
        f'--add-data={str(bin_path)};bin',
        '--collect-all=customtkinter',
        '--collect-all=faster_whisper',
        '--collect-all=pykakasi',
        '--clean', # Bersihkan cache lama
        script_name
    ]

    print("[BUILD] Memulai proses pembuatan EXE (Mode: Folder)...")
    print(f"[INFO] Hasilnya ada di folder 'dist/{exe_name}'")
    try:
        subprocess.check_call(params)
        print(f"\n[OK] Berhasil! Silakan buka folder 'dist/{exe_name}' dan jalankan '{exe_name}.exe'")
    except Exception as e:
        print(f"\n[FAIL] Gagal membuat EXE: {str(e)}")

if __name__ == "__main__":
    build()
