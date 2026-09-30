"""
Test untuk clipper_guard.py dan wiring-nya di GUI.

Yang diuji
----------
1. Gerbang benar-benar memblokir saat ada blocker, dan melepas saat tidak
2. Analisis tidak ditolak karena masalah render (dan sebaliknya)
3. Dialog berisi blocker + saran perbaikan, dalam bahasa yang terbaca
4. `show_startup_report()` benar-benar dipanggil — bug aslinya adalah check
   yang dijalankan lalu hasilnya dibuang, jadi test harus menangkap "dipanggil"
   dan bukan hanya "ada"

Poin 4 yang paling penting: keberadaan sebuah fungsi tidak membuktikan bahwa ia
dipakai. Check di fase 5 dijalankan saat startup lalu hasilnya langsung
dibuang — kode yang terlihat seperti safety check tapi berfungsi sebagai dead
code.
"""
import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import clipper_firstrun as fr  # noqa: E402
import clipper_guard as g  # noqa: E402

GUI = ROOT / "clipper_gui_modern.py"


# ==========================================================================
# GateResult
# ==========================================================================
class TestGateResult:
    def test_blockers_and_warnings_split(self):
        issues = [
            fr.Issue("a", "B", "d", fr.Severity.BLOCKER),
            fr.Issue("b", "W", "d", fr.Severity.WARNING),
            fr.Issue("c", "I", "d", fr.Severity.INFO),
        ]
        res = g.GateResult(can_proceed=False, issues=issues)
        assert [i.code for i in res.blockers] == ["a"]
        assert [i.code for i in res.warnings] == ["b"]

    def test_can_proceed_only_when_no_blocker(self):
        blocker = g.GateResult(
            can_proceed=False,
            issues=[fr.Issue("a", "t", "d", fr.Severity.BLOCKER)],
        )
        warning_only = g.GateResult(
            can_proceed=True,
            issues=[fr.Issue("b", "t", "d", fr.Severity.WARNING)],
        )
        assert not blocker.can_proceed
        assert warning_only.can_proceed
        assert warning_only.should_warn_only()
        assert not blocker.should_warn_only()

    def test_message_empty_when_can_proceed(self):
        res = g.gate_before_work({})
        if res.can_proceed:
            assert res.message == ""


# ==========================================================================
# gate_before_work
# ==========================================================================
class TestGateBeforeWork:
    def test_returns_gate_result(self):
        assert isinstance(g.gate_before_work({}), g.GateResult)

    def test_config_none_does_not_raise(self):
        """Dipakai sebelum Settings pernah dibuka."""
        assert g.gate_before_work(None) is not None

    def test_never_returns_duplicate_codes(self):
        codes = [i.code for i in g.gate_before_work({}).issues]
        assert len(codes) == len(set(codes))

    def test_render_issues_excluded_when_not_rendering(self):
        """Analisis tidak boleh ditolak karena ffmpeg tidak ada.

        Menolak analisis karena masalah render membuat user bingung: masalahnya
        tidak terkait, dan analisis tetap berguna (transkrip bisa dilihat).
        """
        res = g.gate_before_work({}, need_render=False)
        codes = {i.code for i in res.issues}
        for render_only in ("ffmpeg_missing", "ffprobe_missing",
                            "subtitle_font_missing", "output_dir_not_writable",
                            "output_dir_known_folder"):
            assert render_only not in codes, (
                f"{render_only} tidak boleh muncul di jalur analisis"
            )

    def test_api_key_checked_for_analysis(self):
        res = g.gate_before_work({"ai_provider": "Groq"}, need_render=False)
        codes = {i.code for i in res.issues}
        assert "api_key_missing" in codes

    def test_blocker_stops_proceed(self, monkeypatch):
        """Blocker harus benar-benar(can_proceed = False), bukan cuma diberi peringatan."""
        monkeypatch.setattr(
            g, "run_all_checks",
            lambda config=None: [fr.Issue("x", "Dummy", "d", fr.Severity.BLOCKER)],
        )
        res = g.gate_before_work({})
        assert res.can_proceed is False
        assert "Dummy" in res.message

    def test_warning_does_not_stop_proceed(self, monkeypatch):
        monkeypatch.setattr(
            g, "run_all_checks",
            lambda config=None: [fr.Issue("x", "Dummy", "d", fr.Severity.WARNING)],
        )
        res = g.gate_before_work({})
        assert res.can_proceed is True

    def test_info_does_not_stop_proceed(self, monkeypatch):
        monkeypatch.setattr(
            g, "run_all_checks",
            lambda config=None: [fr.Issue("x", "Dummy", "d", fr.Severity.INFO)],
        )
        assert g.gate_before_work({}).can_proceed is True


