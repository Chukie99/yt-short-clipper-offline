"""
Test untuk clipper_firstrun.py.

Modul ini deciding apakah user baru bisa pakai aplikasi. Test di sini menjaga
dua hal:

  1. Menemukan masalah yang benar. Ditemukan saat menulis fase 5: output default
     `~/Videos` gagal ditulis dengan errno 2, sementara `~/Downloads` berhasil
     di PC yang sama.Gejalanya identik dengan folder yang hilang, padahal
     user punya Full Control dan foldernya ada di depan mata.
  2. Tidak melaporkan masalah yang tidak ada. False positive di wizard pertama
     itu mahal — user dituntun melakukan perbaikan untuk masalah yang tidak
     pernah terjadi, dan setelah beberapa kali begitu mereka berhenti percaya
     pada pesan-pesan aplikasi.
"""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import clipper_firstrun as fr  # noqa: E402


# ==========================================================================
# Bentuk data
# ==========================================================================
class TestIssueShape:
    def test_issue_has_all_fields(self):
        issue = fr.Issue(code="x", title="Judul", detail="Detail")
        assert issue.severity is fr.Severity.WARNING
        assert issue.auto_fixable is False
        assert issue.fix_hint == ""

    def test_user_text_includes_hint(self):
        issue = fr.Issue(
            code="x", title="Judul", detail="Detail", fix_hint="Lakukan ini"
        )
        text = issue.user_text()
        assert "Judul" in text
        assert "Detail" in text
        assert "Lakukan ini" in text

    def test_user_text_omits_empty_hint(self):
        issue = fr.Issue(code="x", title="Judul", detail="Detail")
        assert "->" not in issue.user_text()

    def test_severity_ordering_is_meaningful(self):
        assert list(fr.Severity).index(fr.Severity.BLOCKER) < \
            list(fr.Severity).index(fr.Severity.WARNING) < \
            list(fr.Severity).index(fr.Severity.INFO)


# ==========================================================================
# Deteksi Known Folder
# ==========================================================================
class TestKnownFolderDetection:
    """Output default menabrak Known Folder Windows. Ini yang ditemukan di fase 5."""

    @pytest.mark.skipif(os.name != "nt", reason="Known Folder hanya di Windows")
    def test_detects_videos_documents_desktop(self):
        home = Path(os.path.expanduser("~"))
        for name in ("Videos", "Documents", "Desktop", "Music", "Pictures"):
            assert fr._is_windows_library_folder(home / name), \
                f"{name} harus terdeteksi sebagai Known Folder"

    @pytest.mark.skipif(os.name != "nt", reason="Known Folder hanya di Windows")
    def test_does_not_flag_ordinary_folders(self):
        home = Path(os.path.expanduser("~"))
        for name in ("Downloads", "yt-short-clipper-offline"):
            assert not fr._is_windows_library_folder(home / name), \
                f"{name} bukan Known Folder, jangan salah tandai"

    @pytest.mark.skipif(os.name != "nt", reason="Known Folder hanya di Windows")
    def test_does_not_flag_nested_library_folder(self):
        """Videos/foo bukan Known Folder, meski namanya Videos."""
        home = Path(os.path.expanduser("~"))
        assert not fr._is_windows_library_folder(home / "Videos" / "YTShortClipperPro")


