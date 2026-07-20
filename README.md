# YT Short Clipper Offline

Alat untuk mengubah video YouTube landscape menjadi format vertikal (9:16) ala YouTube Shorts.
- Otomatis crop mengikuti pembicara (tanpa AI berat, hanya visi komputer klasik)
- Overlay subtitle otomatis (faster-whisper)
- Semua offline, tanpa API cloud

## Persyaratan Sistem
- Python 3.8+
- FFmpeg terinstall dan ada di PATH ([download](https://ffmpeg.org/download.html))
- RAM 4 GB+ (tergantung model faster-whisper)

## Instalasi
1. Clone/download repository ini.
2. Install dependensi Python:
   ```bash
   pip install -r requirements.txt