# ==========================================================================
# format_gate_dialog
# ==========================================================================
class TestDialogText:
    def test_blocker_dialog_has_three_parts(self):
        res = g.GateResult(
            can_proceed=False,
            issues=[fr.Issue("a", "Judul", "Detail", fr.Severity.BLOCKER,
                            fix_hint="Lakukan begini")],
        )
        text = g.format_gate_dialog(res)
        assert "Judul" in text
        assert "Detail" in text
        assert "Lakukan begini" in text

    def test_clean_state_says_ready(self):
        assert g.format_gate_dialog(g.GateResult(True, [])) == "Siap."

    def test_warning_dialog_lists_warnings_only(self):
        res = g.GateResult(
            True,
            [fr.Issue("a", "Peringatan", "d", fr.Severity.WARNING)],
        )
        text = g.format_gate_dialog(res)
        assert "Peringatan" in text
        assert "Belum bisa" not in text

    def test_dialog_does_not_bury_blocker_in_jargon(self):
        """Tidak boleh ada nama modul atau istilah internal di pesan user."""
        res = g.gate_before_work({})
        if not res.can_proceed:
            text = g.format_gate_dialog(res).lower()
            for jargon in ("sys._meipass", "resourcedir", "traceback",
                           "modulenotfounderror", "nonepath"):
                assert jargon not in text, f"jargon internal bocor ke user: {jargon}"


# ==========================================================================
# Wiring di GUI
# ==========================================================================
class TestGuiWiring:
    """Fase 5: check dijalankan lalu dibuang. Test ini menangkap itu."""

    def _tree(self):
        return ast.parse(GUI.read_text(encoding="utf-8"))

    def test_startup_report_method_exists(self):
        names = {n.name for n in ast.walk(self._tree()) if isinstance(n, ast.FunctionDef)}
        assert "show_startup_report" in names

    def test_startup_report_is_actually_called(self):
        """Keberadaan method bukan bukti dipakai — harus ada yang memanggil."""
        src = GUI.read_text(encoding="utf-8")
        assert "self.after(500, self.show_startup_report)" in src, (
            "show_startup_report() tidak pernah dipanggil — persis bug fase 5: "
            "check dijalankan lalu hasilnya dibuang"
        )

    def test_dependency_errors_kept_not_discarded(self):
        src = GUI.read_text(encoding="utf-8")
        assert "self.dependency_errors = check_dependencies()" in src
        assert "self.dependency_failed = len(self.dependency_errors) > 0" in src

    def test_gate_runs_before_queue_is_saved(self):
        """Gate harus sebelum antrean disimpan, kalau tidak state jadi tidak sinkron."""
        tree = self._tree()
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "start_processing")
        src = ast.get_source_segment(GUI.read_text(encoding="utf-8"), fn) or ""
        gate = src.find("gate_before_work")
        save = src.find("save_queue_state")
        thread = src.find("threading.Thread")
        assert -1 not in (gate, save, thread)
        assert gate < save < thread, (
            "urutan salah: gate harus dipanggil sebelum antrean disimpan dan "
            "sebelum thread render dijalankan"
        )

    def test_gate_blocks_before_thread_starts(self):
        """Kalau gate gagal, thread render tidak boleh sampai dijalankan."""
        tree = self._tree()
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "start_processing")
        src = ast.get_source_segment(GUI.read_text(encoding="utf-8"), fn) or ""
        gate = src.find("gate_before_work")
        thread = src.find("threading.Thread")
        between = src[gate:thread]
        assert "return" in between, (
            "tidak ada return setelah gate gagal — render akan tetap jalan"
        )

    def test_guard_module_imported(self):
        src = GUI.read_text(encoding="utf-8")
        assert "from clipper_guard import" in src
        assert "gate_before_work" in src

    def test_startup_report_runs_checks_not_just_log(self):
        """Isi method harus benar-benar menghitung, bukan hanya menampilkan."""
        tree = self._tree()
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "show_startup_report")
        src = ast.get_source_segment(GUI.read_text(encoding="utf-8"), fn) or ""
        assert "run_all_checks" in src
        assert "has_blockers" in src


