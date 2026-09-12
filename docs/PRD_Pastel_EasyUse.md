# PRD — YT Short Clipper v3.1 (Pastel & Easy Use)

**Tanggal:** 12 Sep 2026 | **Repo:** Chukie99/yt-short-clipper-offline | **Platform:** Windows EXE + Colab
**Tagline:** Paste link YouTube → jadi Shorts 9:16 viral dalam 1 klik

---

## 1. Tujuan
Bikin app clipper yang orang awam pun paham dalam 30 detik. Fokus: AI cari segmen viral, face-tracking auto, karaoke subtitle, export TikTok-ready. Gak perlu skill editing.

## 2. Persona
- **Creator pemula (18–35)** — mau jadi Shorts dari podcast/ceramah tanpa belajar Premiere.
- **Admin sosmed UMKM** — butuh 3–5 Shorts/hari cepat.
- Pain: download manual ribet, crop 9:16 miring, subtitle ngetik manual lama.

## 3. Prinsip Easy Use (WAJIB)
1. **3 klik jadi:** Paste → Centang segmen AI → Proses.
2. **Zero config default:** Template Cinematic, 1080×1920, karaoke ON, BGM 15% — langsung jalan tanpa setting.
3. **Bahasa Indonesia simpel:** "Ambil & Analisis", "Proses Terpilih", "Hasil ada di output/".
4. **Progress jelas:** ETA + bar + log ringkas ("30 detik lagi").
5. **Undo aman:** queue_state.json — kalau crash bisa lanjut, gak ngulang download.

## 4. Palette Pastel (Brand)
```
BG: #FFF7F0 (warm cream)  Card: #FFFFFF  Line: #F0DDD2
Peach: #FFDAC1  Mint: #C8EDE0  Lilac: #E2D8F5  Yellow: #FFF2B2  Blue: #B5D8FF
Ink: #2B2D42  Muted: #8D99AE  Accent: #FF8A65  Navy CTA: #2B2D42
```
- Corner 16–20px, shadow soft `0 6px 24px rgba(43,45,66,.06)`
- Font: Inter (UI) + Montserrat Bold/Black (subtitle karaoke)
- Button: pill (999px), CTA navy, ghost putih-line. Chip template pastel.

## 5. Information Architecture
```
[Header: Logo + v3.1]
[Hero: Headline kiri + Phone preview kanan (420x740)]
[Stats: AI / Face / Karaoke — 3 kartu pastel]
[Main: Kiri= Alur 3 langkah + Quality chip | Kanan= Input Link + Template + Badges]
[Footer: Settings / Output path]
```
Mobile: hero stack, 3 kartu jadi 1 kolom.

## 6. Fitur Inti (MVP v3.1)
| Fitur | Detail | Easy Use |
|---|---|---|
| AI Viral Finder | Gemini/OpenRouter, prompt skor 1–10 (aha, emosi, punchline), durasi 45–75s, skor≥7 | 1 klik analisis, hasil berupa card dengan judul viral + hook |
| Face Tracking | MediaPipe + Kalman, crop 9:16, split-screen 2 pembicara | auto, toggle "Split jika 2 orang" |
| Karaoke Subtitle | per-kata, active kuning #FFE600 scale 1.1 bounce, inactive putih alpha 150 | 4 template: Cinematic/Clean/Bold/Story — 1 klik ganti |
| B-Roll | Pexels keyword dari transcript (opsional) | toggle ON/OFF |
| BGM | backsound/kocak/sedih.mp3 auto | volume slider 0–30% default 15% |
| Export | 1080×1920, CRF preset draft/normal/high, end-card "Follow for more!" | 3 chip quality + preview |
| Watermark | pill logo | input logo + text |

## 7. Alur (Happy Path)
1. User paste `https://youtube.com/watch?v=...` → klik **Ambil & Analisis** (validasi url, show spinner "Menganalisis 20–40 detik").
2. AI return 3–5 segmen: card dengan [00:12–01:08] "Kenapa Kamu Overthinking?" + hook + mood + checkbox. User centang 1–3.
3. Klik **Proses Terpilih** → queue, ETA per clip, log "Face tracking 60%". Selesai → notif "✅ 3 Shorts jadi di output/" + tombol Buka Folder.

## 8. UI Spec Detail
- Input: `border #F0DDD2, bg #FFF7F0, radius 12, placeholder muted`
- Card: `bg #FFFFFF, border #F0DDD2, radius 16`
- Chip active: `bg #2B2D42 text white`, inactive `bg #FFF7F0`
- Phone mock: 220×390, radius 26, border 6px #222, cap putih 96% opacity.
- Empty state: ilustrasi pastel + "Belum ada clip — paste link dulu".

## 9. Settings (disembunyikan default)
Advanced di modal: AI provider (OpenRouter free rekom), Pexels key, cookies.txt, font, logo, export resolution. Default aman biar pemula gak nyentuh.

## 10. Acceptance Criteria (QA 10 poin)
1. Paste link invalid → toast merah pastel "Link tidak valid".
2. AI return <7 skor → jangan tampilkan (filter).
3. Clip 45–75s ±2s.
4. Face tracking tidak jitter (>90% frame ada wajah).
5. Subtitle karaoke sync per-kata (Whisper word timestamps).
6. Export 1080×1920, 30fps, AAC, <50MB per Shorts 60s.
7. Draft 3x lebih cepat dari High.
8. Kalau cookies expired → pesan jelas + cara export cookies.
9. Crash mid-render → queue_state.json bisa resume.
10. EXE jalan tanpa install Python (bundled bin/ffmpeg, yt-dlp).

## 11. Non-Goals v3.1
Bukan editor timeline manual, bukan autotranslate, bukan upload langsung ke YouTube.

## 12. File Terkait
- Mockup: `docs/mockup_pastel.html` (buka di browser)
- Core: `clipper_core.py` (1845 baris)
- GUI: `clipper_gui_modern.py` (akan di-reskin pastel)
- Build: `build_exe.py`

---
**Next:** approve mockup → gue reskin `clipper_gui_modern.py` ke pastel + 3-langkah wizard, lalu build EXE.
