"""
clipper_secrets.py — Penyimpanan API key yang tidak plaintext.

Konteks
-------
v1.2.0 menulis `gemini_api_key`, `openrouter_api_key`, `groq_api_key`, dan
`pexels_api_key` apa adanya ke `config.json`. File itu:
  1. dibaca pretty-printed, jadi siapa pun yang membuka config bisa langsung
     menyalin key-nya;
  2. ikut ter-backup ke cloud drive atau sinkronisasi OneDrive;
  3. sering ikut ter-commit kalau `.gitignore` tidak sengaja tidak berlaku.

DPAPI
-----
Windows sudah punya mekanisme yang tepat untuk ini: DPAPI (Data Protection API).
Enkripsi terikat ke akun user Windows yang sedang login — proses milik user lain
tidak bisa membukanya, dan administrator pun tidak bisa tanpa kredensial. Persis
yang dibutuhkan untuk "API key milik user".

Jadi di Windows: `secrets.dat` berisi satu blob terenkripsi DPAPI (user-scope).
`config.json` tetap ada dan tetap dibaca manusia, tapi tidak lagi memuat rahasia.

Di luar Windows tidak ada DPAPI. Fallback-nya file biasa dengan permission 0600
dan peringatan di log — cukup untuk dev dan CI, TIDAK cukup untuk rilis. Lihat
`protection_kind()` dan `describe_protection()`.
"""
from __future__ import annotations

import ctypes
import json
import logging
import os
import platform
import re
import sys
from ctypes import wintypes
from pathlib import Path

from clipper_paths import APP_DIR_NAME, data_dir, ensure_dirs

logger = logging.getLogger("clipper")

# Field config yang dianggap rahasia. Dipisah dari config.json ke secrets.dat.
SECRET_FIELDS = (
    "gemini_api_key",
    "openrouter_api_key",
    "groq_api_key",
    "pexels_api_key",
)

# Environment variable sebagai fallback kalau secret belum pernah disimpan.
ENV_FOR_FIELD = {
    "gemini_api_key": "GEMINI_API_KEY",
    "openrouter_api_key": "OPENROUTER_API_KEY",
    "groq_api_key": "GROQ_API_KEY",
    "pexels_api_key": "PEXELS_API_KEY",
}

# Entropi tambahan untuk DPAPI. Tanpa ini, blob user-scope masih bisa dibuka
# proses lain milik user yang sama. Dengan entropi yang hanya app ini yang tahu,
# proses lain harus menebak passphrase-nya lebih dulu.
_ENTROPY = b"YTShortClipperPro/secrets/v1:" + APP_DIR_NAME.encode("utf-8")

_SECRETS_VERSION = 1

# Magic untuk fallback plaintext, supaya file bisa dikenali tanpa menebak.
_PLAINTEXT_MAGIC = b"CLIPSEC1:"

_CRYPTPROTECT_UI_FORBIDDEN = 0x1


# --------------------------------------------------------------------------
# DPAPI lewat ctypes (tanpa dependensi baru)
# --------------------------------------------------------------------------
if sys.platform == "win32":
    class _Blob(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_char)),
        ]

    _crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    def _blob_from_bytes(data: bytes):
        """Bentuk DATA_BLOB dari bytes. Buffer harus hidup selama blob dipakai."""
        buf = ctypes.create_string_buffer(data, len(data))
        blob = _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
        # Disimpan sebagai atribut supaya buffer tidak di-GC sebelum dibaca.
        blob._keepalive = buf  # type: ignore[attr-defined]
        return blob

    def _bytes_from_blob(blob) -> bytes:
        return ctypes.string_at(blob.pbData, blob.cbData)

    def _dpapi_protect(data: bytes) -> bytes:
        in_blob = _blob_from_bytes(data)
        ent_blob = _blob_from_bytes(_ENTROPY)
        out = _Blob()
        if not _crypt32.CryptProtectData(
            ctypes.byref(in_blob),
            None,
            ctypes.byref(ent_blob),
            None,
            None,
            _CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(out),
        ):
            raise OSError(ctypes.get_last_error(), "CryptProtectData gagal")
        try:
            return _bytes_from_blob(out)
        finally:
            _kernel32.LocalFree(out.pbData)

    def _dpapi_unprotect(data: bytes) -> bytes:
        in_blob = _blob_from_bytes(data)
        ent_blob = _blob_from_bytes(_ENTROPY)
        out = _Blob()
        if not _crypt32.CryptUnprotectData(
            ctypes.byref(in_blob),
            None,
            ctypes.byref(ent_blob),
            None,
            None,
            _CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(out),
        ):
            raise OSError(ctypes.get_last_error(), "CryptUnprotectData gagal")
        try:
            return _bytes_from_blob(out)
        finally:
            _kernel32.LocalFree(out.pbData)

else:
    class _Blob:  # noqa: D101 — stub supaya modul tetap bisa diimpor di Linux/macOS
        pass

    def _dpapi_protect(data: bytes) -> bytes:
        raise OSError("DPAPI hanya tersedia di Windows")

    def _dpapi_unprotect(data: bytes) -> bytes:
        raise OSError("DPAPI hanya tersedia di Windows")


# --------------------------------------------------------------------------
# Lokasi file
# --------------------------------------------------------------------------
def secrets_file() -> Path:
    """Path blob secret. Selalu di DATA_DIR, tidak pernah di folder aplikasi."""
    return data_dir() / "secrets.dat"


