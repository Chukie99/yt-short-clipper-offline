# THIRD-PARTY NOTICES

Aplikasi ini mendistribusikan aset pihak ketiga berikut.
Daftar ini dibuat oleh `clipper_legal.py` dan dijaga sebagai satu sumber
kebenaran — kalau ada aset yang berubah statusnya, ubah di sana dulu.

> **TODO(owner):** file ini wajib ikut installer dan halaman About. Installer
> tidak boleh rilis kalau `licenses/` tidak ada di paket.

---

## 1. Dikemas di installer

### Montserrat (family font, subset yang dipakai)
- **Lisensi:** SIL Open Font License 1.1
- **Teks lisensi:** `licenses/OFL.txt`
- **Sumber:** https://github.com/JulietaUla/Montserrat
- **Kegunaan:** font subtitle bawaan

OFL mengizinkan penggunaan komersial. Kewajiban yang harus dipenuhi:

1. Teks lisensi (OFL.txt) ikut disertakan — sudah ada di folder `licenses/`.
2. Font tidak boleh dijual sendirian sebagai aset.
3. Font tidak boleh dinamai ulang jika sudah dimodifikasi.
4. Menyebut "Montserrat" sebagai Credit di halaman About adalah voluntarily encouraged
   oleh OFL, dan sangat disarankan di sini karena Montserrat dipakai ribuan
   produk lain — kredit soal siapa yang benar-benar memakai font ini berarti.

### MediaPipe — model deteksi wajah
- **Lisensi:** Apache License 2.0
- **Teks lisensi:** `licenses/Apache-2.0.txt`
- **Sumber:** https://github.com/google-ai-edge/mediapipe
- **File:** `bin/deploy.prototxt`, `bin/detector.tflite`,
  `bin/res10_300x300_ssd_iter_140000.caffemodel`

Apache 2.0 mengizinkan penggunaan komersial. Kewajiban: menyertakan teks lisensi
dan salinan Makers NOTICE bila ada. Ketiganya file binary model, bukan kode
aplikasi, jadi tidak ada kewajiban source code dari kode aplikasi.

---

## 2. TIDAK dikemas — dipasang pengguna

### ffmpeg / ffprobe
- **Lisensi:** LGPL v2.1+ atau GPL v2+, tergantung build
- **Sumber:** https://ffmpeg.org/legal.html
- **Kenapa tidak dikemas:** aplikasi memanggil `ffmpeg` sebagai **proses terpisah**
  dari PATH. Tidak ada tautan statis ke libavcodec, jadi tidak ada kewajiban
  LGPL "reverse engineering" untuk library yang dipanggil terpisah.

**Tapi perhatikan ini penting untuk installer:** sebagian besar build ffmpeg yang
populer — termasuk build BtbN/FFmpeg-Builds — dikompilasi dengan `--enable-gpl`.
Build GPL memaksa kewajiban berikut bila Anda mendistribusikan binernya:

1. Menyediakan corresponding source code.
2. Menjual dengan lisensi GPL (bukan proprietary).
3. Menjual tanpa tambahan warranty.

Installer karena itu punya dua jalur yang bisa dipilih:

| Opsi | Lisensi | Kewajiban | Rekomendasi |
|---|---|---|---|
| Build LGPL-only | LGPL | Hanya sertakan teks lisensi | ✅ lebih ringan, pilih ini |
| Build GPL (BtbN) | GPL | Source + same license | Untuk ACM internal saja |

Yang paling aman untuk produk berbayar: **installer memaketkan build LGPL-only**,
atau mendeteksi ffmpeg di PATH dan membiarkan pengguna yang sudah punya.

Pengguna Windows biasanya sudah punya ffmpeg dari WinGet:

```
winget install Gyan.FFmpeg
```

### yt-dlp
- **Lisensi:** Unlicense (domain publik)
- **Sumber:** https://github.com/yt-dlp/yt-dlp
- **Kenapa tidak dikemas:** dipasang lewat pip atau package manager; bukan aset statis.
- **Catatan penting:** yt-dlp rusak sering kali setelah YouTube berubah. Pastikan
  installer memperbarui versi ini, atau minimal mendeteksi versi lama saat start.

---

## 3. Dihapus dari repo

### ~~KOMIKAX_.ttf~~ (font Komika Axis)
- **Status:** ~~dikemas~~ → **tidak lagi dikemas**, dihapus pada fase 4
- **Alasan:** `nameID 0` berbunyi "© 1999-2001, WolfBainX & Apostrophic Labs.
  All rights reserved". Tidak ada `nameID 14` (URL lisensi). Font inidijual komersial oleh pembuatnya.
- **Dampak:** default subtitle diganti ke `Montserrat-Bold.ttf` (SIL OFL).
  Pengguna yang punya lisensi font ini boleh tetap memilihnya lewat Settings.

---

## 4. Aset yang perlu klarifikasi sebelum rilis

### `backsound/kocak.mp3` dan `backsound/sedih.mp3`
- **Status:** **provenance tidak diketahui.** Tidak ada LICENSE, tidak ada sumber,
  tidak ada metadata ID3 yang mencatat pencipta.
- **Masalah:** kedua file ini ikut ter-commit dan akan ikut ter-install. Kalau
  berasal dari YouTube "no copyright" atau dari sumber yang tidak jelas, audio
  tersebut tetap memiliki hak cipta. Label "no copyright" di YouTube tidak
 Tidak menjamin bebas royalti.
- **Syarat rilis (WAJIB):** ganti dengan musik berlisensi jelas — misalnya dari
  YouTube Audio Library (cek tiap track: sebagian punya syarat atribusi),
  Free Music Archive dengan lisensi CC0, atau beli dari Artlist/Epidemic Sound.
  Ganti juga kode fallback `ensure_bgm()` supaya tidak lagi mengambil audio dari
  stock video Pexels (lihat DECISIONS.md [D012]).

###BGM fallback dari Pexels
- **Status:** **akan dihapus** (fase 4/fase 5).
- **Alasan:** Pexels adalah library foto dan video, bukan library musik.
  Mengambil audio dari stock video untuk BGM menghasilkan trek yang terdengar
  seperti video, dan lisensinya tidak jelas untuk keperluan musik.
