# DECISIONS.md

Catatan singkat untuk keputusan desain yang tidak terlihat dari kode.
Satu entri = satu keputusan + alasannya.

---

## [D001] RESOURCE_DIR dan DATA_DIR dipisah

**Konteks.** v1.2.0 menaruh `bin/`, `fonts/`, `backsound/`, `config.json`,
`temp/`, `output/`, dan `queue_state.json` semuanya di satu `BASE_DIR`. Saat
dibekukan PyInstaller, `BASE_DIR` = `sys._MEIPASS`, yaitu folder ekstraksi
sementara. Build onefile menghapus folder itu tiap app ditutup.

**Akibatnya:** config, API key, dan hasil video hilang tiap restart.

**Keputusan.** Dua akar, dua aturan berbeda:

| | Lokasi | Aturan |
|---|---|---|
| `RESOURCE_DIR` | folder aplikasi / `_MEIPASS` | hanya baca. Tidak boleh ada satu byte pun ditulis. |
| `DATA_DIR` | `%LOCALAPPDATA%\YTShortClipperPro` | semua yang bisa ditulis |

Output video tidak di bawah `DATA_DIR` sondern default ke
`~/Videos/YTShortClipperPro` dan bisa diubah user lewat `config["output_dir"]`.

**Alasan.** Dua hal yang tidak boleh tercampur: (1) saat frozen, folder aplikasi
benar-benar read-only di beberapa konfigurasi, jadi menulis ke sana gagal dengan
error yang membingungkan; (2) cache tidak boleh ikut terhapus bersama video —
user sering menghapus folder output, dan itu tidak boleh berarti cache hilang
juga. Folder `DATA_DIR` yang terpisah juga membuat "reset app" jadi satu hal
yang jelas: hapus `%LOCALAPPDATA%\YTShortClipperPro`.

**Konsekuensi yang disengaja.** `RESOURCE_DIR` stabil untuk seluruh proses,
jadi dipanggil langsung. `DATA_DIR` bisa dipindah (test, first-run wizard),
jadi punya bentuk accessor (`temp_dir()`, `config_file()`) yang resolve saat
dipanggil; constant `DATA_DIR`/`TEMP_DIR` tetap dipertahankan sebagai alias
baca-saja supaya call site lama tidak langsung rusak.

---

## [D002] clipper_run.py adalah satu-satunya jalan eksekusi proses

**Konteks.** Hampir semua pemanggilan ffmpeg/ffprobe/yt-dlp memakai
`shell=True` dengan string f-string yang memuat link, judul, dan path dari
input user. Judul short selalu berasal dari AI, jadi ini bukan data tepercaya.

**Keputusan.** Modul baru `clipper_run.py`. `run_command()` dan
`run_streaming()` hanya menerima `Sequence[str]` — kalau diberi `str`, langsung
`TypeError`. Bukan diperbaiki diam-diam ke `shell=False`, tapi ditolak.

**Alasan.** Kalau string diam-diam diterima dengan `shell=False`, reviewer
berikutnya bisa menambahkan f-string lagi tanpa sadar bahwa kontrak aslinya sudah
berubah. Menolak string menggeser kesalahan ke waktu kompilasi dan test, bukan ke
momen runtime di depan user.

`run_cmd()` lama di `clipper_core.py` dipertahankan sebagai jembatan supaya
tidak ada caller yang langsung rusak, tapi sekarang juga menolak string.

`shell=False` tetap eksplisit di `Popen`, hanya sebagai belt-and-suspenders:
`Sequence[str]` saja tidak secara formal melarang shell.

---

## [D003] Timeout lewat watchdog thread, bukan `proc.wait(timeout=)`

**Konteks.** `subprocess.Popen.communicate(timeout=)` punyatimeout yang benar
di pustaka, tapi `wait(timeout=)` yang dikombinasikan dengan loop baca manual
tidak: loop `proc.stdout.readline()` memblokir sampai childNutup stdout-nya.

**Akibatnya.** `wait(timeout=)` tidak pernah dievaluasi. Timeout jadi hiasan —
proses yang macet menggantung selamanya.

**Keputusan.** `threading.Timer` mengirim sinyal ke proses saat deadline habis;
loop baca stdout tetap jadi urutan utama.

