# AUDIT.md — Verifikasi Temuan Awal & Temuan Tambahan

Status: **Langkah 0 selesai** — seluruh kode dibaca (`clipper_core.py` 1884 baris,
`clipper_gui_modern.py` 545, `app.py` 571, `clipper_web.py` 480, `clipper_tts.py` 60,
`build_exe.py` 53, `tests/test_pure_functions.py` 275).

Semua temuan di bawah **sudah diverifikasi terhadap kode** — bukan asumsi. Yang tidak
bisa diverifikasi dari kode ditandai eksplisit di bagian [X].

> Catatan versi: deskripsi di brief menyebut `clipper_gui_modern.py` 2184 baris monolit.
> Kenyataannya logika sudah dipindah ke `clipper_core.py`; GUI sekarang 545 baris.
> Brief juga menyebut `voicebox` dan `edge-tts` sebagai fitur aktif — keduanya **sudah
> dicabut** di commit `d0f139f` ("pure OptiClone"). Pend briefed tidak boleh dipakai
> sebagai sumber kebenaran; isi repo yang dipakai.

---

## A. Bug fatal build EXE — **TERVERIFIKASI, benar**

`clipper_core.py:41-54`

```python
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys._MEIPASS)      # folder temp PyInstaller
TEMP_DIR  = BASE_DIR / "temp"
OUTPUT_DIR = BASE_DIR / "output"
CONFIG_FILE = BASE_DIR / "config.json"
```

Konsekuensi saat frozen:
- `config.json`, `temp/` (termasuk `_full.mp4` cache, subtitle, queue state), dan
  `output/` semuanya ditulis ke dalam `sys._MEIPASS`.
- `--onedir`: folder temp dihapus saat app ditutup → **semua hasil render hilang**,
  settings hilang, queue resume hilang.
- `--onefile` (kalau nanti dipakai): dihapus tiap exit → sama.
- `error.log` (`:15`) juga di `BASE_DIR`.
- `ensure_bgm()` menulis ke `BASE_DIR/"backsound"` (`:492`) → di folder read-only
  PyInstaller ini **menThrow OSError**.
- `process_single_video` menulis `today_dir` ke `OUTPUT_DIR` → ikut hilang.

Varian yang lebih ringan dari temuan ini: `clipper_tts.py:14` dan `vendor/opticlone`
juga di-hardcode ke `Path(__file__).parent`.

## B. Keamanan — **TERVERIFIKASI, sebagian sudah diperbaiki duluan**

### B1 `shell=True` — sudah DIREDUksi, belum habis
Temuan brief ("hampir semua command pakai shell=True + f-string") **sudah usang**:
commit sebelumnya sudah mengonversi jalur utama ke list-args. Status aktual:

| Lokasi | Status |
|---|---|
| `clipper_core.py:1111, 1116, 862` (trim, audio, download) | ✅ sudah list-args |
| `clipper_core.py:517` (`ensure_bgm` → ffmpeg Pexels) | ❌ **masih f-string** → `run_cmd(f'... -i "{temp_vid}" ...')` |
| `clipper_core.py:414` (`run_cmd` sendiri) | ❌ masih menerima `str` dan menjalankan `shell=True` |
| `app.py:247, 261` (Streamlit) | ❌ **masih shell=True + f-string berisi `link` dari user** |
| `clipper_web.py:99, 113` (Gradio) | ❌ **masih shell=True + f-string berisi `link` dari user** |

Jadi: `run_cmd` yang "aman" bisa dibelNKai oleh caller mana pun yang mengirim string.
Penyerang di `app.py`/`clipper_web.py` masih nyata. `_valid_youtube_url()` memblokir
metachar, tapi itu filter di level yang salah — harbor yang benar adalah list-args.

### B2 API key plaintext — **TERVERIFIKASI**
`save_config()` (`:286`) menulis JSON apa adanya, termasuk `gemini_api_key`,
`openrouter_api_key`, `groq_api_key`, `pexels_api_key` ke `CONFIG_FILE` yang saat ini
berada di folder aplikasi. Di `%APPDATA%` plaintext tanpa proteksi OS.
`cookies.txt` juga dibaca dari path bebas yang diisi user, dan tidak pernah divalidasi
format/ukuran.

## C. Legal / Lisensi — **TERVERIFIKASI**

