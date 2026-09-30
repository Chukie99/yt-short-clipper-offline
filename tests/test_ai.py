"""
Test untuk clipper_ai.py dan clipper_retry.py.

Yang diuji di sini adalah tempat di mana bug sebelumnya lolos tanpa terdeteksi:

  - Output AI dibungkus markdown / diawali penjelasan → harus tetap ter-parse
  - Field yang tidak dikirim AI → harus diisi default, tidak boleh KeyError
  - Timestamp rusak → harus jadi tidak-ada, tidak boleh meledak jauh dari sumber
  - Prompt dengan placeholder kosong → harus DITOLAK, bukan mengirim `{transcript}`
    ke model sehingga AI mengarang analisis dari nol
  - Retry: 401 tidak boleh dicoba ulang; 429 harus menghormati Retry-After
  - API key tidak boleh bocor ke pesan error
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from clipper_ai import (  # noqa: E402
    Segment, build_prompt, extract_json, format_timestamp, normalize_mood,
    parse_timestamp, segment_from_dict, segments_from_response,
    strip_control_chars, strip_fences,
)
from clipper_retry import (  # noqa: E402
    AIError, call_with_retry, compute_delay, is_retryable,
)


# ==========================================================================
# Ekstraksi JSON
# ==========================================================================
class TestExtractJson:
    def test_plain_json(self):
        assert extract_json('{"a": 1}') == {"a": 1}

    def test_json_in_markdown_fence(self):
        raw = 'Ini hasilnya:\n```json\n[{"start": "00:00:10"}]\n```\nSemoga membantu.'
        assert extract_json(raw) == [{"start": "00:00:10"}]

    def test_fence_without_language(self):
        raw = chr(96) * 3 + chr(10) + '[{"a": 1}]' + chr(10) + chr(96) * 3

        assert extract_json(raw) == [{"a": 1}]

    def test_prose_then_json(self):
        raw = 'Baik, berikut analisisnya:\n[{"title": "Rahasia"}]\n\nDeploy.'
        assert extract_json(raw) == [{"title": "Rahasia"}]

    def test_control_chars_removed(self):
        assert extract_json('[{"a": 1}]') == [{"a": 1}]
        assert extract_json('[{"a": 1}]') is not None

    def test_nested_braces_preserved(self):
        raw = '{"outer": {"inner": [1, 2]}}'
        assert extract_json(raw) == {"outer": {"inner": [1, 2]}}

    def test_brace_inside_string_not_confusing(self):
        raw = '{"title": " interwoven } stuff", "n": 1}'
        assert extract_json(raw)["title"] == " interwoven } stuff"

    def test_none_when_no_json(self):
        assert extract_json("Maaf, saya tidak bisa membantu itu.") is None
        assert extract_json("") is None
        assert extract_json(None) is None

    def test_unterminated_json_returns_none(self):
        assert extract_json('[{"a": 1') is None

    def test_strip_fences_helper(self):
        assert "```" not in strip_fences("```json\n{}\n```")

    def test_strip_control_keeps_newline_and_tab(self):
        # Newline dan tab valid di dalam JSON string; jangan sampai ikut hilang.
        assert "\n" in strip_control_chars("a\nb")
        assert "\t" in strip_control_chars("a\tb")
        assert "\x00" not in strip_control_chars("a\x00b")


# ==========================================================================
# Timestamp
# ==========================================================================
class TestTimestamp:
    def test_hms(self):
        assert parse_timestamp("00:01:30") == 90.0

    def test_ms(self):
        assert parse_timestamp("01:30") == 90.0

    def test_hours(self):
        assert parse_timestamp("02:00:00") == 7200.0

    def test_number_passthrough(self):
        assert parse_timestamp(83) == 83.0
        assert parse_timestamp(83.5) == 83.5

    @pytest.mark.parametrize("bad", [None, "", "abc", "start", "1m23s", "00:99:99", True, [1]])
    def test_unparseable_returns_none(self, bad):
        assert parse_timestamp(bad) is None

    def test_negative_rejected(self):
        assert parse_timestamp(-5) is None

    def test_format_roundtrip(self):
        assert format_timestamp(90) == "00:01:30"
        assert format_timestamp(0) == "00:00:00"

    def test_format_clamps_negative(self):
        assert format_timestamp(-10) == "00:00:00"


# ==========================================================================
# Mood
# ==========================================================================
class TestMood:
    def test_known_mood_kept(self):
        assert normalize_mood("tegang") == "tegang"
        assert normalize_mood("INSPIRASI") == "inspirasi"

    def test_unknown_mood_falls_back(self):
        # Mood menentukan file BGM; nilai asing akan membuat request yang pasti gagal.
        assert normalize_mood("d, cosmic") == "santai"
        assert normalize_mood("") == "santai"
        assert normalize_mood(None) == "santai"


# ==========================================================================
# Segment
# ==========================================================================
class TestSegmentFromDict:
    def test_full_dict(self):
        seg = segment_from_dict({
            "start": "00:00:10", "end": "00:00:40", "title": "Rahasia",
            "mood": "kocak", "viral_score": 9, "split_screen": True,
            "hashtags": ["#a", "#b"],
        })
        assert seg.start == 10.0
        assert seg.end == 40.0
        assert seg.duration == 30.0
        assert seg.mood == "kocak"
        assert seg.viral_score == 9
        assert seg.split_screen is True

    def test_missing_fields_use_defaults(self):
        """AI sering tidak mengirim semua field. Tidak boleh KeyError."""
        seg = segment_from_dict({"start": "00:00:05"})
        assert seg.start == 5.0
        assert seg.end == 15.0
        assert seg.title == ""
        assert seg.hashtags == []
        assert seg.mood == "santai"
        assert seg.duration == 10.0

    def test_empty_dict_is_safe(self):
        seg = segment_from_dict({})
        assert seg.start == 0.0
        assert seg.end == 10.0
        assert seg.duration == 10.0

    def test_non_dict_is_safe(self):
        # Dafail(list) harus jadi segmen default, bukan crash.
        for bad in ([1, 2], "string", None, 5):
            seg = segment_from_dict(bad)
            assert seg.duration > 0

    def test_end_before_start_is_corrected(self):
        """Rentang terbalik akan membuat ffmpeg gagal tanpa pesan jelas (AUDIT.md G3)."""
        seg = segment_from_dict({"start": "00:01:00", "end": "00:00:10"})
        assert seg.end > seg.start
        assert seg.duration > 0

    def test_equal_start_end_is_corrected(self):
        seg = segment_from_dict({"start": "00:00:10", "end": "00:00:10"})
        assert seg.duration > 0

    def test_unparseable_start_becomes_zero(self):
        seg = segment_from_dict({"start": "awal", "end": "00:00:30"})
        assert seg.start == 0.0
        assert seg.duration > 0

    def test_score_clamped(self):
        assert segment_from_dict({"viral_score": 99}).viral_score == 10
        assert segment_from_dict({"viral_score": -5}).viral_score == 1
        assert segment_from_dict({"viral_score": "abc"}).viral_score == 5

    def test_hashtags_from_comma_string(self):
        seg = segment_from_dict({"hashtags": "#a, #b, #c"})
        assert seg.hashtags == ["#a", "#b", "#c"]

    def test_title_alt_from_string(self):
        seg = segment_from_dict({"title_alt": "satu, dua"})
        assert seg.title_alt == ["satu", "dua"]

    def test_bool_from_string(self):
        assert segment_from_dict({"split_screen": "true"}).split_screen is True
        assert segment_from_dict({"split_screen": "no"}).split_screen is False

    def test_to_dict_roundtrip(self):
        original = segment_from_dict({"start": "00:00:10", "end": "00:00:40", "title": "X"})
        again = segment_from_dict(original.to_dict())
        assert again.start == original.start
        assert again.end == original.end
        assert again.title == original.title

    def test_to_dict_is_json_safe(self):
        import json

        seg = segment_from_dict({"start": 10, "end": 40, "hashtags": ["#a"]})
        json.dumps(seg.to_dict())  # harus tidak melempar


# ==========================================================================
# segments_from_response
# ==========================================================================
class TestSegmentsFromResponse:
    def test_multiple_segments(self):
        raw = '[{"start":"00:00:00","end":"00:00:30","title":"A"},' \
              '{"start":"00:01:00","end":"00:01:30","title":"B"}]'
        segs = segments_from_response(raw)
        assert len(segs) == 2
        assert [s.title for s in segs] == ["A", "B"]

    def test_single_dict_wrapped(self):
        segs = segments_from_response('{"start":"00:00:00","end":"00:00:30"}')
        assert len(segs) == 1

    def test_fenced_array(self):
        raw = '```json\n[{"start":"00:00:00","end":"00:00:30","title":"Z"}]\n```'
        assert len(segments_from_response(raw)) == 1

    def test_non_json_returns_empty_and_logs(self):
        messages = []
        segs = segments_from_response("Maaf, tidak bisa.", log_func=messages.append)
        assert segs == []
        assert any("JSON" in m for m in messages), "user harus diberi tahu, bukan diam"

    def test_skips_non_dict_items(self):
        raw = '[{"start":"00:00:00","end":"00:00:30"}, "junk", null, 5]'
        segs = segments_from_response(raw)
        assert len(segs) == 1

    def test_empty_array(self):
        assert segments_from_response("[]") == []

    def test_string_payload_returns_empty(self):
        assert segments_from_response('"just a string"') == []

    def test_none_input(self):
        assert segments_from_response(None) == []


# ==========================================================================
# Prompt
# ==========================================================================
class TestBuildPrompt:
    def test_fills_placeholder(self):
        assert build_prompt("Halo {nama}", nama="Budi") == "Halo Budi"

    def test_missing_placeholder_raises(self):
        """AUDIT.md G1: model yang menerima '{transcript}' mengarang dari nol."""
        with pytest.raises(ValueError) as exc:
            build_prompt("Analisis {transcript}")
        assert "transcript" in str(exc.value)

    def test_error_message_names_the_placeholder(self):
        with pytest.raises(ValueError) as exc:
            build_prompt("a {x} b {y}", x="1")
        assert "{y}" in str(exc.value)

    def test_extra_kwargs_ignored(self):
        assert build_prompt("Halo {nama}", nama="Budi", tidak_dipakai="x") == "Halo Budi"

    def test_no_placeholder_is_fine(self):
        assert build_prompt("Teks polos") == "Teks polos"

    def test_real_prompt_rejects_empty_analysis_call(self):
        """Prompt asli harus menolak panggilan yang tidak punya transkrip."""
        import clipper_core

        with pytest.raises(ValueError):
            build_prompt(clipper_core.GEMINI_PROMPT)


# ==========================================================================
# Klasifikasi error
# ==========================================================================
class Err(Exception):
    def __init__(self, message, status=None, response=None):
        super().__init__(message)
        self.status = status
        self.response = response


class Resp:
    def __init__(self, status_code, headers=None):
        self.status_code = status_code
        self.headers = headers or {}


class TestIsRetryable:
    @pytest.mark.parametrize("status", [429, 500, 502, 503, 504, 408])
    def test_retryable(self, status):
        assert is_retryable(Err("x", status=status)) is True

    @pytest.mark.parametrize("status", [400, 401, 403, 404, 413, 422])
    def test_not_retryable(self, status):
        # 401 = API key salah. Mencoba lagi hanya membuang kuota.
        assert is_retryable(Err("x", status=status)) is False

    def test_no_status_is_retryable(self):
        # Timeout dan connection reset tidak punya status HTTP.
        assert is_retryable(Err("connection reset")) is True

    def test_status_from_response_attribute(self):
        assert is_retryable(Err("x", response=Resp(503))) is True
        assert is_retryable(Err("x", response=Resp(401))) is False

    def test_status_found_in_message(self):
        assert is_retryable(Err("429 RESOURCE_EXHAUSTED")) is True


# ==========================================================================
# Backoff
# ==========================================================================
class TestComputeDelay:
    def test_grows_exponentially(self):
        assert compute_delay(0, jitter=0) == 2.0
        assert compute_delay(1, jitter=0) == 4.0
        assert compute_delay(2, jitter=0) == 8.0

    def test_capped(self):
        assert compute_delay(20, cap=60, jitter=0) == 60

    def test_jitter_stays_in_bounds(self):
        # attempt=3 -> delay 2*2^3 = 16s, jitter 30% -> 16 +/- 4.8
        for _ in range(50):
            d = compute_delay(3, base=2.0, cap=60, jitter=0.3)
            assert 11.2 <= d <= 20.8

    def test_never_negative(self):
        for _ in range(50):
            assert compute_delay(0, jitter=0.9) >= 0.0


# ==========================================================================
# call_with_retry
# ==========================================================================
class TestCallWithRetry:
    def test_succeeds_first_try(self):
        calls = []
        out = call_with_retry(lambda: calls.append(1) or "ok", sleep=lambda _: None)
        assert out == "ok"
        assert len(calls) == 1

    def test_retries_on_503_then_succeeds(self):
        state = {"n": 0}

        def flaky():
            state["n"] += 1
            if state["n"] < 3:
                raise Err("busy", status=503)
            return "ok"

        slept = []
        assert call_with_retry(flaky, sleep=slept.append) == "ok"
        assert state["n"] == 3
        assert len(slept) == 2

    def test_fatal_error_not_retried(self):
        calls = []

        def always_401():
            calls.append(1)
            raise Err("unauthorized", status=401)

        with pytest.raises(AIError) as exc:
            call_with_retry(always_401, sleep=lambda _: None)
        assert len(calls) == 1, "401 tidak boleh dicoba ulang"
        assert "API key" in str(exc.value)

    def test_exhausted_raises_with_attempt_count(self):
        def always_503():
            raise Err("boom", status=503)

        with pytest.raises(AIError) as exc:
            call_with_retry(always_503, attempts=3, sleep=lambda _: None)
        assert exc.value.attempts == 3
        assert "3 percobaan" in str(exc.value)

    def test_retry_after_header_respected(self):
        from clipper_retry import retry_after_seconds

        exc = Err("rate", status=429, response=Resp(429, {"Retry-After": "7"}))
        assert retry_after_seconds(exc) == 7.0

    def test_retry_after_capped(self):
        slept = []

        def always_429():
            raise Err("rate", status=429, response=Resp(429, {"Retry-After": "9999"}))

        with pytest.raises(AIError):
            call_with_retry(always_429, attempts=2, cap=5, sleep=slept.append)
        assert all(d <= 5 for d in slept)

    def test_no_retry_when_cap_is_zero(self):
        calls = []

        def flaky():
            calls.append(1)
            raise Err("busy", status=503)

        with pytest.raises(AIError):
            call_with_retry(flaky, attempts=1, sleep=lambda _: None)
        assert len(calls) == 1

    def test_log_func_notified_per_retry(self):
        msgs = []

        def always_503():
            raise Err("busy", status=503)

        with pytest.raises(AIError):
            call_with_retry(always_503, attempts=3, sleep=lambda _: None, log_func=msgs.append)
        assert len(msgs) == 2

    def test_keyboard_interrupt_not_swallowed(self):
        def interrupted():
            raise KeyboardInterrupt

        with pytest.raises(KeyboardInterrupt):
            call_with_retry(interrupted, sleep=lambda _: None)

    def test_error_message_has_no_api_key(self):
        """Pesan error tidak boleh membocorkan key yang ada di URL."""
        import clipper_secrets

        secret = "AIzaSyLEAKINERROR12345678"
        clipper_secrets.register_secret(secret)
        try:
            def failing():
                raise Err(f"401 Client Error for url: https://x?key={secret}", status=401)

            with pytest.raises(AIError) as exc:
                call_with_retry(failing, sleep=lambda _: None)
            assert secret not in str(exc.value)
        finally:
            clipper_secrets.reset_secret_registry()


# ==========================================================================
# Segment dataclass
# ==========================================================================
class TestSegment:
    def test_duration_property(self):
        assert Segment(start=10, end=40, title="x").duration == 30.0

    def test_negative_duration_clamped(self):
        assert Segment(start=40, end=10, title="x").duration == 0.0

    def test_defaults_are_independent(self):
        """List default harus per-instance, bukan shared (bug klasik dataclass)."""
        a = Segment(start=0, end=1, title="a")
        b = Segment(start=0, end=1, title="b")
        a.hashtags.append("#x")
        assert b.hashtags == [], "list default harus per-instance"