**Alasan.** Timeout harus jadi gatnjil yang benar-benar menyala. Plus satu
masalah nyata: membuka `stdin=PIPE` tanpa menulis *dan menutup* membuat child
menunggu EOF selamanya — hang permanen yang tidak bisa dikejar timeout karena
deadline-nya sendiri tidak pernah dievaluasi. Sekarang `stdin` ditutup eksplisit
setelah payload dikirim.

**Akibat yang perlu diketahui.** Setelah watchdog menyala, proses bisa saja
meninggalkan anak besar (ffmpeg yang sudah punya child). `clipper_run` tidak
melakukan tree-kill. Untuk proses yang dipakai sekarang (ffmpeg, ffprobe,
yt-dlp) ini cukup; kalau nanti menambah tool yang tree-nya dalam, tree-kill
perlu ditambahkan di sini, bukan di call site.

---

## [D004] safe_filename() menyaring pemisah path, bukan hanya karakter

**Konteks.** `safe_id()` yang lama hanya mengizinkan alnum, spasi, dash, dan
underscore. Judul short datang dari AI dan bisa berisi apa saja.

**Keputusan.** `safe_filename()` mengganti karakter illegal Windows, memotong ke panjang wajar, dan menutup dua kasus yang sering terlewat:

- **Nama reserved Windows** (`CON`, `PRN`, `AUX`, `NUL`, `COM1`..`COM9`,
  `LPT1`..`LPT9`) — `CON.mp4` tidak bisa dibuat di NTFS.
- **Path separator yang lolos** — nilai `..` atau `../../windows` menghasilkan
  path yang menulis ke luar folder output. Diblokir di tingkat komponen, bukan
  hanya di tingkat karakter.

**Alasan.** Sanitasi nama file adalah batas keamanan, bukan kosmetik. Judul dari
AI adalah input yang tidak dipercaya, dan `..` tidak mengandung karakter
terlarang sama sekali — cara memfilter karakter saja tidak pernah menyentuhnya.

---

## [D005] quote_for_filtergraph() untuk semua nilai non-literal

**Konteks.** Filter ffmpeg punya sintaks sendiri: `,` dan `;` memisahkan
filter, `[` `]` menandai label, `'` adalah escape, `"` menutup operand
bertanda kutip. Nilai yang masuk ke `-filter_complex` / `-vf` / `-metadata`
dari AI atau user tidak boleh bisa menyuntik filter baru.

**Keputusan.** Semua nilai yang bukan literal ffmpeg melewati
`quote_for_filtergraph()`, yang menyaring `;` `,` `[` `]` `\` `'` `"` `` ` ``
dan NUL.

**Alasan.** Karena pemanggilan string ke `shell=True` sudah dihapus, jalur
injeksi lewat shell tertutup. Tapi ffmpeg punya bahasa filter sendiri, jadi
perlu lapisan kedua. Menyaring `"` itu ditemukan oleh test, bukan oleh review —
saya lupa `"` ikut disaring; double quote menutup operand di ffmpeg.

---

## [D006] API key disimpan dengan DPAPI, bukan third-party

**Konteks.** v1.2.0 menulis `gemini_api_key`, `openrouter_api_key`,
`groq_api_key`, dan `pexels_api_key` apa adanya ke `config.json`. File itu
pretty-printed, jadi siapa pun yang membuka config bisa menyalin key; ikut
ter-backup ke cloud/OneDrive; dan pernah ikut ter-commit saat `.gitignore`
tidak berlaku.

**Keputusan.** Modul baru `clipper_secrets.py`. Di Windows, satu blob terenkripsi
DPAPI user-scope di `%LOCALAPPDATA%/YTShortClipperPro/secrets.dat`. `config.json`
tetap ada dan tetap dibaca manusia, tapi tidak lagi memuat rahasia. Migrasi dari
config lama berjalan sekali: key dipindahkan ke `secrets.dat`, lalu `config.json`
ditulis ulang tanpa key — jadi user lama tidak kehilangan apa pun.

**Kenapa DPAPI dan bukan `keyring` atau `cryptography`.** DPAPI sudah ada di
Windows, terikat ke akun user yang sedang login, dan memanggilnya cukup lewat
`ctypes` — tanpa dependensi baru untuk produk yang harus tetap ringan. `keyring`
menambahkan backend per-platform tanpa memberi keuntungan nyata di target kita;
`cryptography` memaksa kita mengelola kunci enkripsi sendiri, yang justru
menghandlung masalah yang sama lebih buruk (kunciaking perlu disimpan di
sesuatu).

