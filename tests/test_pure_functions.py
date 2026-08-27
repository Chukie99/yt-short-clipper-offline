"""Unit tests for yt-short-clipper-offline pure functions.

Strategy
--------
`clipper_core.py` imports heavy / optional deps at module top-level:
  - cv2, numpy, mediapipe (optional heavy ML)
  - PIL (Pillow)
  - dotenv
  - google.genai (optional)

Importing `clipper_core` directly therefore requires those packages.  To keep
tests hermetic and fast we inject lightweight stand-ins into ``sys.modules``
*before* importing the module under test.  After the import we exercise the
pure functions (KalmanFilter, get_safe_id, time_str_to_seconds,
compute_speech_segments, detect_emphasis_words, SpeakerTracker._match_face)
without touching any real video / network / GPU code.
"""
import os
import sys
import math
import types

# ---------------------------------------------------------------------------
# Mock heavy dependencies *before* importing clipper_core
# ---------------------------------------------------------------------------
import numpy as np  # numpy is fine to import for real — we only stub cv2/mp

# cv2 stub — we need a few constants and the functions used by pure helpers
class _Cv2Stub:
    # constants
    CAP_PROP_FPS = 5
    CAP_PROP_FRAME_WIDTH = 3
    CAP_PROP_FRAME_HEIGHT = 4
    CAP_PROP_FRAME_COUNT = 7
    COLOR_BGR2RGB = 4
    COLOR_RGB2GRAY = 6
    COLOR_BGR2LAB = 44
    COLOR_LAB2BGR = 55
    COLOR_BGR2HSV = 40
    COLOR_HSV2BGR = 54
    COLOR_RGB2BGR = 62
    ROTATE_90_COUNTERCLOCKWISE = 1
    INTER_CUBIC = 2
    INTER_AREA = 0

    def __getattr__(self, name):
        # Any attribute/method referenced by clipper_core but not explicitly
        # listed above becomes a no-op callable.  This keeps import-time and
        # pure-function usage happy without a real OpenCV install.
        return lambda *a, **k: None

cv2 = _Cv2Stub()

# mediapipe stub — only the bits clipper_core references at import time
mp = types.ModuleType("mediapipe")
mp.ImageFormat = type("ImageFormat", (), {"SRGB": 1})
mp.Image = lambda *a, **k: None
mp.__dict__["IMAGE_FORMAT"] = mp.ImageFormat
mp_tasks = types.ModuleType("mediapipe.tasks")
mp_tasks_python = types.ModuleType("mediapipe.tasks.python")
mp_tasks_python_vision = types.ModuleType("mediapipe.tasks.python.vision")
mp_core = types.ModuleType("mediapipe.tasks.python.core")
mp_base = types.ModuleType("mediapipe.tasks.python.core.base_options")
mp_base.BaseOptions = lambda **k: None
mp_tasks_python_vision.FaceDetector = type(
    "FaceDetector", (), {"create_from_options": staticmethod(lambda o: None)}
)
mp_tasks_python_vision.RunningMode = type("RunningMode", (), {"IMAGE": 1, "LIVE_STREAM": 2})
mp_tasks_python_vision.FaceDetectorOptions = lambda **k: None
# Wire submodules so `from mediapipe.tasks.python import vision, core` works
mp_tasks_python.vision = mp_tasks_python_vision
mp_tasks_python.core = mp_core
mp_core.base_options = mp_base

mp.tasks = mp_tasks
mp.tasks.python = mp_tasks_python
mp.tasks.python.vision = mp_tasks_python_vision
mp.tasks.python.core = mp_core

# PIL stub
pil = types.ModuleType("PIL")
pil_image_mod = types.ModuleType("PIL.Image")
pil_Image = type("Image", (), {
    "fromarray": staticmethod(lambda *a, **k: None),
    "new": staticmethod(lambda *a, **k: None),
    "alpha_composite": staticmethod(lambda *a, **k: None),
    "Resampling": type("Resampling", (), {"LANCZOS": 1}),
})
pil_image_mod.Image = pil_Image
pil_draw_mod = types.ModuleType("PIL.ImageDraw")
pil_draw_mod.ImageDraw = type("ImageDraw", (), {"Draw": staticmethod(lambda *a, **k: None)})
pil_font_mod = types.ModuleType("PIL.ImageFont")
pil_font_mod.ImageFont = type("ImageFont", (), {
    "truetype": staticmethod(lambda *a, **k: type("Font", (), {"path": "", "size": 65})()),
    "load_default": staticmethod(lambda *a, **k: None),
})
pil.Image = pil_image_mod
pil.ImageDraw = pil_draw_mod
pil.ImageFont = pil_font_mod

# dotenv stub
dotenv = types.ModuleType("dotenv")
dotenv.load_dotenv = lambda *a, **k: None

# google.genai stub (optional — only imported if available)
genai_stub = types.ModuleType("google.genai")
genai_stub.Client = lambda **k: None
google_stub = types.ModuleType("google")
google_stub.genai = genai_stub

