"""
Test untuk installer PowerShell.

Dua kelas bug yang nyata terjadi di file .ps1, dan keduanya dicek di sini:

1. Windows PowerShell 5.1 membaca file .ps1 sebagai ANSI kalau tidak ada BOM.
   Efeknya bukan error yang jujur — setiap karakter non-ASCII (em-dash di
   "YT Short Clipper Pro — Installer") mengacor baris string, dan karena string
   itu tidak pernah tertutup, SEMUA baris setelahnya dilaporkan rusak. Akar
   masalahnya satu byte yang hilang, tapi gejalanya 19 error di tempat yang
   tidak ada hubungannya.

2. "$var (teks)" di dalam string adalah subexpression di PowerShell, bukan
   teks. Parse error yang sama muncul di beberapa tempat kalau tidak dihindari.

Parse check dijalankan sungguhan lewat Parser.ParseFile, bukan regex, karena
inilah satu-satunya cara memverifikasi sintaks tanpa menjalankan installer.
"""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INSTALLER_DIR = ROOT / "installer"
PS_SCRIPTS = sorted(INSTALLER_DIR.glob("*.ps1"))


class TestPowerShellSyntax:
    def test_installer_scripts_exist(self):
        assert PS_SCRIPTS, "tidak ada .ps1 di installer/"

    @pytest.mark.parametrize("script", PS_SCRIPTS, ids=lambda p: p.name)
    def test_script_parses(self, script):
        """Nilai balik 0 = tidak ada error sintaks sama sekali."""
        if sys.platform != "win32":
            pytest.skip("PowerShell hanya di Windows")
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", str(INSTALLER_DIR / "check_syntax.ps1"),
                "-ScriptPath", str(script),
            ],
            capture_output=True,
        text=True,
            timeout=180,
        )
        assert result.returncode == 0, (
            f"{script.name} gagal parse:\n{result.stdout}{result.stderr}"
        )

    @pytest.mark.parametrize("script", PS_SCRIPTS, ids=lambda p: p.name)
    def test_script_has_utf8_bom(self, script):
        """Tanpa BOM, karakter non-ASCII merusak baris string di PS 5.1."""
        raw = script.read_bytes()
        assert raw.startswith(b"\xef\xbb\xbf"), (
            f"{script.name} tidak punya BOM UTF-8. Windows PowerShell 5.1 akan "
            "membacanya sebagai ANSI dan merusak setiap baris yang memuat "
            "karakter non-ASCII — gejalanya jauh dari lokasi masalahnya."
        )

    @pytest.mark.parametrize("script", PS_SCRIPTS, ids=lambda p: p.name)
    def test_no_variable_followed_by_paren_in_string(self, script):
        """"$var (teks)" = subexpression di PowerShell, bukan teks."""
        import re

        text = script.read_text(encoding="utf-8-sig")
        offenders = [
            (i, line.strip())
            for i, line in enumerate(text.split("\n"), 1)
            if re.search(r'"\s*\$[A-Za-z_][A-Za-z0-9_.]*\s*\(', line)
        ]
        assert not offenders, (
            f'pakai "$var (teks)" di dalam string: {offenders}. '
            "PowerShell menganggapnya subexpression."
        )


class TestInstallerSafety:
    def _install_ps1(self):
        return INSTALLER_DIR / "install.ps1"

    def test_does_not_write_api_keys_to_disk(self):
        """Installer boleh menerima key, tapi tidak boleh menuliskannya."""
        import re

        text = self._install_ps1().read_text(encoding="utf-8-sig")
        for pattern in (
            r"Set-Content[^\n]*api[-_ ]?key",
            r"Out-File[^\n]*api[-_ ]?key",
            r'"[a-z_]*api_key[a-z_]*"\s*=\s*"[A-Za-z0-9]',
        ):
            assert not re.search(pattern, text, re.IGNORECASE), (
                f"installer seems to write an API key to disk: {pattern}"
            )

    def test_does_not_create_temp_or_output_in_app_folder(self):
        """Pola yang dihindari: mkdir temp/output di dalam folder aplikasi."""
        import re

        text = self._install_ps1().read_text(encoding="utf-8-sig")
        offenders = [
            line.strip()
            for line in text.split("\n")
            if re.search(r'New-Item[^\n]*-Path[^\n]*\\"(temp|output)\\"', line)
        ]
        assert not offenders, f"installer membuat folder di app dir: {offenders}"

    def test_uses_virtualenv_not_system_python(self):
        text = self._install_ps1().read_text(encoding="utf-8-sig")
        assert ".venv" in text, "installer harus memakai venv, bukan system Python"

    def test_checks_ffmpeg(self):
        text = self._install_ps1().read_text(encoding="utf-8-sig")
        assert "ffmpeg" in text.lower()

    def test_asks_before_downloading_executables(self):
        """Installer tidak boleh mengunduh executable tanpa ditanya."""
        text = self._install_ps1().read_text(encoding="utf-8-sig").lower()
        assert "read-host" in text, (
            "installer harus menanyakan sebelum mengunduh/memasang apa pun"
        )

    def test_is_idempotent(self):
        text = self._install_ps1().read_text(encoding="utf-8-sig")
        assert "Test-Path" in text, (
            "installer harus mengecek keberadaan dulu agar aman dijalankan ulang"
        )