**Entropi tambahan.** `CryptProtectData` diberi entropi opsional yang hanya app
ini yang tahu. Tanpa itu, blob user-scope bisa dibuka proses lain milik user
yang sama — misalnya aplikasi lain yang dikompromi. Kesetimbangan yang
sengaja diambil: kalau binary-nya dibalik, entropi bocor, tapi DPAPI tetap
menjaga privasi lintas akun. Untuk Serialize key milik user, itu cukup.

**Fallback di luar Windows.** Tidak ada DPAPI, jadi key disimpan sebagai JSON
dengan permission 0600 dan modul ini menghasilkan peringatan jujur lewat
`describe_protection()`. Cukup untuk dev dan CI; first-run wizard (Fase 5)
WAJIB memberi tahu user bahwa perlindungannya lebih lemah. Target rilis tetap
Windows, jadi jalur ini tidak menyentuh user rilis.

---

## [D007] Penghapusan secret berarti hapus, bukan "simpan yang kosong"

**Konteks.** `load_config()` versi lama membuang semua string kosong dari config,
sehingga user tidak pernah bisa mengosongkan field API key — begitu dihapus,
nilai lama langsung kembali muncul. Ini AUDIT.md G6.

**Keputusan.** `set_secret(field, "")` menghapus field dari blob, dan
`save_config()` menarik seluruh `SECRET_FIELDS` keluar dari dict sebelum menulis
JSON. Kalau tidak ada secret yang tersisa, file `secrets.dat` dihapus.

**Alasan.** "Kosong" adalah nilai yang valid untuk preference biasa (tema, path)
tetapi bukan untuk rahasia. Membedakan keduanya perlu tempat berbeda — yang ini
memang membuat `config.json` bersih dibaca orang, dan `secrets.dat` tidak pernah
berisi entri kosong yang membingungkan.

---

## [D008] Redaksi di level logging, bukan di setiap call site

**Konteks.** Key bisa bocor ke log bukan cuma dari kode kita, tapi juga dari
exception library pihak ketiga (`requests`, `google-genai`) yang kadang menyertakan
URL berisi key di pesan error.

**Keputusan.** `RedactingFormatter` disisipkan di kedua handler (file dan
console). `redact()` menyensor nilai yang sudah terdaftar (`register_secret`) dan
pola key yang dikenali (`AIza…`, `gsk_…`, `sk-or-v1-…`, `sk-…`) untuk menangkap
key yang belum pernah terdaftar — misalnya yang hanya ada di environment
variable.

**Alasan.** Menyensor di setiap call site selalu bocor di satu tempat yang lupa.
Menyensor di level handler menutup semua jalur sekaligus. Pola regex menutup
key dari env yang tidak pernah melewati `register_secret`. Nilai dengan panjang
< 8 sengaja tidak didaftarkan: menyensor "a" membuat log tak terbaca tanpa
menambah keamanan yang berarti.

---

## [D009] Output AI diperlakukan sebagai input yang tidak dipercaya

**Konteks.** Output AI langsung berakhir jadi argumen ffmpeg, nama file, dan teks
yang ditampilkan ke user. Jadi ia tidak lebih dipercaya daripada input user —
bedanya hanya datang lewat jaringan, sehingga gagal lebih jarang terlihat.

Tiga kelas masalah nyata:

1. **JSON rusak.** Model sering membungkus JSON di ``` ``` ```, menambah
   penjelasan di depan, atau menambah karakter kontrol. `json.loads` gagal dan
   seluruh hasil analisis hilang.
2. **JSON valid tapi salah bentuk.** `{"start": "abc"}` lolos parse lalu meledak
   di `time_str_to_seconds` — jauh dari tempat masalahnya, dan setelah AI sudah
   spends token.
3. **Prompt dengan placeholder kosong.** `GEMINI_PROMPT` punya `{transcript}`,
   dan tombol "Analisis" mengirim apa adanya, sehingga model menerima string
   literal `{transcript}` lalu mengarang analisis dari nol (AUDIT.md G1).
   Hasilnya terlihat meyakinkan dan sama sekali tidak berdasarkan video user.

**Keputusan.** Modul baru `clipper_ai.py`.

- `extract_json()` mencoba urutan dari ketat ke longgar: fence, karakter kontrol,
  lalu potongan dengan kurung kurawal seimbang.
- `segments_from_response()` mengembalikan objek `Segment` yang sudah
  divalidasi, bukan `dict` mentah. Field hilang diisi default; timestamp rusak
  jadi "tidak ada"; `end <= start` diperbaiki.
- `build_prompt()` **menolak** placeholder yang tidak terisi dengan `ValueError`.

**Alasan menolak, bukan mengirim string kosong.** Mengirim `transcript=""` ke AI
tetap menghasilkan analisis yang terdengar masuk akal. Menolak membuat masalahnya
terlihat di log, dan user bisa memperbaikinya. Untuk kasus "Analisis" yang memang
sengaja tanpa transkrip, pemanggil mengirim nilai yang menjelaskan situasinya —
bukan diam-diam mengarang.

**Kenapa `end` dinaikkan, bukan ditukar.** `start=60, end=10` setelah ditukar
menjadi `10..60`, yaitu segmen yang tidak ada di video. Menaikkan `end` memberi
user sesuatu yang bisa dilihat dan diedit; menukar menghasilkan video yang salah
diam-diam. Render menolak rentang terbalik di tempat lain juga (AUDIT.md G3), jadi
ini lapisan kedua.

---

## [D010] Retry hanya untuk error yang mungkin membaik

**Konteks.** Loop lama mencoba 3 kali, tapi `sleep()` hanya di 429 dan semua error
lain langsung `raise` di percobaan pertama. Jadi timeout dan 502 tidak pernah
dicoba ulang — loop itu hanya bekerja untuk rate limit, dan bahkan di sana
`Retry-After` dari server diabaikan.

**Keputusan.** Modul baru `clipper_retry.py`.

- Klasifikasi error: `RETRYABLE_STATUS` (408/429/5xx) vs `FATAL_STATUS`
  (401/403/404/422). Error tanpa status — timeout, connection reset — dianggap
  retryable.
- Backoff eksponensial + jitter, `Retry-After` diprioritaskan.
- API key yang tidak ada dicek **sebelum** request, jadi user dapat pesan jelas
  alih-alih HTTP 401 setelah menunggu.

**Alasan.** 401 tidak akan membaik dengan mencoba lagi; mencoba hanya membuang
kuota dan menipu user dengan spinner. Sebaliknya, 429/502 hampir selalu sementara.
Jitter penting karena tanpa itu beberapa request yang gagal bersamaan akan
menghantam server di detik yang sama — pola yang justru memperlambat pemulihan
rate limit.

**Alasan tidak menghapus API key dari `config` sebagai sumber.** `load_config`
sudah mengisinya dari secret store (fase 2), jadi kode ini membaca dari `config`
seperti biasa. Tidak ada jalur baca key dari environment di sini — kalau ada, itu
membuat perilaku berbeda antara dev dan rilis.

---

## [D011] Font berlisensi komersial dihapus, bukan cuma "dilarang pakai"

**Konteks.** `fonts/KOMIKAX_.ttf` adalah default subtitle. Dibaca dengan
fontTools: `nameID 0` = "© 1999-2001, WolfBainX & Apostrophic Labs. All rights
reserved", dan **tidak ada `nameID 14`** (tanda tidak ada URL lisensi). Font ini
dijual komersial oleh pembuatnya.

**Keputusan.** File dihapus dari repo. Default subtitle jadi `Montserrat-Bold.ttf`
(SIL OFL, terverifikasi `nameID 14` = openfontlicense.org). Pengguna yang punya
lisensi KOMIKAX masih bisa memilihnya lewat Settings — yang hilang hanya
hak untuk mendistribusikannya.

**Alasan menghapus, bukan hanya memperingatkan.** Font yang tidak boleh
didistribusikan tidak bisa "berdiam" di repo hanya karena aplikasi tidak
memakainya secara default: repo ini sendiri adalah distribusi. Selalu ada
kemungkinan build script menyalin seluruh folder `fonts/`. Menghapus satu file
lebih murah dan lebih pasti daripada berharap tidak ada yang menyalin.

**Kenapa Montserrat boleh.** SIL OFL 1.1 mengizinkan penggunaan komersial,
termasuk menjual Font Software sebagai bagian dari aplikasi — yang dilarang
adalah menjual font itu sendirian. Kewajibannya: sertakan teks lisensi
(`licenses/OFL.txt`) dan jangan gunakan nama "Montserrat" untuk font turunan
yang sudah dimodifikasi.

---

## [D012] BGM dari stock video Pexels dihapus

**Konteks.** `ensure_bgm()` mencari video di Pexels dengan query
`{mood}+music`, lalu mengambil audio track-nya pakai ffmpeg `-vn`.

**Keputusan.** Fallback itu dihapus. BGM sekarang hanya dari file lokal milik
user di `%LOCALAPPDATA%/YTShortClipperPro/bgm/`.

**Alasan.** Pexels adalah library foto dan video, bukan library musik. Audio dari
stock video bukan musik — hasilnya terdengar seperti cuplikan video, dan yang
lebih penting lisensinya tidak dirancang untuk penggunaan musik. Untuk produk
yang dijual, ini risiko yang tidak perlu diambil, terutama karena BGM adalah
**enhancement**: tanpa BGM videonya tetap jalan.

Perubahan perilaku yang disengaja: sebelumnya fallback yang gagal tidak terlihat,
sekarang mood tanpa file BGM menghasilkan render tanpa BGM **dengan pesan di log**. Itu
lebih jujur daripada diam-diam menghasilkan video dengan trek yang salah.

---

## [D013] Minimum Python 3.10, ditentukan kode kita sendiri

**Konteks.** Brief menyebut `google-genai` butuh >= 3.9, jadi ada tekanan untuk
mengganti 3.8 di README jadi 3.9.

**Setelah diverifikasi, itu bukan jawabannya.** Dua fakta:

1. `google-genai` memang `>=3.9`. Tapi Mediapipe 0.10.x juga mengizinkan 3.9
   (sudah dicek: wheel `py3` tersedia untuk 3.9). Jadi Mediapipe bukan pembatas.
2. Pembatas sebenarnya adalah kode kita: `clipper_core.py` memakai anotasi
   PEP 604 (`dict | None`) **tanpa** `from __future__ import annotations`. PEP 604
   butuh Python 3.10.

**Keputusan.** Floor = **3.10**, diuji sampai 3.12, anjuran 3.12. Semua angka
hidup di `clipper_version.py`; README, `build_exe.py`, dan `setup_pc_baru.bat`
harus membacanya dari sana.

**Kenapa tidak turunkan ke 3.9 dengan menambah future import.** Menambah
`from __future__ import annotations` ke file 2000+ baris di tengah refactor
berisiko mengubah perilaku hal lain, dan 3.9 sendiri sudah EOL (Oktober 2025) —
produk berbayar tidak sebaiknya bergantung padanya. Ditandai `TODO(owner)` di
`clipper_version.py` kalau dukungan 3.9 nanti benar-benar dibutuhkan.

**Test yang menjaga alasannya.** `test_code_syntax_requires_min_python` gagal kalau
siapa pun menurunkan angka ini ke 3.9 tanpa addressing PEP 604 — supaya
perubahan tidak lolos diam-diam.

---

## [D014] Aset yang lisensinya tidak jelas tidak boleh dikemas

**Konteks.** `backsound/kocak.mp3` dan `backsound/sedih.mp3` ada di repo tanpa
LICENSE, tanpa sumber, tanpa metadata pencipta. `THIRD_PARTY_NOTICES.md`
sekarang menandai keduanya sebagai **blokir rilis**, bukan sekadar catatan.

**Prinsip.** Untuk aset yang lisensinya tidak jelas, ada dua pilihan: hapus, atau
tandai eksplisit sebagai syarat rilis. Untuk dua file BGM ini, keduanya belum
dikerjakan karena butuh keputusan produk — user mungkin punya lisensi, atau
mungkin tidak tahu sama sekali.

**Kenapa tidak diam-diam hapus sekarang.** Menghapus aset yang mungkin
dibeli/dikumpulkan user adalah keputusan yang bukan hak kode untuk diambil
sendiri. Yang bisa dan harus dilakukan kode sekarang adalah memastikan tidak ada
**keraguan** yang tersembunyi: file ditandai di THIRD_PARTY_NOTICES.md sebagai
"provenance tidak diketahui", dan test menjaga agar tidak ada aset terlarang yang
ter-kemas diam-diam.