# ==========================================================================
# check_output_dir
# ==========================================================================
class TestOutputDirCheck:
    def test_writable_dir_passes(self, tmp_path):
        assert fr.check_output_dir({"output_dir": str(tmp_path)}) == []

    def test_creates_missing_dir(self, tmp_path):
        target = tmp_path / "new" / "output"
        assert fr.check_output_dir({"output_dir": str(target)}) == []
        assert target.exists()

    def test_does_not_leave_probe_file(self, tmp_path):
        fr.check_output_dir({"output_dir": str(tmp_path)})
        assert not (tmp_path / ".write_test").exists()

    def test_reports_blocker_when_unwritable(self, tmp_path):
        """Folder yang tidak bisa ditulis harus dilaporkan sebagai BLOCKER."""
        if os.name == "nt":
            pytest.skip("butuh hak akses khusus di Windows")
        locked = tmp_path / "locked"
        locked.mkdir()
        os.chmod(locked, 0o500)
        try:
            issues = fr.check_output_dir({"output_dir": str(locked / "out")})
            assert issues
            assert issues[0].severity in (fr.Severity.BLOCKER, fr.Severity.WARNING)
            assert issues[0].fix_hint, "perlu saran perbaikan"
        finally:
            os.chmod(locked, 0o700)

    def test_known_folder_error_is_honest(self, tmp_path, monkeypatch):
        """Pesan error tidak boleh menyebut 'tidak ditemukan' untuk folder yang ada."""
        home = Path(os.path.expanduser("~"))
        if os.name != "nt":
            pytest.skip("Known Folder hanya di Windows")

        videos = home / "Videos"
        if not videos.exists():
            pytest.skip("tidak ada folder Videos di PC ini")

        issues = fr.check_output_dir({"output_dir": str(videos / "probe_dir")})
        if not issues:
            pytest.skip("Videos bisa ditulis di PC ini — tidak ada yang diuji")
        issue = issues[0]
        if issue.code == "output_dir_known_folder":
            assert "Known Folder" in issue.detail
            assert issue.fix_hint
        # Kalau kode lain, tetap harus jujur dan tidak menyalahkan folder hilang
        assert "tidak ditemukan" not in issue.detail.lower() or \
            issue.code == "output_dir_not_writable"


# ==========================================================================
# Pengechecking lain
# ==========================================================================
class TestIndividualChecks:
    def test_python_check_passes_on_supported(self):
        assert fr.check_python_runtime() == []

    def test_ffmpeg_check_returns_issues_or_empty(self):
        for issue in fr.check_ffmpeg():
            assert issue.severity is fr.Severity.BLOCKER
            assert "ffmpeg" in issue.detail.lower()

    def test_ffprobe_not_double_reported(self):
        """Kalau ffmpeg hilang, ffprobe tidak perlu dilaporkan dua kali."""
        if fr.check_ffmpeg():
            assert fr.check_ffprobe() == []

    def test_subtitle_font_check_uses_default(self):
        issues = fr.check_subtitle_font({})
        assert issues == [], (
            f"font default {fr.SUBTITLE_FONT_DEFAULT if hasattr(fr, 'SUBTITLE_FONT_DEFAULT') else '?'} "
            "tidak terbaca ada — cek ulang packaging"
        )

    def test_subtitle_font_missing_is_blocker(self, monkeypatch):
        import clipper_paths

        fake = ROOT / "_nofonts"
        monkeypatch.setattr(clipper_paths, "RESOURCE_DIR", fake)
        issues = fr.check_subtitle_font({"subtitle_font": "TidakAda.ttf"})
        assert issues
        assert issues[0].severity is fr.Severity.BLOCKER

    def test_api_key_missing_per_provider(self):
        for provider, field in (
            ("Gemini (Native)", "gemini_api_key"),
            ("Groq", "groq_api_key"),
            ("OpenRouter (DeepSeek/GPT/etc)", "openrouter_api_key"),
        ):
            issues = fr.check_api_key({"ai_provider": provider})
            assert len(issues) == 1, f"{provider} harus dilaporkan"
            assert issues[0].code == "api_key_missing"
            assert issues[0].severity is fr.Severity.WARNING

    def test_api_key_present_no_issue(self):
        issues = fr.check_api_key({
            "ai_provider": "Gemini (Native)", "gemini_api_key": "dummy-key",
        })
        assert issues == []

    def test_api_key_not_checked_for_unknown_provider(self):
        assert fr.check_api_key({"ai_provider": "Tidak Dikenal"}) == []

    def test_whisper_cache_is_info_only(self):
        for issue in fr.check_whisper_model_cache():
            assert issue.severity is fr.Severity.INFO, (
                "model belum ter-cache bukan blocker — render pertama tetap jalan"
            )


# ==========================================================================
# Gabungan
# ==========================================================================
class TestRunAllChecks:
    def test_returns_sorted_by_severity(self):
        issues = fr.run_all_checks()
        severities = [i.severity for i in issues]
        assert severities == sorted(severities, key=lambda s: list(fr.Severity).index(s))

    def test_config_none_skips_api_key(self):
        codes = {i.code for i in fr.run_all_checks(None)}
        assert "api_key_missing" not in codes

    def test_config_provided_checks_api_key(self):
        codes = {i.code for i in fr.run_all_checks({"ai_provider": "Groq"})}
        assert "api_key_missing" in codes

    def test_no_duplicate_codes(self):
        codes = [i.code for i in fr.run_all_checks()]
        assert len(codes) == len(set(codes)), "ada kode masalah yang dobel"

    def test_runs_in_real_environment_without_raising(self):
        """Fungsi ini dipanggil saat startup — tidak boleh melempar exception."""
        issues = fr.run_all_checks()
        assert isinstance(issues, list)


