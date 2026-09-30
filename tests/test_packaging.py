"""
Test untuk packaging: build_exe.py dan installer.

Yang diuji di sini bukan "build-nya jalan" (itu butuh beberapa menit dan
butuh PyInstaller terinstall), tapi INVARIAN yang sering dilanggar tanpa disadari:

  - resource yang dibaca runtime ikut ke dalam bundle
  - dokumen legal ikut ke dalam bundle
  - aset berlisensi komersial TIDAK ikut
  - argumen PyInstaller yang dibentuk dengan benar (termasuk separator Windows)
  - installer tidak menulis ke folder aplikasi dan tidak menaruh API key di disk

Kalau salah satu ini bergeser, gejalanya bukan crash yang jujur — subtitle
hilang diam-diam, atau aplikasi tidak bisa dibuka karena satu file kurang.
"""
import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build_exe  # noqa: E402
from clipper_legal import BLOCKED_ASSETS  # noqa: E402


class TestBuildCommand:
    def test_uses_onedir_not_onefile(self):
        cmd = build_exe.build_command()
        assert "--onedir" in cmd
        assert "--onefile" not in cmd, (
            "onefile ekstrak ke %TEMP% tiap launch dan menghapus dirinya saat "
            "keluar — kelas bug path yang harus dihindari"
        )

    def test_windowed(self):
        """--windowed supaya tidak ada console window di balik GUI."""
        assert "--windowed" in build_exe.build_command()

    def test_entry_point_is_gui(self):
        cmd = build_exe.build_command()
        assert cmd[-1].endswith("clipper_gui_modern.py")

    def test_add_data_uses_correct_separator(self):
        """Separator harus ';' di Windows, ':' di POSIX.

        Kalau salah, PyInstaller tidak protes — dia hanya menghasilkan folder
        yang tidak pernah dibaca aplikasi. Ini harus gagal di test, bukan di
        laptop user.
        """
        expected = ";" if os.name == "nt" else ":"
        data_args = [a for a in build_exe.build_command() if a.startswith("--add-data=")]
        assert data_args, "tidak ada --add-data sama sekali"
        for arg in data_args:
            assert expected in arg, f"separator salah di: {arg}"

    def test_add_data_never_ships_secrets(self):
        cmd = build_exe.build_command()
        for forbidden in (".env", "config.json", "secrets.dat", "cookies.txt"):
            for arg in cmd:
                assert forbidden not in arg, f"{forbidden} masuk ke build: {arg}"

    def test_excludes_web_only_packages(self):
        """gradio/streamlit hanya untuk Colab; ikutnya menambah ratusan MB."""
        cmd = " ".join(build_exe.build_command())
        assert "--exclude-module=gradio" in cmd
        assert "--exclude-module=streamlit" in cmd


class TestBundledResources:
    """Resource yang dibaca runtime wajib ikut. Tidak ikut = crash saat frozen."""

    @pytest.mark.parametrize("rel", [
        "fonts", "bin", "vendor", "backsound",
    ])
    def test_required_data_dir_present(self, rel):
        assert (ROOT / rel).exists(), f"{rel}/ hilang dari repo — build akan gagal"

    def test_data_args_cover_every_required_dir(self):
        args = " ".join(build_exe.build_command())
        for name in build_exe.REQUIRED_DATA_DIRS:
            assert f";{name}" in args or f":{name}" in args, (
                f"{name}/ tidak masuk ke --add-data"
            )

    def test_legal_documents_bundled(self):
        """OFL 1.1 dan Apache 2.0 mewajibkan teks lisensi ikut distribusi."""
        args = " ".join(build_exe.build_command())
        assert "licenses" in args
        assert "THIRD_PARTY_NOTICES.md" in args
        assert "LICENSE" in args

    def test_skip_dirs_not_bundled(self):
        args = " ".join(build_exe.build_command())
        for junk in ("notebooks", "tests"):
            assert f";{junk}" not in args and f":{junk}" not in args