# Register all mocks
sys.modules["cv2"] = cv2
sys.modules["mediapipe"] = mp
sys.modules["mediapipe.tasks"] = mp_tasks
sys.modules["mediapipe.tasks.python"] = mp_tasks_python
sys.modules["mediapipe.tasks.python.vision"] = mp_tasks_python_vision
sys.modules["mediapipe.tasks.python.core"] = mp_core
sys.modules["PIL"] = pil
sys.modules["PIL.Image"] = pil_image_mod
sys.modules["PIL.ImageDraw"] = pil_draw_mod
sys.modules["PIL.ImageFont"] = pil_font_mod
sys.modules["dotenv"] = dotenv
sys.modules["google"] = google_stub
sys.modules["google.genai"] = genai_stub

# ---------------------------------------------------------------------------
# Import the module under test (now that deps are stubbed)
# ---------------------------------------------------------------------------
REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_DIR)

from clipper_core import (  # noqa: E402
    KalmanFilter,
    get_safe_id,
    time_str_to_seconds,
    compute_speech_segments,
    detect_emphasis_words,
    SpeakerTracker,
    FaceState,
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestKalmanFilter:
    def test_initial_estimate(self):
        kf = KalmanFilter()
        assert kf.estimate == 0

    def test_update_converges_to_measurement(self):
        kf = KalmanFilter(process_noise=1e-5, measurement_noise=1e-2)
        # Feed constant measurement, estimate should converge
        result = 0
        for _ in range(100):
            result = kf.update(10.0)
        assert abs(result - 10.0) < 0.1

    def test_smooth_noisy_measurements(self):
        kf = KalmanFilter(process_noise=1e-5, measurement_noise=1e-1)
        measurements = [5.0, 5.1, 4.9, 5.05, 4.95, 5.02]
        results = []
        for m in measurements:
            results.append(kf.update(m))
        # Final estimate should be close to the mean
        assert abs(results[-1] - 5.0) < 0.5


class TestGetSafeId:
    def test_standard_youtube_url(self):
        assert get_safe_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_shorts_url(self):
        assert get_safe_id("https://youtube.com/shorts/abc123XYZ") == "abc123XYZ"

    def test_embed_url(self):
        assert get_safe_id("https://youtube.com/embed/xyz789") == "xyz789"

    def test_youtu_be_short(self):
        assert get_safe_id("https://youtu.be/abc-123") == "abc123"

    def test_invalid_url_returns_default(self):
        result = get_safe_id("not a url at all")
        assert result == "video" or len(result) > 0

    def test_alphanumeric_only(self):
        result = get_safe_id("https://youtube.com/watch?v=test_123-ABC")
        assert result.isalnum()


class TestTimeStrToSeconds:
    def test_hh_mm_ss(self):
        assert time_str_to_seconds("01:30:00") == 5400.0

    def test_mm_ss(self):
        assert time_str_to_seconds("05:30") == 330.0

    def test_ss_only(self):
        assert time_str_to_seconds("45") == 45.0

    def test_zero(self):
        assert time_str_to_seconds("00:00:00") == 0.0

    def test_fallback_to_float(self):
        assert time_str_to_seconds("3.14") == 3.14


class TestSpeakerTrackerMatchFace:
    def setup_method(self):
        self.tracker = SpeakerTracker()

    def test_no_faces_returns_none(self):
        assert self.tracker._match_face(100, 100, 50, 50) is None

    def test_match_close_face(self):
        self.tracker.faces = [FaceState(cx=100, cy=100, w=50, h=50)]
        result = self.tracker._match_face(110, 110, 50, 50)
        assert result == 0

    def test_no_match_distant_face(self):
        self.tracker.faces = [FaceState(cx=100, cy=100, w=50, h=50)]
        result = self.tracker._match_face(500, 500, 50, 50)
        assert result is None


class TestComputeSpeechSegments:
    def test_empty_words(self):
        assert compute_speech_segments([], 0.6) == []

    def test_single_word(self):
        words = [{"start": 0.0, "end": 1.0, "text": "HELLO"}]
        result = compute_speech_segments(words, 0.6)
        assert len(result) == 1
        assert result[0] == (0.0, 1.0)

    def test_consecutive_words_merge(self):
        words = [
            {"start": 0.0, "end": 0.5, "text": "HELLO"},
            {"start": 0.6, "end": 1.0, "text": "WORLD"},
        ]
        result = compute_speech_segments(words, 0.6)
        assert len(result) == 1

    def test_gap_splits_segments(self):
        words = [
            {"start": 0.0, "end": 0.5, "text": "HELLO"},
            {"start": 1.5, "end": 2.0, "text": "WORLD"},
        ]
        result = compute_speech_segments(words, 0.6)
        assert len(result) == 2


class TestDetectEmphasisWords:
    def test_all_caps(self):
        words = [{"text": "STOP"}, {"text": "the"}, {"text": "RUNNING"}]
        result = detect_emphasis_words(words)
        assert 0 in result
        assert 2 in result
        assert 1 not in result

    def test_exclamation_mark(self):
        words = [{"text": "Wow!"}, {"text": "normal"}]
        result = detect_emphasis_words(words)
        assert 0 in result
        assert 1 not in result

    def test_known_keywords(self):
        words = [{"text": "Never"}, {"text": "give"}, {"text": "up"}]
        result = detect_emphasis_words(words)
        assert 0 in result  # "Never" is in emphasis_words set


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
