"""
clipper_version.py — Satu sumber kebenaran untuk versi runtime.

Kenapa modul ini perlu
----------------------
Nomor versi Python minimum pernah ditulis di README, badge, build_exe.py, dan
setup_pc_baru.bat. Kalau salah satu berbeda, user punya cara install yang
tidak jalan, dan tidak ada yang tahu pasti mana yang salah.

Semua angka versi sekarang hidup di sini. README dan script build membacanya.

Berapa minimum Python yang benar
--------------------------------
Bukan 3.9. google-genai memang butuh >= 3.9, tapi itu bukan pembatas kita.

Pembatas sebenarnya ada di kode kita sendiri: `clipper_core.py` memakai
annotatedPEP 604 (`dict | None`) TANPA `from __future__ import annotations`,
karena file itu sudah 2000 baris dan menambahkannya di tengah refactor berisiko
mengubah perilaku. PEP 604 butuh Python 3.10.

Mediapipe 0.10.x mengizinkan 3.9 (sudah diverifikasi: wheel py3 tersedia untuk
3.9), jadi Mediapipe bukan pembatas.

Dipilih: **Python 3.10**.

Alternatif yang lebih bersih: tambah `from __future__ import annotations` ke
clipper_core.py agar floor bisa turun ke 3.9. Tidak dilakukan di fase 4 karena
menyentuh seluruh file 2000+ baris — TODO(owner) kalau dukungan 3.9 masih diperlukan.

Kenapa bukan 3.13+: Python 3.13 masih relatif baru dan beberapa wheel yang kita
pakai belum menyediakannya. 3.10-3.12 range yang aman dan sudah diuji di build
lokal (3.12.3).
"""
from __future__ import annotations

import sys

# Versi aplikasi
APP_VERSION = "2.0.0"

# Rentang Python yang didukung
MIN_PYTHON = (3, 10)
MAX_TESTED_PYTHON = (3, 12)
RECOMMENDED_PYTHON = (3, 12)

# Python yang sudah EOL dan TIDAK didukung, supaya pesan errornya jelas.
EOL_PYTHON = ((3, 8), (3, 9))


def min_python_str() -> str:
    return f"{MIN_PYTHON[0]}.{MIN_PYTHON[1]}"


def max_tested_str() -> str:
    return f"{MAX_TESTED_PYTHON[0]}.{MAX_TESTED_PYTHON[1]}"


def python_requirement_str() -> str:
    """String untuk README dan pesan error."""
    return f"Python {min_python_str()}+ (diuji sampai {max_tested_str()})"


def current_python_str() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}"


def check_python() -> str:
    """Kembalikan pesan error kalau Python sekarang tidak cocok. Kosong = OK.

    Dipanggil check_dependencies() dan first-run wizard, jadi user dapat
    penjelasan langsung, bukan `SyntaxError` dari file yang gagal di-import.
    """
    v = (sys.version_info.major, sys.version_info.minor)
    if v < MIN_PYTHON:
        return (
            f"Python {current_python_str()} terlalu lama. Butuh minimal "
            f"{min_python_str()}. Pakai Python {RECOMMENDED_PYTHON[0]}."
            f"{RECOMMENDED_PYTHON[1]} dari python.org."
        )
    if v in EOL_PYTHON:
        return (
            f"Python {current_python_str()} sudah habis masa dukungannya "
            f"(EOL) dan tidak aman dipakai untuk produk berbayar."
        )
    if v > MAX_TESTED_PYTHON:
        return (
            f"Python {current_python_str()} lebih baru dari yang sudah diuji "
            f"({max_tested_str()}). Kemungkinan besar jalan, tapi belum diuji."
        )
    return ""


def python_supported() -> bool:
    return check_python() == ""
