"""
build_exe.py — Build distribusi Windows untuk YT Short Clipper Pro.

Bukan sekadar pembungkus PyInstaller: ini satu-satunya tempat yang tahu apa
yang BOLEH ikut installer. Kalau aset berlisensi komersial masuk ke sini tanpa
disengaja, tidak ada yang menahan — makanya `--exclude-module` dan daftar aset
dipakai clipper_legal.py, dan `verify_build()` dipakai test.

Kenapa onedir, bukan onefile
---------------------------
Onefile ekstrak ke %TEMP% setiap kali dijalankan, lalu menghapusnya saat
keluar. Dengan model whisper berukuran ratusan MB, itu berarti dua kali baca
disk besar setiap launch, dan `sys._MEIPASS` pindah tiap proses — persis
kelas bug yang clipper_paths.py dibangun untuk menutup. Onedir juga lebih cepat
dan lebih mudah di-debug, dan zip-nya tetap satu file saat dikirim.

Pilihan lain yang disengaja:
  - TIDAK ada ffmpeg.exe/yt-dlp.exe yang dibundel -> lihat clipper_legal.py
  - faster_whisper: model di-download saat runtime ke cache user, jadi tidak
    bisa di-bundle di build ini (lihat DECISIONS.md [D015])
  - mediapipe: protobuf + TFLite dinamis, bundling rapuh; dipakai lewat
    import langsung dan sudah ada di requirements.txt
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from clipper_legal import (  # noqa: E402
    BUNDLED_ASSETS, BLOCKED_ASSETS, EXTERNAL_ASSETS,
)
from clipper_version import APP_VERSION  # noqa: E402

ROOT = Path(__file__).resolve().parent
EXE_NAME = "YTShortClipper"
ENTRY_POINT = "clipper_gui_modern.py"

# Direktori resource yang HARUS ikut. Tidak ikut = crash saat frozen, karena
# RESOURCE_DIR menunjuk ke folder tersebut.
REQUIRED_DATA_DIRS = ("fonts", "bin", "vendor", "backsound")

# Direktori yang tidak boleh ikut Ukuran besar, dan tidak dipakai runtime.
SKIP_DATA_DIRS = ("notebooks", "tests", "dist", "build", "__pycache__", ".git")


def _pyi_arg(flag: str, source, *dest_parts: str) -> str:
    """Bentuk argumen --add-data. Separator PATH dipisah titik koma, bukan titik.

    Ini yang membuat build lama rusak diam-diam: separator Windows harus ';',
    dan kalau salah jadi ';' yang ditulis ulang jadi separator lain, PyInstaller
    tidak protes, hanya menghasilkan folder yang tidak pernah dibaca.
    """
    sep = ";" if os.name == "nt" else ":"
    return f"--add-data={source}{sep}{'/'.join(dest_parts)}"


def collect_data_args() -> list:
    """Argumen --add-data untuk semua resource yang dibaca runtime."""
    args = []
    for name in REQUIRED_DATA_DIRS:
        src = ROOT / name
        if not src.exists():
            print(f"  [LEWATI] {name}/ tidak ada — periksa packaging")
            continue
        args.append(_pyi_arg("--add-data", str(src), name))
    # Lisensi harus ikut: obligations redistribusi hanya berlaku kalau teksnya
    # ikut installer (OFL 1.1 dan Apache 2.0 sama-sama mewajibkannya).
    licenses = ROOT / "licenses"
    if licenses.exists():
        args.append(_pyi_arg("--add-data", str(licenses), "licenses"))
    for doc in ("THIRD_PARTY_NOTICES.md", "LICENSE", "README.md"):
        if (ROOT / doc).exists():
            args.append(_pyi_arg("--add-data", str(ROOT / doc), doc))
    return args


def collect_hidden_imports() -> list:
    """Import yang tidak terdeteksi PyInstaller karena dipanggil lewat string."""
    args = [
        "--hidden-import=clipper_tts",
        "--hidden-import=clipper_legal",
        "--hidden-import=clipper_version",
        "--hidden-import=clipper_secrets",
    ]
    # pykakasi (romaji -> kanji) opsional; dipakai lewat import lokal, dan
    # environment build belum tentu punya.
    import importlib.util

    try:
        importlib.util.find_spec("pykakasi")
    except (ImportError, ValueError):
        args.append("--exclude-module=pykakasi")
    else:
        args.append("--collect-all=pykakasi")
    return args


def collect_excludes() -> list:
    """Paket besar yang tidak dipakai jalur GUI dan tidak perlu ikut.

    Kenapa dikecualikan: gradio + streamlit + tensorflow pull ratusan MB, dan
    keduanya hanya untuk web/Colab. Installer desktop tidak butuh keduanya.
    """
    return [
        "--exclude-module=gradio",
        "--exclude-module=streamlit",
        "--exclude-module=matplotlib",
        "--exclude-module=notebook",
        "--exclude-module=IPython",
        "--exclude-module=pykakasi",
        "--exclude-module=pytest",
    ]


def build_command() -> list:
    """Argumen PyInstaller lengkap. Terpisah agar bisa diuji tanpa build."""
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed",
        f"--name={EXE_NAME}",
        f"--distpath={ROOT / 'dist'}",
        f"--workpath={ROOT / 'build'}",
        f"--specpath={ROOT / 'build'}",
    ]
    args += collect_data_args()
    args += collect_hidden_imports()
    args += collect_excludes()

    for lib in ("customtkinter", "faster_whisper", "PIL", "google.genai"):
        args.append(f"--collect-all={lib}")

    args.append(str(ROOT / ENTRY_POINT))
    return args


def expected_artifact(relpath: str) -> Path:
    return ROOT / "dist" / EXE_NAME / relpath


def bundle_data_root() -> Path:
    """Folder tempat PyInstaller 6.x menaruh data (bukan binary) dari --add-data.

    PENTING: sejak PyInstaller 6, layout onedir berubah. Semua data dan binary
    went ke dalam `_internal/`, dan hanya bootloader EXE + folder `_internal`
    yang ada di root. Versi pertama dari fungsi ini mencari di root dan melaporkan
    5 resource "hilang" padahal semuanya ada di `_internal/`.

    Caraceo mendeteksinya, bukan Konstantin: beberapa build (mis. dengan
    `--contents-directory=''`) menaruh data di root. Jadi dicek dua-duanya dan
    dipakai yang benar-benar berisi data kita.
    """
    base = ROOT / "dist" / EXE_NAME
    internal = base / "_internal"
    marker = internal / "fonts" / "Montserrat-Bold.ttf"
    if marker.exists():
        return internal
    root_marker = base / "fonts" / "Montserrat-Bold.ttf"
    if root_marker.exists():
        return base
    return internal   # default: hopes for the best, reported as missing


def verify_build() -> list:
    """Cek hasil build. Kembalikan list pesan; kosong = semua beres.

    Resource yang hilang tidak selalu berarti build gagal — tapi efeknya
    sama saja bagi user: subtitle diam-diam tidak muncul, atau aplikasi tidak
    bisa dibuka karena satu file kurang. Karena itu yang dicek adalah isi bundle,
    bukan exit code PyInstaller.
    """
    problems = []
    base = ROOT / "dist" / EXE_NAME
    if not base.exists():
        return [f"dist/{EXE_NAME} tidak ada - build gagal atau belum dijalankan"]

    exe = base / f"{EXE_NAME}.exe"
    if not exe.exists():
        problems.append(f"{exe.name} tidak ada")

    data_root = bundle_data_root()

    # Resource yang dibaca runtime harus ada di dalam bundle. Tidak adanya
    # font di sini = subtitle diam-diam hilang di build user.
    for rel in ("fonts/Montserrat-Bold.ttf", "bin/detector.tflite"):
        if not (data_root / rel).exists():
            problems.append(f"resource hilang di bundle: {rel}")

    # Dokumen legal wajib ikut installer.
    for rel in ("LICENSE", "THIRD_PARTY_NOTICES.md", "licenses/OFL.txt"):
        if not (data_root / rel).exists():
            problems.append(f"dokumen legal hilang di bundle: {rel}")

    # Aset berlisensi komersial tidak boleh ikut.
    for asset in BLOCKED_ASSETS:
        for candidate in (data_root / asset.name, data_root / "fonts" / asset.name):
            if candidate.exists():
                problems.append(f"aset terlarang ikut bundle: {candidate.name}")
    return problems


def print_bundled_assets() -> None:
    print("\nAset yang ikut installer:")
    for asset in BUNDLED_ASSETS:
        print(f"  + {asset.name}  [{asset.license_id}]")
    for asset in EXTERNAL_ASSETS:
        print(f"  o {asset.name}  [{asset.license_id}]  -> {asset.notes[:60]}")
    blocked_now = [a for a in BLOCKED_ASSETS if a.bundled]
    if blocked_now:
        print(f"\n  ! MASALAH: {len(blocked_now)} aset terlarang ter-kemas")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build EXE Windows")
    parser.add_argument("--verify-only", action="store_true",
                        help="hanya cek hasil build yang ada")
    args = parser.parse_args(argv)

    if args.verify_only:
        problems = verify_build()
        if problems:
            print("BUILD TIDAK LENGKAP:")
            for p in problems:
                print(f"  - {p}")
            return 1
        print("Build lengkap: EXE + resource + dokumen legal semua ada.")
        return 0

    print_bundled_assets()
    print(f"\n[1/3] Menyiapkan environment build (v{APP_VERSION})")
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "PyInstaller>=6.0,<7.0"]
        )

    print("[2/3] Menjalankan PyInstaller (butuh beberapa menit)...")
    cmd = build_command()
    try:
        subprocess.check_call(cmd)
    except subprocess.CalledProcessError as exc:
        print(f"\n[FAIL] PyInstaller gagal: {exc}")
        return 1

    print("[3/3] Memverifikasi hasil build")
    problems = verify_build()
    if problems:
        print("Build selesai tapi TIDAK lengkap:")
        for p in problems:
            print(f"  - {p}")
        return 1

    print(f"\n[OK] dist/{EXE_NAME}/ siap. Zip dan kirim.")
    print(f"     legal: {len(BUNDLED_ASSETS)} aset ter-bundle, "
          f"{len(EXTERNAL_ASSETS)} eksternal, "
          f"{len([a for a in BLOCKED_ASSETS if a.bundled])} terlarang")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