| Item | Status |
|---|---|
| README klaim MIT | ❌ **tidak ada file `LICENSE`** di repo (diverifikasi `ls`, `git ls-files`). Tanpa file LICENSE, default-nya "all rights reserved" — klaim MIT di README jadi klaim kosong |
| `bin/` berisi ffmpeg.exe / yt-dlp.exe | ❌ **SALAH**. `git ls-files bin/` = hanya `deploy.prototxt`, `detector.tflite`, `res10_300x300_ssd_iter_140000.caffemodel`. Tidak ada `.exe` yang di-commit. **Tapi ini bug lain yang lebih parah:** `get_ffmpeg_path()`/`get_ytdlp_path()` mencari `bin/ffmpeg.exe` & `bin/yt-dlp.exe` (`:61, :68`) dan `build_exe.py` tidak pernah membundel/menyalinnya → **EXE hasil build tidak punya ffmpeg sama sekali** |
| Font `KOMIKAX_.ttf` | ❌ **berbahaya untuk produk komersial**. `nameID 0` = `© 1999-2001, WolfBainX & Apostrophic Labs. All rights reserved`. Tidak ada `nameID 14` (license). **✅ RESOLVED di fase 4** — file dihapus, default diganti `Montserrat-Bold.ttf` (SIL OFL). `Montserrat-*` aman (terverifikasi) |
| `deploy.prototxt` + `res10_300x300_ssd_iter_140000.caffemodel` | ⚠️ **mati** — `grep` seluruh `.py`: nol referensi. Beban repo 10.6 MB tanpa fungsi |
| Pexels-sebagai-musik | ❌ benar. `ensure_bgm()` (:511-517) mengunduh **video stock** lalu cabut audio-nya jadi BGM. Pexels ≠ musik; lisensi & kualitas. Kode sendiri sudah memberi warning, tapi warning ≠ fix |
| Fallback BGM dari `ytsearch1` | ❌ benar. `:540` `ytsearch1:...no copyright` lalu `--extract-audio`. Melanggar ToS YouTube **dan** berisiko claim. Untuk produk yang dijual: harus dihapus, bukan hanya di-warning |
| Download YouTube | ⚠️ benar sebagai eksposur legal; `--cookies` membaca cookies login user dari PC-nya. Tidak ada `--cookies-from-browser` di kode (temuan brief soal ini **tidak ada di kode**, kemungkinan versi lama) |
| THIRD_PARTY_NOTICES | ❌ tidak ada. Tidak wajib GPL untuk ffmpeg (LGPL/GPL), tapi wajib untuk model `.tflite` + font Montserrat + OptiClone |

## D. Bug & kualitas — diverifikasi, dengan koreksi

| Temuan brief | Status nyata |
|---|---|
| `download_youtube`: `strategies[:max_retries]` dengan `max_retries=3` bikin strategi ke-4 tak terpakai | ❌ **tidakoccur**. Signature sekarang `max_retries=5` (`:821`) dan ada tepat 5 strategi; semua caller pakai default. Tidak ada bug di sini — **jangan diubah** |
| `extract_keywords_from_transcript` 1 request per 5 detik | ✅ benar (`:574` `range(0, int(max_time), 5)`). Clip 75 s → 15 request |
| `ensure_bgm`: `requests.get` tanpa timeout | ✅ benar, tapi hanya **satu**: `:511` `requests.get(v_url, stream=True)` — API call `:505` sudah punya `timeout=15` |
| Banyak `except: pass` | ✅ benar, 6 di `clipper_core.py` |
| `detect_whisper_device` import torch padahal pakai ctranslate2 | ✅ benar, dan **lebih berbahaya dari yang tertulis**: ia mengembalikan `("cuda", "float16")` hanya karena `torch.cuda.is_available()`, padahal `faster-whisper` butuh cuDNN. Di PC bertenaga GPU tanpa cuDNN → crash saat transkripsi |
| `voicebox_generate` hardcode language "en" | ❌ **tidak ada lagi**. `voicebox_generate` sekarang stub yang selalu `return False` (`:896`), TTS murni OptiClone. Tidak ada parameter language |
| Output AI tanpa schema validation | ✅ benar — `re.search(r'(\[.*\]\|\{.*\})', rt, re.DOTALL)` + `json.loads` di `clipper_gui_modern.py:291,448`, `app.py:299`, `clipper_web.py:140`. Tidak ada validasi field afterwards |
| Render per-frame OpenCV+PIL di Python | ✅ benar — loop `for frame_num in range(total_frames)` (`:1482`) dengan ~6 operasi PIL/frame |
| Nama "offline" menyesatkan | ✅ benar — analisis AI, Pexels, dan download semuanya cloud. 24 test pun bernama `yt-short-clipper-offline` |