def protection_kind() -> str:
    """'dpapi' di Windows, 'plaintext' di platform lain."""
    return "dpapi" if sys.platform == "win32" else "plaintext"


# --------------------------------------------------------------------------
# (de)serialisasi blob
# --------------------------------------------------------------------------
def _encode(payload: dict, kind: str) -> bytes:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if kind == "dpapi":
        return _dpapi_protect(raw)
    return _PLAINTEXT_MAGIC + raw


def _decode(blob: bytes) -> dict:
    if blob.startswith(_PLAINTEXT_MAGIC):
        raw = blob[len(_PLAINTEXT_MAGIC):]
    else:
        raw = _dpapi_unprotect(blob)
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("blob secret bukan objek JSON")
    values = data.get("values")
    return values if isinstance(values, dict) else {}


# --------------------------------------------------------------------------
# API publik
# --------------------------------------------------------------------------
def load_secrets() -> dict:
    """Baca semua secret. Kembalikan dict kosong kalau belum ada atau rusak.

    Tidak pernah melempar exception: secret yang tidak terbaca harus bisa
    diperbaiki lewat Settings, bukan membuat app tidak bisa dibuka.
    """
    path = secrets_file()
    if not path.exists():
        return {}
    try:
        values = _decode(path.read_bytes())
    except Exception as e:  # noqa: BLE001 — sengaja luas, lihat docstring
        logger.warning(
            "secrets.dat tidak bisa dibaca (%s). Key mungkin perlu diisi ulang di Settings.",
            type(e).__name__,
        )
        return {}
    return {k: v for k, v in values.items() if isinstance(v, str) and v}


def save_secrets(values: dict) -> None:
    """Simpan secret. Dict tanpa nilai berarti hapus file.

    Menulis ulang seluruh blob, jadi ini operasi yang jarang — tidak dipanggil
    di hot path.
    """
    ensure_dirs()
    path = secrets_file()
    keep = {
        k: v for k, v in values.items()
        if k in SECRET_FIELDS and isinstance(v, str) and v
    }
    if not keep:
        path.unlink(missing_ok=True)
        return
    payload = {"version": _SECRETS_VERSION, "values": keep}
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(_encode(payload, protection_kind()))
    tmp.replace(path)
    for v in keep.values():
        register_secret(v)


def get_secret(field: str) -> str:
    """Satu secret, dengan fallback ke environment variable."""
    value = load_secrets().get(field, "")
    if value:
        return value
    env_name = ENV_FOR_FIELD.get(field, "")
    return os.environ.get(env_name, "") or "" if env_name else ""


def set_secret(field: str, value: str) -> None:
    """Set satu secret. String kosong berarti HAPUS, bukan "simpan yang kosong".

    Inilah yang bikin user akhirnya bisa mengosongkan field API key di Settings.
    """
    current = load_secrets()
    value = (value or "").strip()
    if value:
        current[field] = value
        register_secret(value)
    else:
        current.pop(field, None)
    save_secrets(current)


def has_secrets() -> bool:
    return bool(load_secrets())


def delete_all_secrets() -> None:
    """Hapus semua secret. Dipakai fitur 'reset app'."""
    secrets_file().unlink(missing_ok=True)
    _SECRET_REGISTRY.clear()


# --------------------------------------------------------------------------
# Redaksi untuk log
# --------------------------------------------------------------------------
# Nilai secret yang diketahui. Diisi setiap kali config dimuat atau secret disimpan.
_SECRET_REGISTRY: set[str] = set()


def register_secret(value: str) -> None:
    """Ingat sebuah nilai supaya bisa disensor di log.

    Nilai pendek diabaikan: menyensor "a" membuat semua pesan tak terbaca tanpa
    menambah keamanan yang berarti.
    """
    if isinstance(value, str) and len(value.strip()) >= 8:
        _SECRET_REGISTRY.add(value.strip())


def reset_secret_registry() -> None:
    _SECRET_REGISTRY.clear()


# Pola key yang dikenal, untuk menangkap key yang belum pernah di-register
# (mis. key yang keluar dari environment variable, bukan dari config tersimpan).
_KEY_PATTERNS = re.compile(
    r"(AIza[0-9A-Za-z_\-]{20,}"
    r"|gsk_[0-9A-Za-z]{20,}"
    r"|sk-or-v1-[0-9A-Za-z\-]{20,}"
    r"|sk-[0-9A-Za-z]{32,})"
)


def redact(text: str) -> str:
    """Sensor nilai secret dari teks sebelum ditulis ke log."""
    if not text:
        return text
    out = text
    for secret in _SECRET_REGISTRY:
        if secret in out:
            out = out.replace(secret, "***REDACTED***")
    return _KEY_PATTERNS.sub("***REDACTED***", out)


def has_plaintext_fallback() -> bool:
    """True kalau platform ini tidak punya enkripsi native.

    First-run wizard memakai ini untuk jujur memberi tahu user.
    """
    return protection_kind() == "plaintext"


def describe_protection() -> str:
    """Kalimat siap tampil untuk UI."""
    if has_plaintext_fallback():
        return (
            f"{platform.system()} tidak punya enkripsi key bawaan Windows (DPAPI). "
            "Key disimpan di file lokal dengan permission khusus. Jangan dipakai "
            "untuk key yang tidak boleh hilang."
        )
    return "API key dienkripsi dengan DPAPI Windows dan hanya bisa dibaca oleh akun Windows ini."