class TestVerifyBuild:
    """verify_build() harus bisa menangkap build yang tidak lengkap."""

    def _make_bundle(self, tmp_path, internal=True):
        """Buat bundle yang minimal valid, mengikuti layout PyInstaller 6.x."""
        base = tmp_path / "dist" / build_exe.EXE_NAME
        data = base / "_internal" if internal else base
        for sub in ("fonts", "bin", "licenses"):
            (data / sub).mkdir(parents=True, exist_ok=True)
        (base / f"{build_exe.EXE_NAME}.exe").write_bytes(b"MZ")
        (data / "fonts" / "Montserrat-Bold.ttf").write_bytes(b"x")
        (data / "bin" / "detector.tflite").write_bytes(b"x")
        (data / "LICENSE").write_text("MIT")
        (data / "THIRD_PARTY_NOTICES.md").write_text("x")
        (data / "licenses" / "OFL.txt").write_text("SIL OPEN FONT LICENSE")
        return base, data

    def test_reports_missing_dist(self, tmp_path, monkeypatch):
        monkeypatch.setattr(build_exe, "ROOT", tmp_path)
        problems = build_exe.verify_build()
        assert problems and "tidak ada" in problems[0]

    def test_accepts_pyinstaller6_internal_layout(self, tmp_path, monkeypatch):
        """PyInstaller 6 menaruh data di _internal/ — verifier harus menemukannya.

        Ini bug yang nyata: versi pertama dari verify_build() mencari di root dan
        melaporkan 5 resource hilang padahal semua ada di _internal/.
        """
        self._make_bundle(tmp_path, internal=True)
        monkeypatch.setattr(build_exe, "ROOT", tmp_path)
        assert build_exe.verify_build() == []

    def test_accepts_flat_layout(self, tmp_path, monkeypatch):
        """Beberapa konfigurasi menaruh data langsung di root."""
        self._make_bundle(tmp_path, internal=False)
        monkeypatch.setattr(build_exe, "ROOT", tmp_path)
        assert build_exe.verify_build() == []

    def test_reports_missing_legal_docs(self, tmp_path, monkeypatch):
        base, data = self._make_bundle(tmp_path)
        (data / "LICENSE").unlink()
        (data / "THIRD_PARTY_NOTICES.md").unlink()
        (data / "licenses" / "OFL.txt").unlink()
        monkeypatch.setattr(build_exe, "ROOT", tmp_path)
        problems = build_exe.verify_build()
        assert any("LICENSE" in p for p in problems)
        assert any("THIRD_PARTY" in p for p in problems)
        assert any("OFL" in p for p in problems)

    def test_flags_bundled_restricted_asset(self, tmp_path, monkeypatch):
        """Kalau font komersial nyasar ke bundle, build harus GAGAL."""
        base, data = self._make_bundle(tmp_path)
        (data / "fonts" / "KOMIKAX_.ttf").write_bytes(b"x")
        monkeypatch.setattr(build_exe, "ROOT", tmp_path)
        problems = build_exe.verify_build()
        assert any("terlarang" in p for p in problems), (
            f"font berlisensi komersial ikut bundle tapi tidak dilaporkan: {problems}"
        )

    def test_passes_on_complete_bundle(self, tmp_path, monkeypatch):
        self._make_bundle(tmp_path)
        monkeypatch.setattr(build_exe, "ROOT", tmp_path)
        assert build_exe.verify_build() == []


class TestNoRestrictedAssetInRepo:
    """Aset terlarang tidak boleh ada di repo, bukan cuma di bundle."""

    def test_no_commercial_font_in_repo(self):
        for asset in BLOCKED_ASSETS:
            assert not (ROOT / asset.name).exists()
            assert not (ROOT / "fonts" / asset.name).exists()


class TestInstallerScript:
    """installer harus idempoten dan tidak menaruh secret di disk."""

    def _setup_script(self):
        for candidate in ROOT.rglob("*.ps1"):
            if "install" in candidate.name.lower():
                return candidate
        return None

    def test_installer_exists(self):
        assert self._setup_script() is not None, (
            "tidak ada skrip installer (.ps1) — produk yang dijual butuh "
            "installer yang bisa dijalankan user di PC kosong"
        )

    def test_installer_does_not_write_secrets_to_disk(self):
        script = self._setup_script()
        if script is None:
            pytest.skip("tidak ada installer")
        text = script.read_text(encoding="utf-8", errors="ignore").lower()
        # Installer boleh menerima key, tapi tidak boleh menuliskannya ke file.
        assert not re.search(r"set-content.*api[-_]?key", text)
        assert not re.search(r"out-file.*api[-_]?key", text)

    def test_installer_checks_python_before_installing(self):
        script = self._setup_script()
        if script is None:
            pytest.skip("tidak ada installer")
        text = script.read_text(encoding="utf-8", errors="ignore")
        assert "python" in text.lower()
        assert "requirements.txt" in text or "pip install" in text.lower()
