# FFmpeg Skill — YT Short Clipper

Skill `skills/ffmpeg-skill` (kajisho5/ffmpeg-skill) bundled sebagai **reference & helper**.
42 tools offline: probe, cut, fit (9:16), caption/karaoke, silence-remove, loudness, export, contact sheet, dll.

## Workflow yang dipakai di clipper (existing)

clipper_core.py sudah pakai FFmpeg via list-args (anti injection):
- `run_cmd([ffmpeg, "-y", "-ss", ...])` → trim, audio extract, final mux
- Face tracking + crop 9:16 manual via OpenCV (Kalman) — lebih presisi untuk clipper daripada fit.py generic
- Karaoke subtitle via PIL draw (custom), bukan ASS — agar style pastel & template konsisten

## Kalau mau pakai skill scripts langsung (opsional)

```bash
# Probe file dulu (wajib step 1 skill)
python skills/ffmpeg-skill/scripts/probe.py input.mp4 --json

# Fit ke 9:16 dengan blur pad (ala phone editor)
python skills/ffmpeg-skill/scripts/fit.py input.mp4 --aspect 9:16 --fit pad --pad-fill blur -o out_916.mp4

# Potong presisi
python skills/ffmpeg-skill/scripts/cut.py input.mp4 --start 10 --end 35 -o cut.mp4

# Cek compliance YouTube Shorts
python skills/ffmpeg-skill/scripts/check.py out_916.mp4 --platform youtube

# Contact sheet buat inspect hasil (wajib sebelum claim jadi)
python skills/ffmpeg-skill/scripts/look.py out_916.mp4
```

## Kapan pakai skill vs core

- **Core (default):** render Shorts final — jangan diganti, karena sudah terintegrasi face tracking + karaoke + BGM ducking + hook
- **Skill:** untuk job terpisah — reframe manual, cut cepat, cek compliance, bikin contact sheet, atau eksperimen sebelum masuk ke pipeline core

Lihat `skills/ffmpeg-skill/SKILL.md` untuk 42 tools lengkap & `references/scripts.md` untuk flags.
