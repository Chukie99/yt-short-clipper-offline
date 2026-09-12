<div align="center">

# yt-short-clipper-offline

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/Chukie99/yt-short-clipper-offline/blob/main/docs/YT_Short_Clipper.ipynb)

**Paste link YouTube → jadi Shorts viral 9:16 otomatis. 3 klik jadi.**

[![Python](https://img.shields.io/badge/Python-3.8+-blue?logo=python&logoColor=white)](https://python.org)
[![FFmpeg](https://img.shields.io/badge/FFmpeg-required-green?logo=ffmpeg&logoColor=white)](https://ffmpeg.org)
[![Release](https://img.shields.io/badge/Release-v1.2.0-FFDAC1?style=for-the-badge)](https://github.com/Chukie99/yt-short-clipper-offline/releases)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-Support%20Me-FF5E5B?logo=ko-fi&logoColor=white)](https://ko-fi.com/chuckie999)

*Desktop Windows (pastel) + 1-Click Colab — offline-first, no watermark.*

</div>

---

## ✨ Apa ini?

YT Short Clipper mengubah **video YouTube panjang → Shorts 9:16 siap upload** secara otomatis:
AI cari momen viral → face tracking ikut pembicara → karaoke subtitle → template 4 style → export 1080x1920.

> **v1.0.0 Renew:** Full rewrite — UI pastel soft, alur 3 langkah, aman (no shell injection), queue anti-corrupt, Test API 1 klik.

---

## 🎨 Desain Pastel & Easy Use

- **Palette:** Cream `#FFF7F0` + Peach/Mint/Lilac, card putih, line `#F0DDD2`, tombol navy `#2B2D42` — soft di mata
- **3 Klik Jadi:** `Paste link` → `Centang segmen AI` → `Proses` (semua default udah jalan, gak perlu setting)
- **4 Template 1-klik:** Cinematic / Clean / Bold / Story
- **Quality chip:** Draft / Normal / High (disarankan Normal)

Mockup desktop: `docs/mockup_desktop.html` — PRD lengkap: `docs/PRD_Pastel_EasyUse.md`

---

## ✨ Fitur

| Fitur | Deskripsi |
|-------|-----------|
| 🤖 **AI Analysis** | Temukan segmen viral otomatis (OpenRouter / Groq / Gemini) |
| 👁️ **Face Tracking** | Kamera follow pembicara (Kalman Filter), auto-rotate landscape→portrait |
| 🎤 **Karaoke Subtitle** | Per kata bounce + warna aktif, font pilihan |
| 🎬 **4 Template** | Cinematic, Clean, Bold, Story |
| 🖼️ **B-Roll** | Overlay visual dari Pexels (sesuai konten) |
| 🎵 **BGM** | Auto backsound lokal `backsound/` + warning kalau fallback YouTube |
| 🎤 **Voice Hook** | Voice over pembuka via **OptiClone** (clone 3s) otomatis, atau MP3 manual + slider 0.5-5s |
| 📐 **Split Screen** | 2+ pembicara sekaligus |
| 🏷️ **Watermark/Logo** | Pill background, posisi custom |
| 📊 **ETA + Log** | Progress + sisa waktu render |
| 🔍 **Test API** | Cek API key jalan/belum langsung di Settings |
| 💾 **Queue Persist** | Antrian aman (atomic save), lanjut setelah restart |

---

## 🚀 Quick Start (3 Langkah)

**1. Paste** link YouTube → klik **Ambil & Analisis**
**2. Centang** segmen yang mau dijadikan Shorts (AI sudah pilihkan)
**3. Klik Proses** → hasil ada di `output/` siap upload TikTok / YouTube Shorts

### Opsi Jalan

**A. 1-Click Colab (paling gampang):**
Klik badge Colab di atas → Run 2 cells → buka URL ngrok di HP/laptop.

**B. Download EXE (Windows):**
Download dari [Releases](https://github.com/Chukie99/yt-short-clipper-offline/releases) → extract → jalankan `YTShortClipper.exe` (bin/ ffmpeg+yt-dlp sudah bundling).

**C. Dari Source:**
```bash
git clone https://github.com/Chukie99/yt-short-clipper-offline.git
cd yt-short-clipper-offline
pip install -r requirements.txt
python clipper_gui_modern.py   # GUI pastel
python build_exe.py            # build EXE
```

---

## ⚙️ Konfigurasi (gak wajib — default sudah jalan)

| Provider | Model default | Catatan |
|----------|---------------|---------|
| OpenRouter | `nvidia/nemotron-3-super-120b-a12b:free` | ✅ Recommended gratis |
| Groq | `llama-3.3-70b-versatile` | ⚠️ Rate limited |
| Gemini | `gemini-2.0-flash` | ⚠️ Quota limited |

Dapatkan key gratis: [OpenRouter](https://openrouter.ai/keys) · [Groq](https://console.groq.com/keys) · [Gemini](https://aistudio.google.com/apikey)
→ Masukkan di **Settings** → klik **🔍 Test API Key** untuk cek.

**YouTube Cookies (biar download gak gagal):** Install extension "Get cookies.txt" → buka YouTube login → Export → simpan `.txt` → atur path di Settings.

**Voice Hook:** Taruh file ref 3 detik di `Settings` (vendor/opticlone) → OptiClone auto clone → AI auto-generate. Tanpa ref → tulis hook manual lalu upload MP3.

---

## 📁 Struktur

```
yt-short-clipper-offline/
├── clipper_gui_modern.py    # Desktop GUI pastel (utama)
├── clipper_core.py          # Core logic (shared)
├── app.py / clipper_web.py  # Streamlit / Gradio WebUI
├── build_exe.py             # Build EXE
├── config.json              # API keys & settings
├── bin/                     # ffmpeg, yt-dlp, detector
├── fonts/ backsound/ output/ dist/
└── docs/
    ├── YT_Short_Clipper.ipynb
    ├── mockup_desktop.html
    ├── mockup_pastel.html
    └── PRD_Pastel_EasyUse.md
```

---

## 🛠️ Dependencies
Python 3.8+ · FFmpeg · yt-dlp · faster-whisper · MediaPipe · OpenCV · CustomTkinter

---

## 📝 Changelog

### v1.2.0 (2026-09-12) — Viral Pack inside
- 🔥 **Hook 0-2s gede:** `hook` AI auto jadi teks besar kuning outline di 0-2s (anti skip, retention +20%)
- 📋 **Tombol Viral Pack per clip:** Copy Judul (3 opsi `title`+`title_alt`), #Hashtag (10-15), Deskripsi+Hashtag 1 klik → clipboard + badge ⭐ viral_score 7-10
- 🤖 **GEMINI_PROMPT v1.2:** output baru `title_alt/hashtags/seo_tags/viral_score` terpisah — SEO siap FYP tanpa edit manual
- 📄 **_desc.txt + cover upgrade:** judul alt + HASHTAG line + SEO TAGS + HOOK 0-2s + auto copy `*_cover.jpg` 9:16 siap upload
- 🎤 **Tetap pure OptiClone inside:** `tts_generate_hook()` lazy, hook TTS di dalem (vendor/opticlone)

### v1.1.0 (2026-09-12) — Voice Hook TTS inside + Engine FFmpeg inside
- 🎤 **Voice Hook TTS di dalem (pure OptiClone):** AI bikin naskah `voice_hook_script` → langsung jadi suara via **OptiClone (LuxTTS)** only — 3 detik ref wav, 48kHz, 150× realtime, <1GB VRAM (`tts_generate_hook()` lazy, pure)
- 🎞️ **Engine video di dalem:** eksekusi video pakai FFmpeg internal (42 tools, bundled `skills/ffmpeg-skill` — probe/cut/fit 9:16/caption/export/loudness) + face tracking Kalman & karaoke PIL tetap jalan, `build_exe` sudah bundle
- ⚙️ **Easy Use:** TTS jalan otomatis di dalem, gak perlu setting
- 📦 **Deps:** OptiClone terpisah `requirements-tts-opticlone.txt` (5-10GB HF cache first run), core ringan tanpa edge-tts

### v1.0.0 (2026-09-12) — Renew Pastel & Easy Use
- 🎨 **UI:** Reskin full pastel (cream/peach/mint/lilac/navy), light mode, layout 3 langkah
- 🔒 **Security:** yt-dlp & ffmpeg pakai list-args (tanpa `shell=True`), validasi URL anti injection, path spasi aman
- 💾 **Stability:** Queue save atomic (`.tmp`→replace), load_config ignore empty key (gak 401 lagi), subtitle prioritas `id`→`en`
- 🧵 **GUI:** `sys.stdout` thread-safe via `after(0)`, cookies insert benar, BGM YouTube fallback kasih warning copyright
- ⚙️ **UX:** Tombol **Test API Key** di Settings, label "Batal", warna pastel konsisten
- 📄 **Docs:** PRD + mockup desktop pastel baru

### v3.1 (2026-07-21) — Bug Fixes + Self-Contained Build
### v3.0 (2026-07-20) — Performance 3x, ETA, auto-rotate, hook slider
### v2.0 — AI viral analysis, karaoke subtitle, B-Roll, split screen

---

## 🤝 Contributing
Fork → branch `fitur/nama-fitur` → commit → push → Pull Request. Atau [Report Bug](https://github.com/Chukie99/yt-short-clipper-offline/issues).

## 💖 Support
Suka project ini? Traktir kopi: [ko-fi.com/chuckie999](https://ko-fi.com/chuckie999) · [GitHub Sponsors](https://github.com/sponsors/Chukie99)

## 📄 License
MIT — bebas personal & komersial.

<div align="center">

**Made with ❤️ for creators — v1.2.0**

[Report Bug](https://github.com/Chukie99/yt-short-clipper-offline/issues) · [Request Feature](https://github.com/Chukie99/yt-short-clipper-offline/issues)

</div>