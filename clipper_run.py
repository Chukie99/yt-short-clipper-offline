"""
clipper_run.py — Satu-satunya jalan untuk menjalankan proses eksternal.

Kenapa modul ini ada
--------------------
v1.2.0 punya `run_cmd()` di clipper_core yang menerima `str` maupun `list`:

    if isinstance(cmd, (list, tuple)):
        Popen(list(cmd), ...)          # aman
    else:
        Popen(cmd, shell=True, ...)    # RENTAN

Artinya caller mana pun yang mengirim string membuat seluruh aplikasi rentan command
injection. Dan memang ada caller begitu — `ensure_bgm()` mengirim f-string berisi
path, sementara app.py / clipper_web.py mengirim link dari user langsung ke shell.
`_valid_youtube_url()` menyaring beberapa metachar, tapi itu defense di lapisan yang
salah: filter input berubah-ubah, dan yang aman secara struktural adalah tidak
pernah mengexecute string.

Aturan di modul ini
-------------------
1. `run_command()` hanya menerima `list[str]`. String ditolak keras (TypeError),
   bukan diam-diam di-`shell=True`.
2. Tidak ada escaping yang perlu dipikirkan pemanggil. Path dengan spasi,
   teks dengan tanda kutip, karakter `&` — semuanya aman karena tidak pernah
   melewati parser shell.
3. Timeout wajib untuk proses yang mungkin menggantung (network call yt-dlp).
4. Error yang dilempar selalu menyebut executable, argumen (dipotong), dan exit code
   supaya bisa dilaporkan user tanpa perlu membuka log.

Yang TIDAK ada di sini: escaping untuk shell. Kalau suatu hari butuh pipeline shell,
tulis sebagai `-filter_complex` ffmpeg (sudah dipakai di clipper_core) — bukan
`cmd1 && cmd2`.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading

from pathlib import Path
from typing import Callable, Iterable, Sequence

# Pola yang di-strip sebelum ditulis ke ffmpeg filtergraph. Berpikir defensif:
# - `;` dan `,` adalah separator di dalam filtergraph ffmpeg, jadi nilai yang tidak
#   dikontrol (judul dari AI, keyword) tidak boleh bisa menyuntik filter baru.
# - `\` dan `'` adalah escape character ffmpeg sendiri, dan `"` menutup operand
#   bertanda kutip — ketiganya harus hilang sebelum masuk ke filtergraph.
# - `\x00` membuat ffmpeg gagal parse dengan pesan yang tidak jelas.
_FFMPEG_UNSAFE = re.compile(r"""[;,\[\]\\'"`\x00]""")


def quote_for_filtergraph(value: str) -> str:
    """Bersihkan nilai destined for an ffmpeg filter option.

    Dipakai untuk `-filter_complex`, `-metadata`, dan `-vf` — tempat di mana nilai
    masuk ke bahasa internal ffmpeg, bukan ke argv. Menghapus lebih banyak karakter
    lebih aman daripada escaping sebagian: judul short tidak butuh koma atau kutip.
    """
    if value is None:
        return ""
    return _FFMPEG_UNSAFE.sub(" ", str(value)).strip()


def safe_filename(name: str, fallback: str = "output", max_len: int = 120) -> str:
    """Nama file aman untuk Windows: tanpa path, reserved name, atau karakter ilegal.

    Menyerap `safe_title` yang sebelumnya inline di process_single_video, tapi juga
    menyaring pemisah path (yang di sana belum ter-handle — judul berisi `..\\` akan
    menulis ke luar folder output).
    """
    cleaned = str(name or "").strip()
    cleaned = cleaned.replace("\x00", "")
    # Path separator diganti DULUAN, sebelum karakter ilegal lain. Kalau urutannya
    # dibalik, `../..` menjadi `.._..` yang masih mengandung `..`.
    cleaned = re.sub(r"[/\\]+", "_", cleaned)
    cleaned = re.sub(r"[<>\"|?*:]", "_", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    # Sisa `..` setelah path separator dinetralkan: buang agar tidak ada segment
    # traversal yang tersisa sama sekali.
    cleaned = cleaned.replace("..", "_")
    # Reserved device names on Windows (CON, PRN, AUX, NUL, COM1..9, LPT1..9)
    if not cleaned:
        return fallback
    stem = cleaned.split(".")[0].upper()
    if stem in {"CON", "PRN", "AUX", "NUL"} or re.fullmatch(r"(COM|LPT)[1-9]", stem):
        cleaned = f"_{cleaned}"
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip(" .")
    return cleaned or fallback


def run_command(
    args: Sequence[str],
    *,
    log_func: Callable[[str], None] | None = None,
    timeout: float | None = None,
    cwd: str | Path | None = None,
    input_bytes: bytes | None = None,
    check: bool = True,
    capture: bool = True,
    env: dict | None = None,
) -> subprocess.CompletedProcess:
    """Jalankan executable dengan list-args. Tidak pernah lewat shell.

    Args:
        args: argv lengkap, executable di index 0.WAJIB list/tuple.
        log_func: dipakai untuk streaming baris yang terlihat menarik (progress,
            error) — sama seperti perilaku run_cmd lama.
        timeout: detik. Lewati = proses boleh menggantung selamanya (hanya untuk
            proses yang memang berjalan sampai stdin ditutup, yaitu render ffmpeg).
        cwd: working directory.
        input_bytes: stdin binary (dipakai untuk probe kecil).
        check: True = lempar CommandError saat exit != 0.

    Returns:
        CompletedProcess dengan .stdout/.stderr sebagai str (bukan bytes).

    Raises:
        TypeError: kalau `args` bukan list/tuple. Ini gunanya: mencegah caller
            baru secara struktural menulis string di sini.
        CommandError: exit != 0 atau timeout. Pesannya self-contained.
    """
    if isinstance(args, (str, bytes)) or not isinstance(args, Iterable):
        raise TypeError(
            "run_command() hanya menerima list argumen, bukan string. "
            "String berarti command injection. Lihat clipper_run.py docstring."
        )
    argv = [str(a) for a in args]
    if not argv:
        raise ValueError("run_command(): argv kosong")

    exe = argv[0]
    # PATH-resolution check. Syaratnya `Path(exe).name == exe` (bukan contains),
    # supaya `bin/ffmpeg.exe` yang TIDAK ada ikut dicek dan pesan "tidak ditemukan"
    # muncul, bukan FileNotFoundError dari Popen.
    if not os.path.isabs(exe) and Path(exe).name == exe and shutil.which(exe) is None:
        raise CommandError(
            f"{exe} tidak ditemukan. Pasang lewat setup, atau taruh "
            f"ffmpeg/yt-dlp di folder 'bin' aplikasi."
        )

    full_env = {**os.environ, **(env or {})}
    started = f"{argv[0]}"

    try:
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
            stderr=subprocess.STDOUT if capture else subprocess.DEVNULL,
            cwd=str(cwd) if cwd else None,
            env=full_env,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            shell=False,  # eksplisit: tidak pernah berubah
        )
    except (OSError, ValueError) as e:
        raise CommandError(f"Gagal menjalankan {started}: {e}") from e

    collected: list[str] = []
    timed_out = False

    # Timeout dijaga oleh watchdog, bukan oleh wait(timeout=).
    #
    # Alasannya: loop baca stdout di bawah memblokir sampai EOF. Kalau proses
    # menggantung sambil menulis output, loop itu tidak pernah selesai, jadi
    # wait(timeout=) tidak pernah tereksekusi dan timeout jadi tidak berguna.
    # Watchdog mematikan proses dari luar, sehingga loop baca ikut berakhir.
    watchdog = None
    if timeout is not None:
        def _on_timeout():
            nonlocal timed_out
            timed_out = True
            try:
                proc.kill()
            except OSError:
                pass

        watchdog = threading.Timer(timeout, _on_timeout)
        watchdog.daemon = True
        watchdog.start()

    try:
        if input_bytes is not None:
            # Kirim stdin lalu TUTUP. Kalau tidak ditutup, anak proses menunggu
            # EOF selamanya dan hang (bug yang ketahuan oleh test).
            try:
                # Popen opened in text mode, so stdin wants str, not bytes.
                payload = input_bytes if isinstance(input_bytes, str) else bytes(input_bytes).decode("utf-8", errors="replace")
                proc.stdin.write(payload)
                proc.stdin.flush()
                proc.stdin.close()
            except (OSError, ValueError) as e:
                proc.kill()
                raise CommandError(f"Gagal menulis input ke {started}: {e}") from e

        if capture and proc.stdout is not None:
            for line in proc.stdout:
                line = line.rstrip()
                if not line:
                    continue
                collected.append(line)
                if log_func and _is_interesting(line):
                    log_func(f"   > {line}")
            proc.stdout.close()

        proc.wait(timeout=(None if timeout is None else timeout + 15))
    finally:
        if watchdog is not None:
            watchdog.cancel()

    if timed_out:
        raise CommandError(
            f"{Path(exe).name} melebihi batas waktu {timeout:.0f}s dan dihentikan. "
            f"Detail: {' | '.join(collected[-5:]) if collected else '(tidak ada output)'}"
        )

    result = subprocess.CompletedProcess(
        argv, proc.returncode, "\n".join(collected), None
    )
    if check and proc.returncode != 0:
        raise CommandError(_friendly_error(Path(exe).name, proc.returncode, collected, argv))
    return result


def run_streaming(
    args: Sequence[str],
    *,
    log_func: Callable[[str], None] | None = None,
    cwd: str | Path | None = None,
) -> subprocess.Popen:
    """Jalankan proses yang menulis frame ke stdin dan selesai saat stdin ditutup.

    Dipakai oleh loop render ffmpeg: kita butuh handle Popen, bukan CompletedProcess.
    Tetap tanpa shell. Timeout TIDAK dipakai di sini — proses memang hidup selama
    frame dikirim; pemanggil yang memutuskan kapan menyerah.
    """
    if isinstance(args, (str, bytes)) or not isinstance(args, Iterable):
        raise TypeError("run_streaming() hanya menerima list argumen.")
    argv = [str(a) for a in args]
    try:
        return subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            cwd=str(cwd) if cwd else None,
            shell=False,
        )
    except (OSError, ValueError) as e:
        raise CommandError(f"Gagal menjalankan {argv[0]}: {e}") from e


