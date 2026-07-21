<div align="center">

# 🎬 YT Short Clipper Pro

**AI-Powered YouTube Shorts Generator**

Ubah video YouTube panjang menjadi Shorts viral secara otomatis dengan AI, face tracking, dan karaoke subtitle.

[![Python](https://img.shields.io/badge/Python-3.8+-blue?logo=python&logoColor=white)](https://python.org)
[![FFmpeg](https://img.shields.io/badge/FFmpeg-required-green?logo=ffmpeg&logoColor=white)](https://ffmpeg.org)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Release](https://img.shields.io/badge/Release-v3.0-brightgreen)](https://github.com/Chukie99/yt-short-clipper-offline/releases)

</div>

---

## ✨ Fitur Utama

| Fitur | Deskripsi |
|-------|-----------|
| 🤖 **AI Analysis** | Otomatis temukan segmen viral menggunakan AI (OpenRouter/Groq/Gemini) |
| 👁️ **Face Tracking** | Kamera otomatis mengikuti pembicara dengan Kalman Filter |
| 🎤 **Karaoke Subtitle** | Subtitle per kata dengan animasi bounce & warna aktif |
| 🎬 **Multiple Template** | 4 style: Cinematic, Clean, Bold, Story |
| 🖼️ **B-Roll Overlay** | Otomatis cari visual dari Pexels berdasarkan konten |
| 🎵 **Background Music** | Auto-download BGM sesuai mood video |
| 🎤 **Voice Hook** | Tambah voice over pembuka dengan Voicebox |
| 📐 **Split Screen** | Tampilkan 2+ pembicara sekaligus |
| 🏷️ **Watermark** | Logo + watermark dengan pill background |
| 📊 **Progress ETA** | Tampil sisa waktu saat rendering |

---

## 🚀 Quick Start

### Download EXE (Recommended)

Download versi terbaru dari [Releases](https://github.com/Chukie99/yt-short-clipper-offline/releases), extract, lalu jalankan `YTShortClipper.exe`.

### Build dari Source

```bash
# Clone repository
git clone https://github.com/Chukie99/yt-short-clipper-offline.git
cd yt-short-clipper-offline

# Install dependencies
pip install -r requirements.txt

# Jalankan
python clipper_gui_modern.py

# Build EXE
python build_exe.py
```

---

## ⚙️ Konfigurasi

### AI Provider (Gratis)

| Provider | Model | Status |
|----------|-------|--------|
| OpenRouter | nvidia/nemotron-3-super-120b-a12b:free | ✅ Recommended |
| Groq | llama-3.3-70b-versatile | ⚠️ Rate limited |
| Gemini | gemini-2.0-flash | ⚠️ Quota limited |

Dapatkan API key gratis di:
- OpenRouter: https://openrouter.ai/keys
- Groq: https://console.groq.com/keys
- Gemini: https://aistudio.google.com/apikey

### YouTube Cookies

Untuk download video tanpa watermark:

1. Install extension "Get cookies.txt" di Chrome
2. Buka YouTube.com dan login
3. Klik extension → Export
4. Simpan file `.txt` dan atur path di Settings

### Voice Hook (Optional)

Fitur Voice Hook memungkinkan menambahkan voice over pembuka secara otomatis menggunakan Voicebox local server.

**Persiapan:**
1. Install dan jalankan [Voicebox](https://github.com/Chukie99/voicebox) di port `17493` (default)
2. Buat voice profile di Voicebox
3. AI akan otomatis generate voice hook saat analisis, atau rekam manual sebagai MP3

**Cara pakai:**
- Saat AI analysis, field `voice_hook_script` akan generate audio otomatis (jika Voicebox running)
- Atau klik folder di kolom "Voice Hook MP3" untuk upload MP3 rekaman manual
- Atur durasi hook dengan slider (0.5 - 5 detik)

---

## 🎯 Cara Pakai

1. **Paste link YouTube** → Klik "Ambil & Analisis"
2. **Tunggu AI analisis** → Akan muncul segmen viral yang direkomendasikan
3. **Editopsional** → Atur zoom, split screen, voice hook
4. **Klik "Proses Terpilih"** → Tunggu rendering selesai
5. **Hasil ada di folder `output/`** → Siap upload ke TikTok/YouTube Shorts

---

## 📁 Struktur Project

```
yt-short-clipper-offline/
├── clipper_gui_modern.py    # Source code utama
├── build_exe.py             # Script build EXE
├── config.json              # Konfigurasi (API keys, settings)
├── cookies.txt              # YouTube cookies
├── requirements.txt         # Python dependencies
├── bin/                     # FFmpeg, yt-dlp, detector model
├── fonts/                   # Font untuk subtitle
├── backsound/               # Background music files
├── output/                  # Hasil video
└── dist/                    # EXE build
```

---

## 🛠️ Dependencies

- **Python 3.8+**
- **FFmpeg** - Video processing
- **yt-dlp** - YouTube download
- **faster-whisper** - Speech-to-text
- **MediaPipe** - Face detection
- **OpenCV** - Image processing
- **CustomTkinter** - Modern GUI

---

## 📝 Changelog

### v3.0 (2026-07-20)
- ✅ Performance: Frame skipping untuk face detection (3x lebih cepat)
- ✅ Performance: Lower detection resolution (2x lebih cepat)
- ✅ Fitur: ETA progress saat rendering
- ✅ Fitur: Auto-rotate landscape ke portrait
- ✅ Fitur: Hook duration slider (0.5-5 detik)
- ✅ Fitur: Subtitle preview di Settings
- ✅ Fix: Export resolution sekarang berfungsi
- ✅ Fix: Thread-safe GUI updates
- ✅ Fix: File dialog support PNG/JPG

### v2.0
- AI-powered viral segment analysis
- Karaoke subtitle animation
- Multiple templates
- B-Roll overlay
- Split screen support

---

## 📄 License

MIT License - Gunakan bebas untuk personal dan komersial.

---

<div align="center">

**Made with ❤️ for content creators**

[Report Bug](https://github.com/Chukie99/yt-short-clipper-offline/issues) · [Request Feature](https://github.com/Chukie99/yt-short-clipper-offline/issues)

</div>
