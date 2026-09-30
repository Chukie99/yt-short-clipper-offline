"""
clipper_paths.py — Pemisahan path RESOURCE (baca-saja) vs DATA (bisa tulis).

Kenapa modul ini ada
--------------------
v1.2.0 menaruh SEMUA folder di satu `BASE_DIR`. Saat dibekukan dengan PyInstaller,
`BASE_DIR` = `sys._MEIPASS`, yaitu folder TEMPORER yang dihapus saat aplikasi ditutup.
Akibatnya `config.json`, folder `output/`, cache `temp/`, dan `error.log` ikut hilang.
Detail + konsekuensi ada di AUDIT.md bagian A.

Konsep
------
RESOURCE_DIR  read-only. Isi: `bin/`, `fonts/`, `backsound/`, `vendor/`, `logo.png`,
              `input_thumbnail.*`. Lokasi = folder aplikasi (frozen) atau root repo
              (dev). Tidak pernah ditulis oleh aplikasi.

DATA_DIR      writable, milik user. Lokasi = `%LOCALAPPDATA%/<APP_DIR_NAME>`.
              Isi: `config.json`, `temp/`, `logs/`, `bgm/` (BGM hasil download),
              `queue_state.json`, `cookies.txt`.

OUTPUT_DIR    default `~/Videos/<APP_DIR_NAME>`, bisa diubah user lewat
              `output_dir` di config. Tidak diletakkan di dalam APP_DIR supaya user
              tidak salah menghapus cache dan ikut menghapus video.

Aturan keras: kalau sebuah path hanya dibaca → RESOURCE_DIR. Kalau ditulis → DATA_DIR
atau OUTPUT_DIR. Kalau ragu, tulis ke DATA_DIR.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from clipper_version import APP_VERSION

# TODO(owner): nama produk ini belum diputuskan. Ganti di sini SEKALI — dipakai
# untuk folder %APPDATA%, folder output default, judul window, dan nama registry
# installer. Setelah diganti, cek juga docs/DECISIONS.md dan README.
# Versi aplikasi TIDAK didefinisikan di sini. Satu sumber kebenaran ada di
# clipper_version.py — dipakai juga oleh README, build_exe.py, dan setup_pc_baru.bat.
APP_NAME = "YT Short Clipper Pro"
APP_DIR_NAME = "YTShortClipperPro"

# Config versi 2 = sudah pakai pemisahan path. Bumped setiap kali ada field baru
# yang butuh migrasi dari config lama.
CONFIG_SCHEMA_VERSION = 2


# --------------------------------------------------------------------------
# RESOURCE_DIR
# --------------------------------------------------------------------------
def resource_dir() -> Path:
    """Folder yang hanya dibaca: bin/, fonts/, backsound/, vendor/.

    Saat frozen (PyInstaller onedir/onefile) ini `sys._MEIPASS`, yang TIDAK boleh
    dipakai untuk menulis apa pun.
    """
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).parent.absolute()


RESOURCE_DIR = resource_dir()


# --------------------------------------------------------------------------
# DATA_DIR
# --------------------------------------------------------------------------
def data_dir() -> Path:
    """Folder data milik user. Menghormati override env untuk testing.

    `CLIPPER_DATA_DIR` hanya dipakai test/dev — jangan di-set di produksi.
    """
    override = os.environ.get("CLIPPER_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / APP_DIR_NAME


DATA_DIR = data_dir()

# Sub-folder didefinisikan sebagai accessor + snapshot di bawah (lihat catatan
# "Accessor untuk path yang bisa berubah"). Snapshot dipakai hanya oleh kode yang
# butuh path stabil sejak import; semua operasi tulis memakai accessor.


def prepend_bin_to_path() -> None:
    """Expose `bin/` (ffmpeg/yt-dlp/detector) ke PATH.

    Hanya supaya `ffprobe` dan `ffmpeg` yang dipanggil sebagai literal bisa
    ditemukan — lihat AUDIT.md G7/G8.
    """
    bundled = RESOURCE_DIR / "bin"
    if bundled.exists() and str(bundled) not in os.environ.get("PATH", ""):
        os.environ["PATH"] = str(bundled) + os.pathsep + os.environ.get("PATH", "")


def resource_file(*parts: str) -> Path:
    """Path file read-only. Tidak ada yang boleh menulis ke hasil ini."""
    return RESOURCE_DIR.joinpath(*parts)


# --------------------------------------------------------------------------
# Accessor untuk path yang bisa berubah
# --------------------------------------------------------------------------
# Constant di bawah hanya snapshot saat import. Kalau aplikasi perlu memindahkan
# data dir (mis. first-run wizard, atau test lewat CLIPPER_DATA_DIR), pemanggil
# WAJIB memakai accessor supaya nilai baru ikut terpakai — bukan constant lama.
# clipper_core memakai accessor untuk semua yang bisa berubah.

def temp_dir() -> Path:
    return data_dir() / "temp"


def log_dir() -> Path:
    return data_dir() / "logs"


def bgm_dir() -> Path:
    return data_dir() / "bgm"


def config_file() -> Path:
    return data_dir() / "config.json"


def queue_state_file() -> Path:
    return data_dir() / "queue_state.json"


def default_output_dir() -> Path:
    """Folder video hasil render. Default: ~/Videos/<APP_DIR_NAME>."""
    return Path.home() / "Videos" / APP_DIR_NAME


def output_dir_from_config(config: dict) -> Path:
    """Output dir dari config, jatuh ke default kalau kosong/tidak bisa dipakai."""
    raw = (config or {}).get("output_dir") or ""
    if not str(raw).strip():
        return default_output_dir()
    return Path(str(raw)).expanduser()


# Snapshot import-time. Dipakai hanya di luar app yang butuh path stabil
# (mis. logging handler yang dibuat sekali saat import).
TEMP_DIR = DATA_DIR / "temp"
LOG_DIR = DATA_DIR / "logs"
BGM_DIR = DATA_DIR / "bgm"
CONFIG_FILE = DATA_DIR / "config.json"
QUEUE_STATE_FILE = DATA_DIR / "queue_state.json"

_WRITE_DIRS = ("temp", "logs", "bgm")


def ensure_dirs() -> None:
    """Buat DATA_DIR + sub-folder temp/logs/bgm. Aman dipanggil berulang kali."""
    data_dir().mkdir(parents=True, exist_ok=True)
    for sub in _WRITE_DIRS:
        (data_dir() / sub).mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------
# Migrasi dari config.json v1.x (yang menaruh config di BASE_DIR)
# --------------------------------------------------------------------------
def legacy_config_candidates() -> list[Path]:
    """Lokasi config.json versi lama, dari yang paling mungkin sampai palingCELL."""
    return [
        RESOURCE_DIR / "config.json",   # dev: root repo
        Path(sys.executable).parent / "config.json" if getattr(sys, "frozen", False) else RESOURCE_DIR / "config.json",
    ]


def migrate_legacy_config() -> dict:
    """Pindahkan config lama ke DATA_DIR kalau belum ada. Kembalikan config hasil.

    Aturan: config lama TIDAK dihapus (user mungkin masih butuh, dan path-nya bisa
    belum bisa ditulis). Yang dipindah adalah salinan. Kalau DATA_DIR sudah punya
    config, migrasi dilewati sepenuhnya — file user tidak ditimpa.
    """
    ensure_dirs()
    dest = config_file()
    if dest.exists():
        return {}

    for candidate in legacy_config_candidates():
        if not candidate.exists():
            continue
        try:
            raw = json.loads(candidate.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            # Config lama rusak: jangan hapus, jangan crash. Default tetap dipakai.
            continue
        if not isinstance(raw, dict):
            continue
        raw["config_schema_version"] = CONFIG_SCHEMA_VERSION
        try:
            dest.write_text(
                json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except OSError:
            continue
        return {"migrated_from": str(candidate)}

    return {}


def adopt_legacy_output_dir(config: dict) -> dict:
    """Kalau user lama punya folder output berisi video, jadikan default.

    Menghapus default `~/Videos/...` dan menggantinya dengan folder output lama
    lebih baik daripada video user "hilang" setelah update. Folder output kosong
    diabaikan supaya user baru tidak ikut menunjuk folder yang tidak pernah dipakai.
    """
    if config.get("output_dir"):
        return config
    legacy = RESOURCE_DIR / "output"
    try:
        has_content = legacy.is_dir() and any(legacy.iterdir())
    except OSError:
        has_content = False
    if has_content:
        config["output_dir"] = str(legacy)
    return config


def copy_legacy_queue_state() -> bool:
    """Salin queue_state lama supaya batch yang belum selesai bisa di-resume."""
    dest = queue_state_file()
    if dest.exists():
        return False
    for candidate in (RESOURCE_DIR / "queue_state.json", RESOURCE_DIR / "temp" / "queue_state.json"):
        if candidate.exists():
            try:
                shutil.copy2(candidate, dest)
                return True
            except OSError:
                return False
    return False


def app_data_summary() -> dict:
    """Ringkasan folder untuk log/dialog About — berguna saat user lapor bug."""
    return {
        "app": APP_NAME,
        "version": APP_VERSION,
        "resource_dir": str(RESOURCE_DIR),
        "data_dir": str(data_dir()),
        "default_output_dir": str(default_output_dir()),
        "frozen": bool(getattr(sys, "frozen", False)),
        "python": sys.version.split()[0],
    }