def _is_interesting(line: str) -> bool:
    """Filter baris log — sama seperti run_cmd lama, tidak berubah perilakunya."""
    low = line.lower()
    return any(
        token in low
        for token in ["%", "fps", "speed", "time=", "download", "error", "failed"]
    )


def _friendly_error(name: str, code: int | None, lines: list[str], argv: list[str]) -> str:
    """Bangun pesan error yang bisa dibaca user, bukan dump 15 baris ffmpeg."""
    tail = "\n".join(lines[-15:])
    low = tail.lower()
    if "sign in to confirm" in low or "cookies" in low:
        return (
            "YouTube menolak akses (cookies kedaluwarsa atau belum diisi).\n"
            "Cara perbaikannya:\n"
            "  1. Buka YouTube.com di browser dan login\n"
            "  2. Pasang extension 'Get cookies.txt locally'\n"
            "  3. Klik extension -> Export, simpan sebagai cookies.txt\n"
            "  4. Settings -> Cookies -> pilih file itu"
        )
    if "no space left" in low or "disk" in low:
        return f"Tidak ada ruang disk cukup untuk menyelesaikan proses.\nDetail: {tail}"
    if name.lower().startswith("yt-dlp"):
        return (
            f"yt-dlp gagal (kode {code}).\n"
            "Coba: (a) perbarui yt-dlp, (b) isi cookies.txt di Settings, "
            "(c) ganti video dengan yang publik.\n"
            f"Detail:\n{tail}"
        )
    shown = " ".join(argv[:4])
    return f"{name} gagal (kode {code}).\nPerintah: {shown} ...\nDetail:\n{tail}"


class CommandError(Exception):
    """Gagal menjalankan proses eksternal. Pesannya sudah siap ditampilkan."""
