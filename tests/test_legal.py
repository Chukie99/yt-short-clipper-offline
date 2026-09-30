"""
Test untuk clipper_legal.py dan clipper_version.py.

Ini test yang menjaga GERBANG RILIS. Kalau produk ini dijual, pertanyaan
"boleh nggak aset ini ikut installer" harus punya jawaban otomatis, bukan
jawaban dari ingatan penyusun installer.

Yang dijaga:
  - Tidak ada aset berlisensi komersial yang masih ter-BUNDLE
  - Font default benar-benar ada di repo dan bebas redistribusi
  - LICENSE dan THIRD_PARTY_NOTICES ada
  - Teks lisensi pihak ketiga ikut dikemas
  - Versi Python konsisten di semua tempat
"""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from clipper_legal import (  # noqa: E402
    APP_LICENSE, BUNDLED_ASSETS, BLOCKED_ASSETS, EXTERNAL_ASSETS,
    FALLBACK_FONTS, SUBTITLE_FONT_DEFAULT, bundled_summary, legal_summary_for_ui, redistribution_allowed,
)
from clipper_version import (  # noqa: E402
    APP_VERSION, EOL_PYTHON, MAX_TESTED_PYTHON, MIN_PYTHON, check_python,
    min_python_str, python_requirement_str,
)

ROOT = Path(__file__).resolve().parents[1]


# ==========================================================================
# Gerbang rilis
# ==========================================================================
class TestReleaseGate:
    def test_no_blocked_asset_is_bundled(self):
        """Aset terlarang tidak boleh berstatus bundled."""
        offenders = [a.name for a in BLOCKED_ASSETS if a.bundled]
        assert not offenders, f"aset terlarang ikut dikemas: {offenders}"

    def test_redistribution_allowed(self):
        assert redistribution_allowed() is True

    def test_every_bundled_asset_is_commercially_usable(self):
        for asset in BUNDLED_ASSETS:
            assert asset.commercial_use, (
                f"{asset.name} dikemas tapi tidak boleh dipakai komersial"
            )

    def test_every_bundled_asset_declares_a_license(self):
        for asset in BUNDLED_ASSETS:
            assert asset.license_id, f"{asset.name} tidak menyebut lisensi"

    def test_bundled_asset_with_requirement_has_license_file(self):
        """Kalau atribusi wajib, teks lisensi harus ikut."""
        for asset in BUNDLED_ASSETS:
            if asset.attribution_required:
                assert asset.license_file, (
                    f"{asset.name} butuh atribusi tapi license_file kosong"
                )
                assert (ROOT / asset.license_file).exists(), (
                    f"{asset.license_file} tidak ada di repo — wajib ikut installer"
                )

    def test_external_assets_are_not_bundled(self):
        for asset in EXTERNAL_ASSETS:
            assert not asset.bundled, f"{asset.name} tidak seharusnya dikemas"


