# Build & Distribution

Cara membuat installer Windows untuk YT Short Clipper Pro, dan apa yang sudah
diverifikasi dan belum.

## Ringkasan

```bash
# Build EXE (butuh PyInstaller, ~5-15 menit)
python build_exe.py

# Cek hasil build saja, tanpa build ulang
python build_exe.py --verify-only

# Test semua
pytest tests/ -q
```

Hasilnya ada di `dist/YTShortClipper/`. Kirim sebagai zip — foldernya satu
unit, tapi zip-nya satu file.

## Dua jalur distribusi

| Jalur | Untuk siapa | Ukuran | Perlu Python? |
|---|---|---|---|
| `installer/install.ps1` | developer, PC kosong | ~1 GB | install sendiri |
| `dist/YTShortClipper/` | distributor, user akhir | ~500 MB | tidak |

Jalur `.ps1` mengunduh dependensi dari PyPI. Jalur EXE mengemas semuanya, tapi
tidak bisa mengemas model whisper (lihat di bawah).

## Yang TIDAK ikut installer, dan kenapa

| Aset | Alasan |
|---|---|
| `ffmpeg.exe`, `ffprobe.exe` | Lisensi LGPL/GPL. Dipasang terpisah via `winget install Gyan.FFmpeg`. Installer menanyakannya, tidak mengunduh diam-diam. |
| `yt-dlp.exe` | Diperbarui hampir setiap minggu. Membekukan versi di installer = langsung basi. Dipasang via `pip install -U yt-dlp`. |
| Model faster-whisper | 1.5–3 GB per model, diunduh saat runtime ke cache user. Dibekukan = satu model yang pasti cepat basi. |
| `backsound/*.mp3` | **SYARAT RILIS.** Provenance belum jelas. Lihat `THIRD_PARTY_NOTICES.md`. |

## Keputusan yang perlu dipahami

**Onedir, bukan onefile.** Onefile ekstrak ke `%TEMP%` tiap kali dijalankan lalu
menghapus dirinya. Dengan model whisper ratusan MB, itu berarti baca disk besar
dua kali per launch, dan `sys._MEIPASS` berpindah tiap proses — persis kelas
bug yang `clipper_paths.py` dibangun untuk menutup. Onedir juga lebih cepat
startup dan lebih mudah di-debug.

**gradio dan streamlit dikecualikan.** Hanya untuk web/Colab. Membawa keduanya
ke installer desktop menambah ratusan MB tanpa dipakai.

**pykakasi opsional.** Dipakai untuk romaji → kanji. Kalau ada di environment
build, ikut; kalau tidak, dikecualikan. Aplikasi harus tetap jalan tanpanya.

## verify_build() — gerbang rilis

`build_exe.py` tidak berhenti di "PyInstaller sukses". Setelah selesai, ia
memeriksa:

- EXE ada
- `fonts/Montserrat-Bold.ttf` dan `bin/detector.tflite` ada di dalam bundle
- `LICENSE`, `THIRD_PARTY_NOTICES.md`, `licenses/OFL.txt` ada
- tidak ada aset berlisensi komersial yang ikut

Yang terakhir adalah yang paling penting: kalau `KOMIKAX_.ttf` atau aset
terlarang lain sampai masuk bundle, build **gagal** dengan pesan jelas, bukan
berhasil diam-diam lalu jadi masalah hukum.

## Status verifikasi

**Sudah diverifikasi di PC ini:**

- `pytest tests/ -q` — 300 test hijau
- `ruff check --select=F,E9` — bersih
- `python -m py_compile` — semua modul compile
- `install.ps1` lolos `Parser.ParseFile` — 0 error sintaks
- `build_exe.py --verify-only` — mendeteksi bundle yang tidak lengkap
- Struktur direktori yang dibutuhkan `--add-data` semua ada

**BELUM diverifikasi — harus diuji manual:**

1. **Hasil `python build_exe.py` untuk build lengkap.** Build sedang berjalan
   saat dokumen ini ditulis; belum ada output final yang diperiksa.
2. **EXE benar-benar jalan.** Mode frozen punya perbedaan dari mode dev yang
   tidak bisa diuji tanpa menjalankan EXE: import dinamis, `sys.frozen`,
   lokasi `RESOURCE_DIR`.
3. **Render video dari EXE.** Butuh video YouTube sungguhan + credit API.
4. **Installer di PC yang benar-benar kosong.** Yang diuji hanya parse check.

Cara mengetestnya:

```bash
# 1. Build
python build_exe.py

# 2. Pastikan eksplisitkan resource ada
python build_exe.py --verify-only

# 3. Jalankan EXE
dist/YTShortClipper/YTShortClipper.exe

# 4. Di app: tempel link YouTube, klik Ambil & Analisis, render 1 segmen
# 5. Cek file .mp4 muncul di folder output
```

Kalau ada yang gagal, cek `dist/YTShortClipper/_internal/` untuk melihat apa
yang sebenarnya ikut.

## Known issue: output default menabrak Known Folder Windows

`clipper_paths.default_output_dir()` = `~/Videos/YTShortClipperPro`. Di sebagian
PC Windows, folder `Videos` (dan `Documents`, `Music`, `Pictures`, `Desktop`)
tidak bisa ditulis, dan errornya menyesatkan: `WinError 2 "The system cannot find
the file specified"` — padahal foldernya ada dan user punya Full Control.

Ditemukan dan diuji di PC develop: `mkdir` di `~/Videos` gagal, di `~/Downloads`
berhasil, di `C:/` berhasil.

`clipper_firstrun.check_output_dir()` mendeteksi ini dan memberi tahu user,
bukan membiarkan render gagal diam-diam di tengah jalan. **Tapi dialog wizard-nya
belum ada** — saat ini baru modul + test. Sampai dialognya ada, user harus
mengganti folder output sendiri di Settings.

## Yang belum dikerjakan

- Dialog first-run wizard (modulnya ada, dialognya belum)
- Inno Setup / NSIS untuk installer `.msi` proper
- Kode aktivasi / lisensi
- Auto-update
- Logo + ikon aplikasi (sekarang pakai emoji)
- `setup_pc_baru.bat` yang lama masih ada di root dan sudah usang —
  belum dihapus karena `installer/install.bat` menggantikannya, tapi hati-hati
  kalau masih dipakai