## E. Produk
❌ Tidak ada: installer, first-run wizard, lisensi, auto-update, batch multi-video,
editor transkrip, brand kit, i18n, crash report, CI (`.github/` tidak ada), dokumentasi
produk, screenshot.
⚠️ Koreksi: **test sudah ada** — `tests/test_pure_functions.py`, 24 test, semua hijau
(`pytest -q` → `24 passed`), memakai stub cv2/mediapipe/PIL. Jadi ini fondasi yang
bisa langsung dibangun, bukan nol.

## F. README
✅ benar semua. Klaim "no watermark" (README baris ~18) — YouTube memang tidak
punya watermark di hasil download, jadi kalimat ini menyesatkan tapi bukan bug.
Badge `Python-3.8+` **SALAH**: dependency butuh ≥3.10 (`google-genai` 2.25.0 → `>=3.10`,
`yt-dlp` → `>=3.10`, `gradio` → `>=3.10`, `streamlit` → `>=3.10`). Tidak ada screenshot/GIF.
Semua requirement `>=` tanpa pin (lihat G9). Bahasa campur ID/EN tanpa kidney.

---

## G. Temuan tambahan (di luar daftar brief), urut tingkat risiko

### G1 — `GEMINI_PROMPT` terkirim dengan brace ganda di tombol "Analisis" manual
**Risiko: TINGGI (fitur rusak diam-diam, hilang revenue path "1 klik analisis")**

`GEMINI_PROMPT` (`:206`) ditulis dengan `{{` / `}}` karenaWEI anggap selalu dipanggil
lewat `.format(transcript=...)` (`:447` di GUI, `:299` app.py, `:140` web.py).

Tapi `clipper_gui_modern.py:290`:
```python
rt = safe_generate_content(self.config, f"{GEMINI_PROMPT}\nLink: {lk}", self.log_func)
```
→ **tanpa `.format()`**. Yang terkirim ke AI adalah contoh JSON dengan `{{`, bukan `{`.
AI cenderung meniru → respons berisi `{{` → `json.loads` GAGAL → `populate_segments`
dapat `[]` → user klik "✨ Analisis", dapat loading, lalu tidak ada segmen sama sekali.

### G2 — `run_batch` bisa mengunci UI selamanya
**Risiko: TINGGI (user harus restart app)**
`clipper_gui_modern.py:488-543`: `self.proc = True` di-set sebelum thread, di-reset
di akhir `run_batch` — **tanpa `try/finally`**. Kalau ada exception di luar
`process_single_video` (mis. `it.set_status` pada item yang sudah di-destroy, atau
`self.p_bar.set` setelah window ditutup), `proc` tetap `True` → klik "PROSES"
seleffective tidak melakukan apa-apa, tanpa pesan error.

### G3 — Durasi segmen tidak divalidasi → `ffmpeg -t` negatif
**Risiko: TINGGI (crash / file 0-byte)**
`run_batch:506-507` membaca `time_str_to_seconds()` lalu langsung dipakai. Kalau user
mengetik `Selesai` < `Mulai` (state default UI `00:00:00` → `00:00:10`, tapi tidak ada
guard), `dur` negatif → `ffmpeg -t -30` → exit != 0 → `run_cmd` melempar. Tidak ada pesan yang menjelaskan hubungan sebab-akibatnya.

### G4 — Font path dan `input_thumbnail.jpg` di dalam `BASE_DIR`
**Risiko: SEDANG**
`:1172` `font_path = BASE_DIR/"fonts"/selected_font`, `:1230` `thumb_img_input_path =
BASE_DIR/"input_thumbnail.jpg"`. Setelah path dipisah (Fase 1) keduanya harus pindah ke
`RESOURCE_DIR`; kalau tidak, fallback ke `C:/Windows/Fonts/impact.ttf` diam-diam dan
tampilan user berubah. Perlu regression test path.

### G5 — Two UI web (`app.py`, `clipper_web.py`) tinggal di repo dan bisa di-build/dijual
**Risiko: SEDANG**
Keduanya punya `shell=True` + f-string (B1), tidak punya guard API key yang sama,
dan menarik `TEMP_DIR/OUTPUT_DIR` saat import — setelah Fase 1 mengubah semantik path,
keduanya akan ikut berubah dan bisa menulis ke `%APPDATA%`. Untuk produk komersial:
entah di-harden identik dengan GUI desktop, atau dikeluarkan dari distribution.

### G6 — `load_config()` membuang key kosong → user tidak bisa menghapus API key
**Risiko: SEDANG**
`:271-274` menghapus semua value string kosong dari file config sebelum merge. Kalau
user menghapus API key di UI dan Save, key itu hilang permanen — baru kembali
setelah `load_config()` dipanggil lagi. Perilaku ini kemungkinan tidak disengaja dan akan membingungkan
user berbayar ("kenapa key saya balik sendiri?").