# ==========================================================================
# Font
# ==========================================================================
class TestFontLicensing:
    def test_default_font_exists_in_repo(self):
        assert (ROOT / "fonts" / SUBTITLE_FONT_DEFAULT).exists(), (
            f"font default {SUBTITLE_FONT_DEFAULT} tidak ada"
        )

    def test_default_font_is_ofl_licensed(self):
        """Font default harus punya nameID 14 (URL lisensi) — tanda SIL OFL."""
        font_path = ROOT / "fonts" / SUBTITLE_FONT_DEFAULT
        if not font_path.exists():
            pytest.skip("fontTools tidak terinstall")
        fontTools = pytest.importorskip("fontTools")
        from fontTools.ttLib import TTFont

        font = TTFont(str(font_path), fontNumber=0, lazy=True)
        license_url = font["name"].getDebugName(14)
        copyright_ = font["name"].getDebugName(0) or ""
        assert license_url, (
            f"{SUBTITLE_FONT_DEFAULT} tidak punya nameID 14 (lisensi). "
            f"copyright: {copyright_}"
        )
        assert "openfontlicense" in license_url.lower() or "SIL" in license_url.upper()

    def test_commercial_font_not_in_repo(self):
        assert not (ROOT / "fonts" / "KOMIKAX_.ttf").exists(), (
            "KOMIKAX_.ttf berlisensi komersial dan tidak boleh ada di repo"
        )

    def test_no_all_rights_reserved_font_shipped(self):
        """Scan semua font: yang copyright-nya 'All rights reserved' tertangkap."""
        fontTools = pytest.importorskip("fontTools")
        from fontTools.ttLib import TTFont

        offenders = []
        for font_path in (ROOT / "fonts").glob("*"):
            if font_path.suffix.lower() not in (".ttf", ".otf"):
                continue
            try:
                font = TTFont(str(font_path), fontNumber=0, lazy=True)
            except Exception:  # noqa: BLE001 — font rusak bukan pelanggaran lisensi
                continue
            copyright_ = font["name"].getDebugName(0) or ""
            license_url = font["name"].getDebugName(14)
            if "all rights reserved" in copyright_.lower() and not license_url:
                offenders.append(font_path.name)
        assert not offenders, f"font 'all rights reserved' di repo: {offenders}"

    def test_all_fonts_in_repo_are_free(self):
        """Setiap font di repo harus punya lisensi redistribusi yang jelas."""
        fontTools = pytest.importorskip("fontTools")
        from fontTools.ttLib import TTFont

        free_markers = ("open font license", "sil ", "ofl", "apache", "gpl", "cc0")
        unproven = []
        for font_path in (ROOT / "fonts").glob("*"):
            if font_path.suffix.lower() not in (".ttf", ".otf"):
                continue
            try:
                font = TTFont(str(font_path), fontNumber=0, lazy=True)
                names = font["name"]
                blob = " ".join(
                    (names.getDebugName(i) or "") for i in (0, 7, 13, 14)
                ).lower()
            except Exception:  # noqa: BLE001
                continue
            if not any(m in blob for m in free_markers):
                unproven.append(font_path.name)
        assert not unproven, (
            f"font tanpa lisensi yang jelas: {unproven}. "
            "Jangan dikemas tanpa verifikasi lisensi."
        )

    def test_fallback_fonts_exist_or_are_system_fonts(self):
        for name in FALLBACK_FONTS:
            if (ROOT / "fonts" / name).exists():
                continue
            assert name.lower() in (
                "arialbd.ttf", "impact.ttf", "arial.ttf",
            ), f"fallback {name} tidak ada dan bukan font sistem yang dikenal"

    def test_audit_detects_blocked_font(self, tmp_path, monkeypatch):
        """Audit harus melaporkan, bukan menghapus file user sendiri."""
        import clipper_legal

        fake = tmp_path / "fonts"
        fake.mkdir()
        (fake / "Montserrat-Bold.ttf").write_bytes(b"x")
        (fake / "komikax_.ttf").write_bytes(b"x")   # huruf kecil harus terdeteksi
        # RESOURCE_DIR di-import di dalam fungsi, jadi yang dipatch adalah
        # clipper_paths-nya.
        import clipper_paths

        monkeypatch.setattr(clipper_paths, "RESOURCE_DIR", tmp_path)
        found = clipper_legal.audit_installed_fonts()
        assert len(found) == 1, f"harus tepat 1, dapat {found}"
        assert found[0].lower() == "komikax_.ttf"
        # file tidak boleh dihapus
        assert (fake / "komikax_.ttf").exists(), "audit tidak boleh menghapus file"


# ==========================================================================
# Dokumen legal
# ==========================================================================
class TestLegalDocuments:
    def test_license_file_exists(self):
        assert (ROOT / "LICENSE").exists(), "README/File badge refers to LICENSE but it's missing"

    def test_license_is_mit_and_matches_badge(self):
        text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        assert "MIT License" in text
        assert APP_LICENSE == "MIT"

    def test_third_party_notices_exist(self):
        assert (ROOT / "THIRD_PARTY_NOTICES.md").exists()

    def test_notices_mention_every_bundled_asset(self):
        text = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        for asset in BUNDLED_ASSETS:
            assert asset.name.split(" ")[0] in text, (
                f"{asset.name} tidak disebut di THIRD_PARTY_NOTICES.md"
            )

    def test_notices_mention_every_external_asset(self):
        text = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        for asset in EXTERNAL_ASSETS:
            keyword = asset.name.split(" ")[0]
            assert keyword in text, f"{asset.name} tidak disebut di THIRD_PARTY_NOTICES.md"

    def test_license_texts_present_and_real(self):
        """Teks lisensi harus isi, bukan stub."""
        ofl = (ROOT / "licenses" / "OFL.txt").read_text(encoding="utf-8")
        assert "SIL OPEN FONT LICENSE" in ofl.upper()
        assert len(ofl) > 2000, "OFL.txt terpotong"
        apache = (ROOT / "licenses" / "Apache-2.0.txt").read_text(encoding="utf-8")
        assert "Apache License" in apache
        assert "Version 2.0" in apache
        assert len(apache) > 8000, "Apache-2.0.txt terpotong"


