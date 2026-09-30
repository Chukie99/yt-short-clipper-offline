"""
clipper_guard.py — Gerbang sebelum kerja mahal dimulai.

Konteks
-------
Aplikasi punya banyak pemeriksaan kesiapan (clipper_firstrun, check_dependencies).
Semua itu sia-sia kalau tidak ada yang memanggilnya sebelum user menekan tombol
yang mahal. Gejalanya di dunia nyata: user baru menekan "Proses Terpilih",
menunggu model whisper terunduh, lalu baru melihat error yang sebenarnya sudah
teretahui sejak aplikasi dibuka.

Yang dik modul ini
-------------------------
Satu fungsi: `gate_before_work()` yang mengembalikan MASALAH atau bukan. Ini
bukan lapisan peringatan — kalau ada blocker, pemanggil harus berhenti.

Kenapa jadi modul terpisah, bukan method di GUI
-----------------------------------------------
Karena aturannya berlaku di lebih dari satu tempat (GUI, Streamlit, Gradio),
dan aturan yang hanya ada di UI bisa dilewati diam-diam oleh jalur lain. Test
juga bisa memanggilnya tanpa menjalankan Tkinter.

Yang SENGAJA tidak dilakukan di sini: memperbaiki apa pun. Installer atau setting
yang mengubah ACL atau mengunduh executable tanpa izin user terlihat seperti
malware, dan sekali user meragukan aplikasi, mereka tidak akan menyerahkan
data-nya. Modul ini melaporkan; user atau Settings yang memutuskan.
"""
from __future__ import annotations

from dataclasses import dataclass

import clipper_firstrun as fr
from clipper_firstrun import Severity, run_all_checks


@dataclass
class GateResult:
    """Hasil gerbang. `can_proceed` adalah satu-satunya yang perlu dibaca."""

    can_proceed: bool
    issues: list
    # Pesan siap tampil untuk log/dialog.
    message: str = ""

    @property
    def blockers(self) -> list:
        return [i for i in self.issues if i.severity == Severity.BLOCKER]

    @property
    def warnings(self) -> list:
        return [i for i in self.issues if i.severity == Severity.WARNING]

    def should_warn_only(self) -> bool:
        """True kalau jalan boleh, tapi ada yang sebaiknya dibereskan."""
        return self.can_proceed and bool(self.warnings)


def gate_before_work(
    config: dict | None = None,
    need_ai: bool = True,
    need_render: bool = True,
) -> GateResult:
    """Periksa kesiapan sebelum Analysis atau Render.

    Parameter
    ---------
    config
        Config hasil load_config(). Kalau None, cek yang tidak butuh data user.
    need_ai
        True untuk "Ambil & Analisis" — butuh API key + SDK.
    need_render
        True untuk "Proses Terpilih" — butuh ffmpeg, font, output folder.

    Kenapa dipisah:_analysis tanpa API key masih berguna (bisa lihat transkrip),
    tapi render tanpa ffmpeg tidak akan pernah jalan. Menolak analisis karena
    ffmpeg hilang akan membuat user bingung — masalahnya tidak terkait.
    """
    issues = run_all_checks(config)

    if not need_ai:
        # Analisis butuh API key, tapi tidak butuh ffmpeg/font/output.
        issues = [i for i in issues if i.code not in _RENDER_ONLY]

    if not need_render:
        issues = [i for i in issues if i.code not in _RENDER_ONLY]

    blockers = [i for i in issues if i.severity == Severity.BLOCKER]
    can_proceed = not blockers

    if can_proceed:
        message = ""
    else:
        message = "\n".join(i.user_text() for i in blockers)

    return GateResult(can_proceed=can_proceed, issues=issues, message=message)


# Kode masalah yang hanya relevan untuk render. Gemini SDK/API key juga
# sebenarnya hanya untuk analisis, tapi dipisah di sini supaya niatnya jelas.
_RENDER_ONLY = {
    "ffmpeg_missing",
    "ffprobe_missing",
    "subtitle_font_missing",
    "output_dir_not_writable",
    "output_dir_known_folder",
}


def format_gate_dialog(result: GateResult) -> str:
    """Teks untuk dialog: masalah yang memblokir + peringatan di bawahnya.

    Dialog harus bisa dibaca orang non-teknis dalam 5 detik. Kalau daftar
    memuat 9 item, user akan menutupnya dan menekan tombol yang salah.
    """
    if result.can_proceed:
        if not result.warnings:
            return "Siap."
        lines = ["Bisa lanjut, tapi ada yang sebaiknya dibereskan:"]
        lines += [f"- {i.title}" for i in result.warnings]
        return "\n".join(lines)

    lines = ["Aplikasi belum bisa dipakai. Perbaiki dulu:"]
    lines += [f"\n{i.title}\n  {i.detail}\n  -> {i.fix_hint}" for i in result.blockers]
    if result.warnings:
        lines.append(f"\nSelain itu, {len(result.warnings)} peringatan lain ada di log.")
    return "\n".join(lines)


def missing_ai_capability(config: dict | None) -> str:
    """Pesan singkat kalau AI tidak bisa dipakai, atau string kosong.

    Dipakai Analytics untuk menentukan apakah tombol harus menolly warning
    atau diam saja — supaya user tidak diberi peringatan untuk hal yang memang
    belum dikonfigurasi.
    """
    issues = fr.check_api_key(config or {})
    return issues[0].detail if issues else ""
