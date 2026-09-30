"""
clipper_firstrun.py — Deteksi kesiapan untuk PC yang baru.

Installer menyiapkan dependensi, tapi ada hal yang tidak bisa disiapkan
otomatis: apakah ffmpeg benar-benar ada, apakah API key sudah diisi, apakah
font subtitle ikut bundle, apakah folder output bisa ditulis. Untuk user yang
baru installing, kegagalan paling mahal itu yang muncul 10 menit kemudian di
tengah render — setelah menunggu unduhan model dan analisis berjalan.

Modul ini mengembalikan DAFTAR MASALAH, bukan menjalankan perbaikan. Yang
memutuskan harus tetap oleh user: installer yang diam-diam mengubah ACL atau
membuka dialog keamanan akan terlihat seperti malware, dan sekali user
meragukan installer, mereka tidak akan menyerahkan data-nya.

Fase 5: belum ada dialog wizard. Yang ini baru modul + test, dipakai
`check_dependencies()` dan akan dipakai dialog Settings di fase berikutnya.
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from clipper_legal import SUBTITLE_FONT_DEFAULT
from clipper_paths import RESOURCE_DIR, output_dir_from_config
from clipper_version import (
    APP_VERSION, MAX_TESTED_PYTHON, MIN_PYTHON, check_python, min_python_str,
)


class Severity(Enum):
    """Seberapa parah masalah ini bagi user."""

    BLOCKER = "blocker"   # aplikasi tidak bisa dipakai sama sekali
    WARNING = "warning"   # bisa jalan, tapi ada yang tidak beres
    INFO = "info"         # informasi, tidak perlu tindakan


@dataclass
class Issue:
    """Satu masalah, dalam bahasa yang bisa ditampilkan ke user."""

    code: str
    title: str
    detail: str
    severity: Severity = Severity.WARNING
    fix_hint: str = ""
    # Kalau True, dialog boleh menawarkan tombol perbaikan otomatis.
    auto_fixable: bool = False

    def user_text(self) -> str:
        """Teks siap tampil, tanpa jargon internal."""
        lines = [self.title, self.detail]
        if self.fix_hint:
            lines.append(f"  -> {self.fix_hint}")
        return "\n".join(lines)


# --------------------------------------------------------------------------
# Pengecekan individual
# --------------------------------------------------------------------------
def check_python_runtime() -> list:
    """Versi Python harus >= minimum. Di luar app, ini hanya informatif."""
    problem = check_python()
    if not problem:
        return []
    return [
        Issue(
            code="python_version",
            title="Python terlalu lama",
            detail=problem,
            severity=Severity.BLOCKER,
            fix_hint=f"Pasang Python {min_python_str()} atau lebih baru",
        )
    ]


def check_ffmpeg() -> list:
    """ffmpeg wajib ada. Tidak ada = tidak bisa render sama sekali."""
    bundled = RESOURCE_DIR / "bin" / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    if bundled.exists():
        return []   # ikut bundle, tidak perlu apa-apa
    if shutil.which("ffmpeg"):
        return []
    return [
        Issue(
            code="ffmpeg_missing",
            title="ffmpeg tidak ditemukan",
            detail="Aplikasi butuh ffmpeg untuk memotong dan render video.",
            severity=Severity.BLOCKER,
            fix_hint="winget install Gyan.FFmpeg, lalu restart aplikasi",
        )
    ]


def check_ffprobe() -> list:
    """ffprobe dipakai untuk ambil durasi audio (lihat AUDIT.md G7)."""
    if shutil.which("ffprobe"):
        return []
    if shutil.which("ffmpeg"):
        # ffprobe biasanya datang bersama ffmpeg; ini paket yang tidak lengkap.
        return [
            Issue(
                code="ffprobe_missing",
                title="ffprobe tidak ditemukan",
                detail="ffmpeg ada tapi ffprobe tidak, jadi durasi audio tidak terbaca.",
                severity=Severity.WARNING,
                fix_hint="Pasang ulang paket ffmpeg yang lengkap",
            )
        ]
    return []   # sudah dilaporkan sebagai ffmpeg_missing


def check_ai_provider_sdk() -> list:
    """Gemini SDK tidak ada = tombol Analisis diam-diam tidak working."""
    try:
        from google import genai  # noqa: F401
    except ImportError:
        return [
            Issue(
                code="genai_missing",
                title="SDK Gemini tidak terinstall",
                detail="Analisis AI tidak akan bisa jalan sama sekali.",
                severity=Severity.WARNING,
                fix_hint="Jalankan: pip install -r requirements.txt",
            )
        ]
    return []


def check_api_key(config: dict) -> list:
    """Tanpa API key, analisis AI tidak jalan. Tidak fatal — transkripsi masih jalan."""
    provider = config.get("ai_provider", "Gemini (Native)")
    field_name = {
        "gemini": "gemini_api_key",
        "openrouter": "openrouter_api_key",
        "groq": "groq_api_key",
    }.get(provider.split(" ")[0].lower())
    if field_name is None or config.get(field_name):
        return []
    return [
        Issue(
            code="api_key_missing",
            title="API key belum diisi",
            detail=(
                f"Provider {provider} dipilih tapi API key-nya kosong. "
                "Analisis AI tidak bisa jalan; transkripsi tetap bisa."
            ),
            severity=Severity.WARNING,
            fix_hint="Buka Settings dan isi API key",
        )
    ]


def check_subtitle_font(config: dict) -> list:
    """Font default harus ada di bundle. Hilang = subtitle tidak muncul."""
    selected = config.get("subtitle_font") or SUBTITLE_FONT_DEFAULT
    if (RESOURCE_DIR / "fonts" / selected).exists():
        return []
    return [
        Issue(
            code="subtitle_font_missing",
            title="Font subtitle tidak ditemukan",
            detail=f"File '{selected}' tidak ada di folder aplikasi.",
            severity=Severity.BLOCKER,
            fix_hint=f"Ganti font di Settings ke {SUBTITLE_FONT_DEFAULT}",
        )
    ]


def _is_windows_library_folder(path: Path) -> bool:
    """Apakah ini salah satu folder library Windows yang Known Folder.

    Videos, Documents, Music, Pictures, dan Desktop bukan folder biasa di
    Windows 10/11 — semuanya adalah "Known Folder" yang dikelola shell, dan
    user bisa memindahkannya ke lokasi lain (OneDrive, drive eksternal) lewat
    registry. Ketika lokasi itu tidak bisa dijangkau, `Path.mkdir()` gagal
    dengan errno 2 "The system cannot find the file specified" — pesan yang
    sama persis dengan folder yang benar-benar hilang, padahal orangnya ada
    dan user punya Full Control (ACL-nya `(OI)(CI)(F)`).

    Ditemukan di PC develop sendiri, jadi ini bukan kasus langka:

        C:\\Users\\SOPIAN\\Videos    -> mkdir gagal (errno 2)
        C:\\Users\\SOPIAN\\Downloads -> mkdir OK

    Gejalanya sangat menyesatkan karena tidak ada yang salah secara permission,
    dan `icacls` menunjukkan user punya Full Control. Yang perlu diperiksa
    justru apakah folder itu Known Folder yang sudah dipindahkan.
    """
    if os.name != "nt":
        return False
    try:
        home = Path(os.path.expanduser("~"))
    except (OSError, RuntimeError):
        return False
    library = {"videos", "documents", "music", "pictures", "desktop"}
    return path.name.lower() in library and path.parent == home


def check_output_dir(config: dict) -> list:
    """Folder output harus benar-benar bisa ditulis.

    Kegagalan yang paling sering untuk user baru adalah output default
    (`~/Videos`) menabrak Known Folder Windows yang tidak bisa dijangkau.
    Yang penting: pesan errornya jujur. "Folder output tidak bisa ditulis"
    jauh lebih berguna daripada "The system cannot find the file specified",
    yang membuat usermengira foldernya hilang padahal ada di depan matanya.
    """
    out = output_dir_from_config(config)
    try:
        out.mkdir(parents=True, exist_ok=True)
        probe = out / ".write_test"
        probe.write_text("x", encoding="utf-8")
        probe.unlink()
        return []
    except OSError as exc:
        is_library = _is_windows_library_folder(out.parent)
        if is_library:
            return [
                Issue(
                    code="output_dir_known_folder",
                    title="Folder output berada di folder sistem Windows",
                    detail=(
                        f"{out.parent} adalah Known Folder Windows (Videos / "
                        "Documents / Desktop). Folder ini kadang tidak bisa "
                        "ditulis, dan errornya menyesatkan."
                    ),
                    severity=Severity.BLOCKER,
                    fix_hint="Ganti folder output di Settings ke folder biasa, "
                             "misalnya folder Downloads",
                )
            ]
        return [
            Issue(
                code="output_dir_not_writable",
                title="Folder output tidak bisa ditulis",
                detail=f"{out} - {exc.strerror or exc}",
                severity=Severity.WARNING,
                fix_hint="Ganti folder output di Settings, atau buat foldernya manual",
            )
        ]


def check_whisper_model_cache() -> list:
    """Model whisper diunduh saat runtime. Kalau belum ada, render pertama lambat.

    INFO, bukan WARNING: aplikasi tetap jalan, hanya perlu mengunduh sekali.
    """
    cache_root = Path(
        os.environ.get("LOCALAPPDATA", str(Path.home()))
    ) / "huggingface" / "hub"
    if cache_root.exists() and any(
        cache_root.glob("models--Systran--faster-whisper-*")
    ):
        return []
    return [
        Issue(
            code="whisper_model_not_cached",
            title="Model transkripsi belum diunduh",
            detail=(
                "Download pertama perlu sekitar 1.5 GB dan beberapa menit. "
                "Setelah itu dipakai offline."
            ),
            severity=Severity.INFO,
            fix_hint="Render pertama akan mengunduh sendiri",
        )
    ]


# --------------------------------------------------------------------------
# Pemeriksaan gabungan
# --------------------------------------------------------------------------
def run_all_checks(config: dict | None = None) -> list:
    """Semua pemeriksaan, urut dari paling parah.

    config=None berarti "cek yang tidak butuh data user" — dipakai sebelum
    Settings pernah dibuka, sehingga pemeriksaan API key dilewati.
    """
    cfg = config if config is not None else {}
    issues = []
    issues += check_python_runtime()
    issues += check_ffmpeg()
    issues += check_ffprobe()
    issues += check_ai_provider_sdk()
    issues += check_subtitle_font(cfg)
    issues += check_output_dir(cfg)
    if config is not None:
        issues += check_api_key(config)
    issues += check_whisper_model_cache()
    issues.sort(key=lambda i: list(Severity).index(i.severity))
    return issues


def has_blockers(issues: list) -> bool:
    return any(i.severity == Severity.BLOCKER for i in issues)


def summary_for_startup(issues: list) -> str:
    """Satu blok teks untuk log atau dialog saat start.

    User baru tidak butuh daftar sembilan item saat membuka aplikasi. Yang
    mereka butuh: bisa dipakai atau tidak, dan kalau tidak, satu langkah
    berikutnya.
    """
    if not issues:
        return f"YT Short Clipper Pro v{APP_VERSION} - siap dipakai."

    blockers = [i for i in issues if i.severity == Severity.BLOCKER]
    warnings = [i for i in issues if i.severity == Severity.WARNING]
    infos = [i for i in issues if i.severity == Severity.INFO]

    parts = [f"YT Short Clipper Pro v{APP_VERSION}"]
    if blockers:
        parts.append(f"{len(blockers)} masalah yang harus dibereskan dulu:")
        parts += [f"  - {i.title}: {i.fix_hint}" for i in blockers]
    if warnings:
        parts.append(f"{len(warnings)} peringatan:")
        parts += [f"  - {i.title}" for i in warnings]
    if infos:
        parts.append(f"{len(infos)} catatan:")
        parts += [f"  - {i.title}" for i in infos]
    return "\n".join(parts)


def python_support_text() -> str:
    """Satu kalimat untuk UI tentang versi Python yang didukung."""
    major, minor = MIN_PYTHON
    return f"Python {major}.{minor}+ (teruji sampai {MAX_TESTED_PYTHON})"