# ==========================================================================
# Binari
# ==========================================================================
class TestNoBundledBinaries:
    """Temuan audit justru salah di sini: bin/ TIDAK berisi ffmpeg/yt-dlp."""

    def test_bin_has_no_ffmpeg_or_ytdlp(self):
        bin_dir = ROOT / "bin"
        if not bin_dir.exists():
            pytest.skip("bin/ tidak ada")
        names = {f.name.lower() for f in bin_dir.iterdir()}
        assert not any("ffmpeg" in n or "yt-dlp" in n or "ytdlp" in n for n in names), (
            f"bin/ berisi executable: {names}. Kalau memang ada, wajib ada "
            "THIRD_PARTY_NOTICES + kewajiban LGPL/GPL."
        )

    def test_bin_contains_mediapipe_models(self):
        bin_dir = ROOT / "bin"
        if not bin_dir.exists():
            pytest.skip("bin/ tidak ada")
        names = {f.name.lower() for f in bin_dir.iterdir()}
        assert "detector.tflite" in names
        assert "deploy.prototxt" in names


# ==========================================================================
# Versi
# ==========================================================================
class TestVersion:
    def test_min_python_matches_wording(self):
        assert min_python_str() == "3.10"

    def test_requirement_string_complete(self):
        assert "3.10" in python_requirement_str()
        assert "3.12" in python_requirement_str()

    def test_current_python_is_supported(self):
        assert check_python() == "", (
            f"Lingkungan dev memakai Python yang dianggap tidak didukung: {check_python()}"
        )

    def test_eol_versions_are_below_min(self):
        for v in EOL_PYTHON:
            assert v < MIN_PYTHON

    def test_max_tested_above_min(self):
        assert MAX_TESTED_PYTHON > MIN_PYTHON

    def test_app_version_consistent_across_modules(self):
        from clipper_paths import APP_VERSION as PATHS_VERSION

        assert PATHS_VERSION == APP_VERSION, (
            "duplicated version number — this is the exact problem clipper_version.py solves"
        )

    def test_version_declared_semver(self):
        assert re.fullmatch(r"\d+\.\d+\.\d+", APP_VERSION), (
            f"APP_VERSION format tidak valid: {APP_VERSION}"
        )

    def test_code_syntax_requires_min_python(self):
        """Jaga alasan kenapa min_python = 3.10.

        clipper_core.py memakai PEP 604 (`dict | None`) tanpa
        `from __future__ import annotations`. Kalau suatu hari angka ini diubah
        ke 3.9, test ini gagal — bukan diam-diam menghasilkan file yang tidak
        bisa jalan di 3.9.
        """
        core = (ROOT / "clipper_core.py").read_text(encoding="utf-8")
        uses_pep604 = re.search(r": *[A-Za-z_][A-Za-z0-9_]* *\| *None", core)
        assert not core.startswith("from __future__")
        if uses_pep604:
            assert MIN_PYTHON >= (3, 10), (
                "clipper_core.py masih memakai PEP 604 tanpa future import — "
                "min Python tidak boleh di bawah 3.10"
            )


# ==========================================================================
# Konsistensi README
# ==========================================================================
class TestReadmeAccuracy:
    def test_readme_states_correct_python_floor(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        assert "3.8" not in readme, (
            "README masih mengklaim Python 3.8+, padahal minsmium sebenarnya 3.10"
        )
        assert "3.10" in readme

    def test_readme_does_not_claim_no_watermark(self):
        """YouTube tidak punya watermark — klaim lama itu salah."""
        readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
        assert "tanpa watermark" not in readme
        assert "no watermark" not in readme

    def test_readme_is_honest_about_cloud_ai(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
        assert "cloud" in readme, "README harus jujur bahwa analisis AI lewat cloud"

    def test_readme_has_license_section(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        assert "LICENSE" in readme
        assert "THIRD_PARTY_NOTICES.md" in readme


# ==========================================================================
# UI
# ==========================================================================
class TestUiData:
    def test_legal_summary_shape(self):
        data = legal_summary_for_ui()
        assert set(data) == {"app_license", "copyright", "bundled", "external", "blocked"}
        assert isinstance(data["bundled"], list)

    def test_bundled_summary_is_readable(self):
        text = bundled_summary()
        assert "Montserrat" in text
        assert len(text.splitlines()) >= len(BUNDLED_ASSETS) + len(EXTERNAL_ASSETS)
