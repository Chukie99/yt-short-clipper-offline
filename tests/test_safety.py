"""
Tests for clipper_run.py and clipper_paths.py.

These are the two modules that enforce the two structural guarantees Phase 1 rests on:
  1. nothing is ever executed through a shell
  2. nothing is ever written into the application directory

Most tests here use real subprocesses (python -c) rather than mocks — a mock cannot
prove that shell metacharacters in an argument do not execute.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from clipper_run import (
    CommandError,
    quote_for_filtergraph,
    run_command,
    run_streaming,
    safe_filename,
)
import clipper_paths


# ---------------------------------------------------------------------------
# run_command: never uses a shell
# ---------------------------------------------------------------------------
class TestNoShell:
    def test_rejects_string(self):
        with pytest.raises(TypeError, match="list"):
            run_command("echo hello")

    def test_rejects_bytes(self):
        with pytest.raises(TypeError, match="list"):
            run_command(b"echo hello")

    def test_rejects_empty(self):
        with pytest.raises(ValueError):
            run_command([])

    @pytest.mark.parametrize(
        "payload",
        [
            "http://x.com/a.mp4; echo PWNED",
            "http://x.com/a.mp4 && echo PWNED",
            "http://x.com/a.mp4 | echo PWNED",
            "$(echo PWNED)",
            "`echo PWNED`",
            "http://x.com/a.mp4\n echo PWNED",
        ],
    )
    def test_metacharacters_in_argv_are_inert(self, payload, tmp_path):
        """A shell-metacharacter-laden argument must arrive at the program verbatim
        and must not spawn a second process."""
        canary = tmp_path / "PWNED"
        out = tmp_path / "arg.txt"
        script = (
            "import sys,pathlib;"
            f"pathlib.Path(r'{out}').write_text(sys.argv[1], encoding='utf-8')"
        )
        run_command([sys.executable, "-c", script, payload], timeout=30)
        assert out.read_text(encoding="utf-8") == payload
        assert not canary.exists()

    def test_arg_with_spaces_is_one_argv(self):
        out = Path(tempfile.gettempdir()) / "clipper_argv_probe.txt"
        script = "import sys;print(len(sys.argv)-1)"
        r = run_command([sys.executable, "-c", script, "a b c", "d\te"], timeout=30)
        assert r.stdout.strip() == "2"

    def test_no_shell_kwarg_reaches_popen(self, monkeypatch):
        """Structural check: even if a caller tried, shell=True is impossible."""
        seen = {}
        real_popen = subprocess.Popen

        def spy(*args, **kwargs):
            seen.update(kwargs)
            return real_popen(*args, **kwargs)

        monkeypatch.setattr(subprocess, "Popen", spy)
        run_command([sys.executable, "-c", "pass"], timeout=30)
        assert seen.get("shell") is False


# ---------------------------------------------------------------------------
# run_command: timeouts, exit codes, error quality
# ---------------------------------------------------------------------------
class TestRunCommand:
    def test_returns_stdout(self):
        r = run_command([sys.executable, "-c", "print('halo')"], timeout=30)
        assert r.returncode == 0
        assert "halo" in r.stdout

    def test_nonzero_exit_raises_with_detail(self):
        with pytest.raises(CommandError) as exc:
            run_command([sys.executable, "-c", "import sys;print('boom');sys.exit(3)"], timeout=30)
        assert "boom" in str(exc.value)

    def test_check_false_returns_result(self):
        r = run_command([sys.executable, "-c", "import sys;sys.exit(3)"], check=False, timeout=30)
        assert r.returncode == 3

    def test_timeout_kills_and_reports(self):
        with pytest.raises(CommandError, match="batas waktu"):
            run_command([sys.executable, "-c", "import time;time.sleep(30)"], timeout=1)

    def test_missing_executable_message_is_actionable(self):
        with pytest.raises(CommandError, match="tidak ditemukan"):
            run_command(["clipper_definitely_not_a_real_binary", "--version"])

    def test_log_func_receives_filtered_lines(self):
        seen = []
        run_command(
            [sys.executable, "-c", "print('frame=10 fps=25');print('boring line')"],
            log_func=seen.append,
            timeout=30,
        )
        joined = "\n".join(seen)
        assert "fps=25" in joined
        assert "boring line" not in joined

    def test_input_bytes(self):
        r = run_command(
            [sys.executable, "-c", "import sys;sys.stdout.write(sys.stdin.read().upper())"],
            input_bytes=b"abc",
            timeout=30,
        )
        assert r.stdout.strip() == "ABC"


# ---------------------------------------------------------------------------
# run_streaming
# ---------------------------------------------------------------------------
class TestRunStreaming:
    def test_rejects_string(self):
        with pytest.raises(TypeError):
            run_streaming("ffmpeg -i x")

    def test_stdin_roundtrip(self):
        p = run_streaming([sys.executable, "-c", "import sys;d=sys.stdin.buffer.read();sys.stderr.write(str(len(d)))"])
        p.stdin.write(b"x" * 100)
        p.stdin.close()
        err = p.stderr.read()
        p.wait(timeout=30)
        assert err.decode() == "100"

    def test_missing_binary_raises_command_error(self):
        with pytest.raises(CommandError):
            run_streaming(["clipper_definitely_not_a_real_binary"])


# ---------------------------------------------------------------------------
# safe_filename
# ---------------------------------------------------------------------------
class TestSafeFilename:
    @pytest.mark.parametrize("bad", ['<', '>', ':', '"', '/', '\\', '|', '?', '*'])
    def test_illegal_chars_replaced(self, bad):
        assert bad not in safe_filename(f"a{bad}c")

    def test_path_traversal_neutralised(self):
        """A title from the AI must never escape the output directory."""
        for payload in ["../../etc/passwd", "..\\..\\windows\\system32", "a/b/../../c"]:
            out = safe_filename(payload)
            assert "/" not in out and "\\" not in out
            assert ".." not in out or out.startswith("_")

    def test_reserved_device_names_prefixed(self):
        for name in ["CON", "prn", "AUX", "nul", "COM1", "LPT9"]:
            assert safe_filename(name).upper().startswith("_")

    def test_empty_uses_fallback(self):
        assert safe_filename("", fallback="short_abc") == "short_abc"
        assert safe_filename("   ", fallback="short_abc") == "short_abc"
        assert safe_filename("...", fallback="short_abc") == "short_abc"

    def test_truncates_and_never_trailing_dot_or_space(self):
        long = "a" * 300
        out = safe_filename(long, max_len=50)
        assert len(out) <= 50
        assert not out.endswith(".") and not out.endswith(" ")

    def test_keeps_normal_title_readable(self):
        assert safe_filename("Momen Viral 2026!") == "Momen Viral 2026!"


# ---------------------------------------------------------------------------
# quote_for_filtergraph
# ---------------------------------------------------------------------------
class TestQuoteForFiltergraph:
    def test_strips_fmpeg_separators(self):
        out = quote_for_filtergraph("Judul [Test]; drawtext=x,evil")
        assert ";" not in out and "," not in out and "[" not in out and "]" not in out

    def test_strips_backslash_and_quotes(self):
        payload = "".join(chr(c) for c in (97, 92, 98, 39, 99, 34, 100, 0, 101))
        out = quote_for_filtergraph(payload)
        for ch in (chr(92), chr(39), chr(34), chr(0)):
            assert ch not in out

    def test_keeps_readable_text(self):
        assert quote_for_filtergraph("3 Trik Viral 2026") == "3 Trik Viral 2026"

    def test_strips_backtick_and_bracket(self):
        out = quote_for_filtergraph("a" + chr(96) + "b" + chr(91) + chr(93))
        for ch in (chr(96), chr(91), chr(93)):
            assert ch not in out

    def test_handles_none(self):
        assert quote_for_filtergraph(None) == ""


# ---------------------------------------------------------------------------
# clipper_paths
# ---------------------------------------------------------------------------
class TestPaths:
    def test_resource_and_data_are_different(self):
        assert clipper_paths.RESOURCE_DIR != clipper_paths.DATA_DIR

    def test_data_dir_env_override(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLIPPER_DATA_DIR", str(tmp_path / "appdata"))
        assert clipper_paths.data_dir() == (tmp_path / "appdata").resolve()

    def test_ensure_dirs_is_idempotent(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLIPPER_DATA_DIR", str(tmp_path / "d"))
        d = clipper_paths.data_dir()
        clipper_paths.ensure_dirs()
        clipper_paths.ensure_dirs()
        for sub in ("temp", "logs", "bgm"):
            assert (d / sub).is_dir()
        assert (d / "config.json").parent == d

    def test_default_output_is_under_videos(self):
        assert clipper_paths.default_output_dir() == Path.home() / "Videos" / clipper_paths.APP_DIR_NAME

    def test_output_from_config_empty_falls_back(self):
        assert clipper_paths.output_dir_from_config({}) == clipper_paths.default_output_dir()
        assert clipper_paths.output_dir_from_config({"output_dir": "  "}) == clipper_paths.default_output_dir()

    def test_output_from_config_honours_user_choice(self):
        assert clipper_paths.output_dir_from_config({"output_dir": "D:/Klip"}) == Path("D:/Klip")

    def test_resource_file_stays_in_resource_dir(self):
        p = clipper_paths.resource_file("fonts", "Montserrat-Bold.ttf")
        assert clipper_paths.RESOURCE_DIR in p.parents

    def test_app_data_summary_keys(self):
        s = clipper_paths.app_data_summary()
        for k in ("app", "version", "resource_dir", "data_dir", "default_output_dir", "python"):
            assert k in s


# ---------------------------------------------------------------------------
# Config migration
# ---------------------------------------------------------------------------
class TestMigration:
    """Migrasi config v1 -> v2.

    Semua test di sini memakai CLIPPER_DATA_DIR terisolasi. Assertion sengaja
    memakai accessor (config_file()) BUKAN snapshot clipper_paths.CONFIG_FILE:
    importing clipper_core di sesi test yang sama bisa saja membuat config nyata
    di %APPDATA%, dan constant snapshot akan menunjuk ke sana, bukan ke tmp_path.
    """

    @pytest.fixture(autouse=True)
    def isolated_data_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLIPPER_DATA_DIR", str(tmp_path / "data"))

    def test_migrates_legacy_config(self):
        legacy = clipper_paths.RESOURCE_DIR / "config.json"
        if legacy.exists():
            pytest.skip("repo punya config.json asli; tidak boleh ditimpa test")
        legacy.write_text(
            json.dumps({"gemini_api_key": "old-key", "template": "bold"}), encoding="utf-8"
        )
        try:
            info = clipper_paths.migrate_legacy_config()
            dest = clipper_paths.config_file()
            assert info.get("migrated_from") == str(legacy)
            migrated = json.loads(dest.read_text(encoding="utf-8"))
            assert migrated["gemini_api_key"] == "old-key"
            assert migrated["template"] == "bold"
            assert migrated["config_schema_version"] == 2
        finally:
            legacy.unlink()

    def test_never_overwrites_existing_config(self):
        clipper_paths.ensure_dirs()
        dest = clipper_paths.config_file()
        dest.write_text(json.dumps({"template": "story"}), encoding="utf-8")
        clipper_paths.migrate_legacy_config()
        assert json.loads(dest.read_text(encoding="utf-8"))["template"] == "story"

    def test_corrupt_legacy_config_does_not_crash(self):
        """Config lama rusak harus diabaikan diam-diam, tanpa crash dan tanpa
        menulis file config yang korup ke tempat baru."""
        legacy = clipper_paths.RESOURCE_DIR / "config.json"
        if legacy.exists():
            pytest.skip("repo punya config.json asli; tidak boleh ditimpa test")
        legacy.write_text("{not json", encoding="utf-8")
        try:
            assert clipper_paths.migrate_legacy_config() == {}
            assert not clipper_paths.config_file().exists()
        finally:
            legacy.unlink()

    def test_corrupt_legacy_non_dict_ignored(self):
        legacy = clipper_paths.RESOURCE_DIR / "config.json"
        if legacy.exists():
            pytest.skip("repo punya config.json asli; tidak boleh ditimpa test")
        legacy.write_text("[1,2,3]", encoding="utf-8")
        try:
            assert clipper_paths.migrate_legacy_config() == {}
            assert not clipper_paths.config_file().exists()
        finally:
            legacy.unlink()

    def test_queue_state_copy_is_not_overwriting(self):
        clipper_paths.ensure_dirs()
        qs = clipper_paths.queue_state_file()
        qs.write_text('{"segments":[]}', encoding="utf-8")
        assert clipper_paths.copy_legacy_queue_state() is False
        assert qs.read_text(encoding="utf-8") == '{"segments":[]}'