### G7 — `get_audio_duration()` memakai literal `"ffprobe"`, bukan `get_ffmpeg_path()`
**Risiko: SEDANG**
`:887` hardcode `ffprobe`, sementara `:1110` memakai `get_ffmpeg_path()`. Aman sekarang
karena `bin/` di-prepend ke `PATH` (`:46-48`), tapi rapuh: kalau user taruh ffmpeg
di tempat lain, atau `bin/ffmpeg.exe` tidak ada (lihat C), path ini bisa gagal diam-diam
→ `audio_hook_dur = 0`.

### G8 — Bare `"ffmpeg"` di perintah render
**Risiko: SEDENG**
`:1365` dan `:1373` `ffmpeg_cmd_list = ["ffmpeg", "-y"]` — bukan `get_ffmpeg_path()`.
Dengan `bin/ffmpeg.exe` tidak ada di repo, build EXE tidak punya ffmpeg dan portions
trim (yg pakai path) akan gagal duluan dengan pesan berbeda.

### G9 — Requirement tidak di-pin → build tidak reproducible
**Risiko: SEDANG**
Semua baris `>=` tanpa versi pasti. Untuk produk berbayar, "install ini menghasilkan
software yang sama seperti yang saya jual" adalah syarat mutlak. Contoh nyata: repo ini
memakai API `mediapipe.tasks.python.vision` yang berubah struktur di major baru.

### G10 — `detect_whisper_device()` salah memilih device
**Risiko: SEDANG (sudah dijelaskan di D, tapi layak jadi item sendiri)**
Torch CUDA ⇏ ctranslate2 CUDA. surfaced sebagai crash runtime, bukan pesan jelas.

### G11 — Dead code & artefak membebani repo profesional
**Risiko: RENDAH (tapi terlihat saat review)**
- `format_variants` (`:825-831`) — list of string, **tidak pernah dipakai**, duplikat dari
  `fmt_args_list` (`:849`).
- `VOICEBOX_API = None` (`:894`) — sisa.
- `browse_tts_ref()` (`clipper_gui_modern.py:107`) — tidak pernah dipanggil; TTS reference
  di-set via hidden var yang tidak ada UI-nya → **fitur "OptiClone 3s ref" tidak bisa dipakai user**.
- `skills/ffmpeg-skill/` — 5.2 MB, Claude plugin, tidak dipakai runtime tapi ikut `--add-data`
  di `build_exe.py` → ukuran EXE membengkak tanpa manfaat.
- `logo.png` 788 KB di root, dipakai di mana? (hanya `README`/docs) — tidak dirujuk kode.

### G12 — Tidak ada `try/finally` di sekitar proses render
**Risiko: RENDAG**
Kalau user tutup window saat render, thread di-`daemon=True` mati → `ffmpeg_proc` jadi
yatim, file outputseparuh jadi 0-byte/corrupt, dan tidak ada penandaan. Perlu pre-check
`final_out.exists()` + validasi ukuran sebelum ditulis `desc.txt`.

---

## [X] Yang TIDAK bisa diverifikasi dari kode — harus diuji manual oleh pemilik

Semua berikut butuh Windows GUI + jaringan + API key berbayar:

1. **Hasil render visual** — tidak ada screenshot/GIF, tidak ada golden image test.
   Aku tidak bisa memastikan subtitle karaoke, grid split-screen, B-roll overlay,
   end card, dan blur cover **tampak benar** setelah refactor. Butuh render nyata.
2. **Perilaku frozen EXE** — `build_exe.py` tidak pernah dijalankan di lingkungan ini.
   Konfirmasi bahwa (a) `--onedir` menghasilkan folder yang bisa dipindah, (b) ffmpeg/yt-dlp
   benar-benar ada di dalam (saat ini **tidak**, lihat C), (c) `%APPDATA%` benar-benar dipakai.
3. **Anti-paquette AI** — kualitas analisis segmen, hook, hashtag tidak terukur.
4. **Rate limit & timeout jaringan** — perilaku retry 429 (`retry_delay=20` +15 per attempt)
   tidak diuji terhadap limit asli Gemini/Groq/OpenRouter.
5. **GPU path** — `detect_whisper_device` perlu diuji di PC bertenaga GPU **dan** PC
   tanpa GPU untuk memastikan tidak ada regresi.
6. **Migrasi config lama** — perlu diuji dengan `config.json`+v1.2.0 sungguhan.