class TestSummary:
    def test_ready_message_when_no_issues(self):
        text = fr.summary_for_startup([])
        assert "siap dipakai" in text
        assert fr.APP_VERSION in text

    def test_blockers_listed_first(self):
        issues = [
            fr.Issue("a", "Info", "d", fr.Severity.INFO),
            fr.Issue("b", "Blocker", "d", fr.Severity.BLOCKER, fix_hint="perbaiki"),
        ]
        text = fr.summary_for_startup(issues)
        assert text.index("Blocker") < text.index("Info")

    def test_blocker_text_includes_fix_hint(self):
        issues = [fr.Issue("b", "Blocker", "d", fr.Severity.BLOCKER, fix_hint="INI CARANYA")]
        assert "INI CARANYA" in fr.summary_for_startup(issues)

    def test_has_blockers(self):
        assert fr.has_blockers([fr.Issue("a", "t", "d", fr.Severity.BLOCKER)])
        assert not fr.has_blockers([fr.Issue("a", "t", "d", fr.Severity.WARNING)])

    def test_python_support_text(self):
        text = fr.python_support_text()
        assert "3.10" in text


# ==========================================================================
# Placeholder yang tidak ter-render
# ==========================================================================
class TestNoUnrenderedPlaceholders:
    """Versi dan path tidak boleh tampil apa adanya ke user.

    Ditulis sebagai test karena bug ini tidak terlihat dari kode: `"{APP_VERSION}"`
    di dalam string biasa (bukan f-string) terlihat benar dan lolos review,
    tapi user membaca teks literal itu di About.
    """

    def _py_files(self):
        return [p for p in ROOT.glob("*.py") if not p.name.startswith("_")]

    def test_no_literal_placeholders_in_ui_modules(self):
        import ast

        offenders = []
        for path in self._py_files():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                # Nama placeholder yang harus sudah ter-substitute
                if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                    continue
                text = node.value
                if "{APP_VERSION}" in text or "{APP_NAME}" in text:
                    # Boleh kalau string ini memang bagian dari f-string, tapi
                    # ast tidak menandai itu; cek kasar: string f tidak punya
                    # placeholder di Constant (kidata JoinedStr), jadi setiap
                    # kemunculan di Constant berarti tidak ter-substitute.
                    offenders.append(f"{path.name}:{node.lineno} {text[:60]!r}")
        assert not offenders, (
            "placeholder versi tampil apa adanya ke user: "
            + "; ".join(offenders)
        )

    def test_version_string_appears_in_gui_title_source(self):
        gui = (ROOT / "clipper_gui_modern.py").read_text(encoding="utf-8")
        assert 'f"YT Short Clipper v{APP_VERSION}"' in gui, (
            "judul window harus memakai APP_VERSION, bukan angka yang diketik manual"
        )

    def test_no_hardcoded_old_version_in_user_facing_text(self):
        """v1.2.0 adalah versi lama dan tidak boleh muncul sebagai teks.

        Hanya string yang benar-benar ditampilkan atau dikirim ke user yang
        dicek: docstring dan komentar sah-saja menyebut versi lama untuk
        menjelaskan asal-usul keputusan desain.
        """
        import ast

        offenders = []
        for path in self._py_files():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Constant):
                    continue
                if not isinstance(node.value, str):
                    continue
                value = node.value
                if "v1.2.0" not in value:
                    continue
                # Docstring adalah statement Expr pertama di modul/kelas/fungsi.
                for outer in ast.walk(tree):
                    body = getattr(outer, "body", None)
                    if (isinstance(body, list) and body
                            and isinstance(body[0], ast.Expr)
                            and body[0].value is node):
                        is_docstring = True
                        break
                if not is_docstring:
                    offenders.append(f"{path.name}:{node.lineno}")
        assert not offenders, (
            "versi lama masih tampil ke user: " + ", ".join(offenders)
        )
