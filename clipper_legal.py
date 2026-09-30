"""
clipper_legal.py — Fakta lisensi dan aset pihak ketiga, dalam bentuk kode.

Konteks
-------
Repo ini akan dijual. Yang boleh dan tidak boleh dikemas harus bisa dijawab
otomatis, bukan dari ingatan penyusun installer. Modul ini jadi satu sumber
kebenaran yang bisa dibaca test, dan dipakai first-run wizard (fase 5) untuk
menampilkan daftarpersed.
//
// Prinsip: kalau lisensi sebuah aset tidak jelas, produk TIDAK BOLEH
// mengemasnya. Aset yang bermasalah dipindah ke daftar "user harus pasang
// sendiri", bukan tetap dipakai dengan harapan tidak ada yang lihat.

Aset yang dipakai aplikasi
-------------------------
  Montserrat-*      SIL Open Font License 1.1. Aman untuk produk komersial,
                    termasuk untuk dijual — syarat wajibnya adalah menyertakan
                    teks lisensi. Lihat licenses/OFL.txt.
  ffmpeg / ffprobe  TIDAK dikemas. Binari diambil dari PATH milik user.
  yt-dlp            TIDAK dikemas. Dipanggil dari PATH / pip.
  model MediaPipe   dikemas (Apache-2.0). Lihat NOTICE-MODELS.md.

Aset yang TIDAK boleh dikemas
----------------------------
  KOMIKAX_.ttf      "All rights reserved", font komersial berbayar.
                    Dihapus dari repo. Font sistem (Impact/Arial) tetap
                    tersedia sebagai ganti.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger("clipper")

APP_LICENSE = "MIT"
APP_COPYRIGHT = "Copyright (c) 2026 YT Short Clipper Pro contributors"


@dataclass(frozen=True)
class AssetLicense:
    """Satu aset pihak ketiga + status lisensinya bagi produk komersial."""

    name: str
    version: str = ""
    license_id: str = ""
    license_file: str = ""
    bundled: bool = False
    commercial_use: bool = False
    attribution_required: bool = False
    source_url: str = ""
    notes: str = ""

    @property
    def short(self) -> str:
        if not self.bundled:
            return f"{self.name} — tidak dikemas (dipasang user/passthrough)"
        return f"{self.name} {self.version} — {self.license_id}".strip()


# --------------------------------------------------------------------------
# Aset yang DIKEMAS di installer
# --------------------------------------------------------------------------
BUNDLED_ASSETS: tuple[AssetLicense, ...] = (
    AssetLicense(
        name="Montserrat",
        version="9.000",
        license_id="SIL Open Font License 1.1",
        license_file="licenses/OFL.txt",
        bundled=True,
        commercial_use=True,
        attribution_required=True,
        source_url="https://github.com/JulietaUla/Montserrat",
        notes=(
            "Syarat OFL: teks lisensi ikut dikemas, nama font tidak boleh "
            "dipakai untuk versi modifikasi yang dianggap turunan, dan font "
            "tidak boleh dijual sendirian. Menyebut Montserrat sebagai Credit "
            "di About itu cukup dan disarankan."
        ),
    ),
    AssetLicense(
        name="MediaPipe face detector (res10 SSD)",
        license_id="Apache License 2.0",
        license_file="licenses/Apache-2.0.txt",
        bundled=True,
        commercial_use=True,
        attribution_required=True,
        source_url="https://github.com/google-ai-edge/mediapipe",
        notes=(
            "bin/deploy.prototxt, bin/detector.tflite, "
            "bin/res10_300x300_ssd_iter_140000.caffemodel"
        ),
    ),
)

# --------------------------------------------------------------------------
# Aset yang TIDAK dikemas — user pasang sendiri
# --------------------------------------------------------------------------
EXTERNAL_ASSETS: tuple[AssetLicense, ...] = (
    AssetLicense(
        name="ffmpeg / ffprobe",
        license_id="LGPL v2.1+ atau GPL v2+ (tergantung build)",
        bundled=False,
        commercial_use=True,
        attribution_required=True,
        source_url="https://ffmpeg.org/legal.html",
        notes=(
            "TIDAK ada di repo ini — bin/ hanya berisi model MediaPipe. "
            "Installer wajib menyediakan ffmpeg (winget install Gyan.FFmpeg, "
            "atau build BtbN) karena aplikasi memanggil CLI-nya, bukan link "
            "statis ke libavcodec. Build BtbN MPEG adalah GPL, bukan LGPL, "
            "jadi installer yang membawakan build GPL wajib menyediakan "
            "corresponding source. Pilih build LGPL bila ingin kewajiban lebih ringan."
        ),
    ),
    AssetLicense(
        name="yt-dlp",
        version="2026.7.4",
        license_id="Unlicense",
        bundled=False,
        commercial_use=True,
        attribution_required=False,
        source_url="https://github.com/yt-dlp/yt-dlp",
        notes="Dipasang lewat pip atau paket manager. Tidak dikemas.",
    ),
)


# --------------------------------------------------------------------------
# Aset yang DILARANG
# --------------------------------------------------------------------------
BLOCKED_ASSETS: tuple[AssetLicense, ...] = (
    AssetLicense(
        name="KOMIKAX_.ttf",
        license_id="Proprietary — All rights reserved",
        bundled=False,
        commercial_use=False,
        attribution_required=True,
        source_url="",
        notes=(
            "Dihapus dari repo pada fase 4. Font ini milik "
            "WolfBainX/Apostrophic Labs dan dijual komersial. "
            "nameID 0 berbunyi 'All rights reserved' dan tidak ada nameID 14 "
            "(URL lisensi).User yang punya lisensi boleh tetap memakainya, "
            "tapi aplikasi tidak boleh mendistribusikannya. Default subtitle "
            "sudah diganti ke Montserrat-Bold (SIL OFL)."
        ),
    ),
)


# --------------------------------------------------------------------------
# Font pengganti
# --------------------------------------------------------------------------
# TODO(owner): kalau produk ini dijual, pertimbangkan mengunduh font display
# SIL OFL sendiri (mis. Bricolage Grotesque, Gabarito, atau Plus Jakarta Sans
# untuk versi Indonesia) supaya tampilan tidak sama dengan Montserrat, yang
# dipakai ribuan aplikasi. Untuk sekarang Montserrat-Bold cukup secara lisensi.
SUBTITLE_FONT_DEFAULT = "Montserrat-Bold.ttf"

# Dipakai kalau font pilihan tidak ada. Semua bebas redistribusi.
FALLBACK_FONTS = ("Montserrat-Bold.ttf", "arialbd.ttf", "Impact.ttf")


def bundled_summary() -> str:
    """Daftar singkat untuk dialog About / first-run wizard."""
    lines = []
    for asset in BUNDLED_ASSETS:
        mark = " wajib atribusi" if asset.attribution_required else ""
        lines.append(f"- {asset.name} {asset.version}: {asset.license_id}{mark}".strip())
    for asset in EXTERNAL_ASSETS:
        lines.append(f"- {asset.name}: {asset.license_id} (tidak dikemas, dipasang terpisah)")
    return "\n".join(lines)


def redistribution_allowed() -> bool:
    """True kalau tidak ada aset terlarang yang masih ikut dikemas.

    Dipakai test sebagai gerbang rilis, dan installer untuk refuse install kalau
    ada aset bermasalah yang belum dibersihkan.
    """
    return not any(asset.bundled for asset in BLOCKED_ASSETS)


def licenses_dir():
    """Folder teks lisensi yang harus ikut installer."""
    from clipper_paths import RESOURCE_DIR

    return RESOURCE_DIR / "licenses"


def audit_installed_fonts():
    """Cek folder fonts/ dan laporkan aset yang tidak boleh ada.

    Tidak menghapus file sendiri — penghapusan file user tanpa izin adalah
    hal yang tidak boleh dilakukan aplikasi. Melaporkan saja, lalu first-run
    wizard yang memberi tahu.
    """
    from clipper_paths import RESOURCE_DIR

    fonts_dir = RESOURCE_DIR / "fonts"
    if not fonts_dir.exists():
        return []
    blocked = {a.name.lower() for a in BLOCKED_ASSETS}
    return sorted(
        f.name for f in fonts_dir.iterdir()
        if f.suffix.lower() in (".ttf", ".otf") and f.name.lower() in blocked
    )


def legal_summary_for_ui() -> dict:
    """Data siap tampil untuk UI: dict agar mudah dipakai Template."""
    return {
        "app_license": APP_LICENSE,
        "copyright": APP_COPYRIGHT,
        "bundled": [
            {"name": a.name, "version": a.version, "license": a.license_id}
            for a in BUNDLED_ASSETS
        ],
        "external": [
            {"name": a.name, "version": a.version, "license": a.license_id}
            for a in EXTERNAL_ASSETS
        ],
        "blocked": [
            {"name": a.name, "license": a.license_id, "reason": a.notes}
            for a in BLOCKED_ASSETS
        ],
    }