# ==========================================================================
# Field output_dir di Settings
# ==========================================================================
class TestOutputDirFieldExists:
    """Gate memberi saran "ganti folder output di Settings".

    Tapi field itu tidak pernah ada di Settings. Saran tanpa aksi adalah
    jebakan: user diarahkan ke tempat yang tidak ada isinya, lalu menganggap
    aplikasinya rusak. Test ini menjaga supaya saran dan aksi selalu seize.
    """

    def _src(self):
        return GUI.read_text(encoding="utf-8")

    def test_output_dir_field_in_settings(self):
        assert "Folder Output:" in self._src(), (
            "tidak ada field 'Folder Output:' di Settings, tapi pesan error "
            "mengarahkan user untuk menggantinya di Settings"
        )

    def test_output_dir_is_persisted(self):
        assert '"output_dir": self.od_var.get().strip()' in self._src(), (
            "field ada tapi tidak disimpan ke config — Perubahan tidak akan bertahan"
        )

    def test_output_dir_has_browse_button(self):
        assert "def browse_output" in self._src()

    def test_output_dir_validated_on_change(self):
        """Folder yang tidak bisa ditulis harus ditolak saat dipilih."""
        src = self._src()
        assert "_check_output_writable" in src
        assert "check_output_dir" in src

    def test_fix_hint_points_at_a_real_field(self):
        """Saran di pesan harus cocok dengan UI yang benar-benar ada."""
        import clipper_firstrun as fr

        issues = fr.check_output_dir({"output_dir": str(
            Path.home() / "Videos" / "probe"
        )})
        if not issues:
            pytest.skip("Videos bisa ditulis di PC ini")
        hint = issues[0].fix_hint
        assert "Settings" in hint
        assert "Folder Output" in self._src()


# ==========================================================================
# Rantai: config -> check
# ==========================================================================
class TestOutputDirChain:
    def test_empty_config_falls_back_to_default(self):
        from clipper_paths import default_output_dir, output_dir_from_config

        assert output_dir_from_config({}) == default_output_dir()
        assert output_dir_from_config({"output_dir": ""}) == default_output_dir()

    def test_config_value_is_honoured(self, tmp_path):
        from clipper_paths import output_dir_from_config

        target = tmp_path / "keluaran"
        assert output_dir_from_config({"output_dir": str(target)}) == target

    def test_gate_accepts_user_chosen_folder(self, tmp_path):
        """Setelah user ganti folder, gate harus melepas."""
        target = tmp_path / "keluaran"
        res = g.gate_before_work({"output_dir": str(target)})
        codes = {i.code for i in res.issues}
        assert "output_dir_known_folder" not in codes
        assert "output_dir_not_writable" not in codes

    def test_writable_folder_passes_check(self, tmp_path):
        assert fr.check_output_dir({"output_dir": str(tmp_path)}) == []
