<div align="center">

# YT Short Clipper Pro

**Tempel link YouTube → jadi Shorts 9:16 otomatis.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://python.org)
[![FFmpeg](https://img.shields.io/badge/FFmpeg-required-green?logo=ffmpeg&logoColor=white)](https://ffmpeg.org)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Windows](https://img.shields.io/badge/Windows-10%2F11-0078D6?logo=windows&logoColor=white)](https://microsoft.com)

Aplikasi desktop Windows. Analisis video berjalan di cloud — lihat
[batasan yang jujur](#-batasan-yang-jujur).

</div>

---

## Apa ini?

YT Short Clipper mengubah **video panjang → Shorts 9:16 siap upload**:

1. Transkrip otomatis (faster-whisper, jalan lokal)
2. AI menandai momen yang layak jadi Short
3. Face tracking mengikuti pembicara (Kalman filter)
4. Subtitle karaoke per kata
5. B-roll, BGM, voice hook
6. Export 1080x1920

Yang diproses: transkripsi, face tracking, dan render. Semua lokal.
Yang perlu internet: analisis AI dan (opsional) B-roll Pexels.

---

## Install

```bash
# 1. Python 3.10–3.12 dari python.org — cek "Add to PATH"
python --version

# 2. ffmpeg (bukan lewat pip)
winget install Gyan.FFmpeg

# 3. Dependensi Python
pip install -r requirements.txt
```

### yt-dlp sering rusak

YouTube rutin memutus extractor lama, jadi `yt-dlp` perlu di-update berkala:

```bash
pip install -U yt-dlp
```

Kalau download video gagal dengan "Sign in to confirm", itu bukan bug aplikasi —
yt-dlp sudah terlalu lama.

---

## Pakai

```bash
python clipper_gui_modern.py
```

1. **Tempel link** YouTube
2. **Klik Analisis** — AI menandai momen
3. **Pilih segmen** → **Proses**

API key diisi lewat **Settings**, dan disimpan terenkripsi (DPAPI Windows),
bukan plaintext di file config.

### Command line

```bash
python clipper_web.py     # Gradio (web/Colab)
python app.py             # Streamlit (web/Colab)
```

---

## Struktur folder

Aplikasi desktop **tidak** menulis ke folder installasinya. Semua data user
berada di `%LOCALAPPDATA%\YTShortClipperPro`:

| Lokasi | Isi |
|---|---|
| `%LOCALAPPDATA%\YTShortClipperPro\` | config, log, cache, `secrets.dat` |
| `~\Videos\YTShortClipperPro\` | hasil render (bisa diubah di Settings) |
| folder aplikasi | hanya dibaca — `bin/`, `fonts/`, `licenses/` |

Artinya update aplikasi tidak menghapus progress, dan uninstall tidak menghapus hasil kerja user.

---

## Konfigurasi

| Provider | Perlu API key | Catatan |
|---|---|---|
| Gemini (Native) | Ya | Default. Gratis untuk penggunaan wajar. |
| Groq | Ya | Cepat, free tier ketat. |
| OpenRouter | Ya | Banyak model, sebagian gratis. |

Key disimpan lewat Windows **DPAPI** — hanya bisa dibaca oleh akun Windows yang
logged in. Tidak ada key di `config.json`, tidak ada key di log, tidak ada key
di dalam paket installer.

---

## Yang perlu kamu tahu sebelum pakai

**Nama repo ini dulu `offline`. Analisisnya tidak offline.** Dia lewat API
provider di atas. Yang offline itu transkripsi dan render.

**Download dari YouTube melanggar ToS YouTube.** Pakai hanya untuk video milik
sendiri,channel Anda, atau yang Anda punya izinnya.

**BGM bawaan (`backsound/`) provenance-nya belum jelas.** Dua file MP3 di repo
ini belum punya LICENSE yang jelas. Untuk penggunaan komersial, ganti dengan musik
berlisensi (YouTube Audio Library / CC0 / Artlist). Lihat
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

**`--cookies-from-browser` tidak dipakai.** Kalau video butuh login, isi
`cookies.txt` sendiri di Settings. Aplikasi tidak pernah membaca cookie browser
Anda secara otomatis.

---

## Lisensi

Kode aplikasi: **MIT** — lihat [LICENSE](LICENSE).

Aset pihak ketiga punya lisensi masing-masing:

| Aset | Lisensi | Dikemas? |
|---|---|---|
| Montserrat | SIL OFL 1.1 | ✅ |
| MediaPipe model | Apache 2.0 | ✅ |
| ffmpeg | LGPL/GPL | ❌ dipasang terpisah |
| yt-dlp | Unlicense | ❌ dipasang terpisah |

Detail dan kewajiban redistribusinya: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

---

## Kontribusi

```bash
pip install -r requirements.txt
pip install pytest ruff
pytest tests/ -q
ruff check --select=F,E9 .
```

Semua komentar, docstring, dan dokumen dalam repo ini ditulis Bahasa Indonesia.
Kodenya dalam Bahasa Inggris.

Keputusan desain ada di [docs/DECISIONS.md](docs/DECISIONS.md). Temuan audit
awal di [AUDIT.md](AUDIT.md).

---

## Credit

- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — transkripsi
- [MediaPipe](https://github.com/google-ai-edge/mediapipe) — face detection
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — download
- [FFmpeg](https://ffmpeg.org) — encode video
- [Montserrat](https://github.com/JulietaUla/Montserrat) — font (SIL OFL)
- [OpenCV](https://opencv.org) — processing frame