---

## Temuan fase 5 (packaging) — urutan menurut risiko

### [P1] Known Folder Windows yang tidak bisa ditulis, dengan pesan yang menyesatkan

**Ditemukan:** saat menulis `check_output_dir()` untuk first-run check, di PC
develop sendiri.

**Gejalanya:**

```
>>> Path.home() / "Videos"
C:\Users\SOPIAN\Videos
>>> (Path.home() / "Videos" / "x").mkdir()
WinError 2: The system cannot find the file specified
```

Foldernya ada. User punya Full Control (`icacls` ->
`SOPIAN\SOPIAN:(I)(OI)(CI)(F)`). `iterdir()` berhasil. Tapi `mkdir` dan
`write_text` di dalamnya gagal.

**HIPOTESIS YANG DICEK DAN SEMUANYA SALAH:**

| Dugaan | Hasil |
|---|---|
| Atribut ReadOnly | `attrib -r` -> "Access denied". `SetFileAttributesW` -> rc=0 (gagal). Atribut tetap 0x11 |
| Symlink / reparse point | `os.readlink` -> "not a reparse point" (WinError 4390). `st_file_attributes & 0x400` = False |
| OneDrive redirect | `OneDrive\Videos` tidak ada |
| ACL kurang | Full control ada |
| Path salah (artefak MSYS) | Gagal juga lewat `cmd.exe` langsung |
| Parent tidak ada | `Videos` `is_dir()` = True, `iterdir()` = 3 entri |

**Yang membuatnya berhasil:**

| Lokasi | mkdir |
|---|---|
| `C:/Users/SOPIAN/Videos` | FAIL |
| `C:/Users/SOPIAN/Documents` | FAIL |
| `C:/Users/SOPIAN/Music` | FAIL |
| `C:/Users/SOPIAN/Pictures` | FAIL |
| `C:/Users/SOPIAN/Desktop` | FAIL |
| `C:/Users/SOPIAN/Downloads` | OK |
| `C:/Users/SOPIAN` | OK |
| `C:/Users/Public` | OK |
| `C:/` | OK |
| `%LOCALAPPDATA%\Temp` | OK |
| repo | OK |

Polanya jelas: yang gagal adalah Known Folder Windows yang dikelola shell
(`Videos`, `Documents`, `Music`, `Pictures`, `Desktop`). Yang berhasil adalah
folder biasa.

**Kenapa ini penting untuk produk yang dijual.** `default_output_dir()` adalah
`~/Videos/YTShortClipperPro`. Artinya di PC dengan kondisi seperti ini, user
mendapat error `WinError 2` yang menyiratkan foldernya hilang - padahal folder
ada di depan mata. Dan gejalanya muncul di tengah render, setelah menunggu
unduhan model.

**Status:** dideteksi oleh `clipper_firstrun.check_output_dir()` dan diberi
pesan yang jujur. Dialog wizard-nya belum ada (fase 6).

### [P2] Regresi path di `clipper_core.py` membatalkan seluruh `clipper_paths.py`

Sudah diperbaiki di commit `d08c45b` (fase-5a). Dicatat di sini karena
menunjukkan Fase 1 punya lubang: blok legacy di baris ~125 menimpa alias yang
sudah benar di baris ~58. Detail lengkap ada di pesan commit tersebut.

Pelajaran: **nilai yang benar diimport time belum tentu nilai yang dipakai.**
Test alias di Fase 1 membaca `c.TEMP_DIR` dan membandingkannya dengan
`temp_dir()` - keduanya sama saat itu, karena baris 135 belum dievaluasi.
Yang diperiksa harus urutan evaluasinya, bukan hanya nilai akhirnya.

### [P3] Nomor versi keras masih di empat tempat setelah `clipper_version.py` dibuat

`v1.2.0` di: judul window (`clipper_gui_modern.py`), badge Streamlit (`app.py`),
footer Gradio (`clipper_web.py`). Yang keempat: `clipper_web.py` menulis
`{APP_VERSION}` di dalam string biasa (bukan f-string) - jadi placeholder-nya
ditampilkan apa adanya ke user, dan ruff tidak menangkapnya.

Semua diperbaiki di fase 5, plus test struktural lewat AST untuk kelas bug
tersebut.

### [P4] `setup_pc_baru.bat` sudah usang

Di root, masih menyebut `python clipper_gui_modern.py` dan mengecek Node.js
(yang sudah tidak relevan - yt-dlp sekarang lewat pip). Digantikan
`installer/install.bat`. **Belum dihapus** karena masih mungkin dipakai user;
TODO(owner).
