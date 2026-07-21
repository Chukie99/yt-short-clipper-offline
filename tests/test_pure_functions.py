"""Unit tests for yt-short-clipper-offline pure functions."""
import sys
import os
import math
import pytest

# Add parent dir to path so we can import the main module
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# We need to mock some imports that require GUI / hardware
import types
mock_cv2 = types.ModuleType("cv2")
mock_cv2.CAP_PROP_FPS = 5
mock_cv2.CAP_PROP_FRAME_WIDTH = 3
mock_cv2.CAP_PROP_FRAME_HEIGHT = 4
mock_cv2.CAP_PROP_FRAME_COUNT = 7
mock_cv2.COLOR_BGR2RGB = 4
mock_cv2.COLOR_RGB2GRAY = 6
mock_cv2.COLOR_BGR2LAB = 44
mock_cv2.COLOR_LAB2BGR = 55
mock_cv2.COLOR_BGR2HSV = 40
mock_cv2.COLOR_HSV2BGR = 54
mock_cv2.ROTATE_90_COUNTERCLOCKWISE = 1
mock_cv2.INTER_CUBIC = 2
mock_cv2.INTER_AREA = 0
mock_cv2.imread = lambda *a, **k: None
mock_cv2.VideoCapture = lambda *a, **k: None
mock_cv2.resize = lambda *a, **k: None
mock_cv2.cvtColor = lambda *a, **k: None
mock_cv2.calcOpticalFlowFarneback = lambda *a, **k: None
mock_cv2.cartToPolar = lambda *a, **k: (None, None)
mock_cv2.GaussianBlur = lambda *a, **k: None
mock_cv2.addWeighted = lambda *a, **k: None
mock_cv2.line = lambda *a, **k: None
mock_cv2.imwrite = lambda *a, **k: None
sys.modules["cv2"] = mock_cv2

mock_numpy = types.ModuleType("numpy")
mock_numpy.ndarray = type("ndarray", (), {})
mock_numpy.ogrid = None
mock_numpy.hypot = math.hypot
mock_numpy.array = lambda *a, **k: None
mock_numpy.mean = lambda *a, **k: 0
mock_numpy.clip = lambda x, lo, hi: max(lo, min(hi, x))
mock_numpy.sqrt = math.sqrt
mock_numpy.pi = math.pi
mock_numpy.sin = math.sin
sys.modules["numpy"] = mock_numpy

mock_mediapipe = types.ModuleType("mediapipe")
sys.modules["mediapipe"] = mock_mediapipe
sys.modules["mediapipe.tasks"] = types.ModuleType("mediapipe.tasks")
sys.modules["mediapipe.tasks.python"] = types.ModuleType("mediapipe.tasks.python")
sys.modules["mediapipe.tasks.python.vision"] = types.ModuleType("mediapipe.tasks.python.vision")
sys.modules["mediapipe.tasks.python.core"] = types.ModuleType("mediapipe.tasks.python.core")
sys.modules["mediapipe.tasks.python.vision"].FaceDetector = type("FaceDetector", (), {"create_from_options": staticmethod(lambda o: None)})
sys.modules["mediapipe.tasks.python.vision"].RunningMode = type("RunningMode", (), {"IMAGE": 1})
sys.modules["mediapipe.tasks.python.vision"].FaceDetectorOptions = lambda **k: None
sys.modules["mediapipe.tasks.python.core"].base_options = types.ModuleType("base_options")
sys.modules["mediapipe.tasks.python.core"].base_options.BaseOptions = lambda **k: None

mock_ctk = types.ModuleType("customtkinter")
mock_ctk.CTk = type("CTk", (), {"__init__": lambda *a, **k: None})
mock_ctk.CTkToplevel = type("CTkToplevel", (), {"__init__": lambda *a, **k: None})
mock_ctk.CTkFrame = type("CTkFrame", (), {"__init__": lambda *a, **k: None})
mock_ctk.CTkLabel = type("CTkLabel", (), {"__init__": lambda *a, **k: None})
mock_ctk.CTkEntry = type("CTkEntry", (), {"__init__": lambda *a, **k: None})
mock_ctk.CTkButton = type("CTkButton", (), {"__init__": lambda *a, **k: None})
mock_ctk.CTkComboBox = type("CTkComboBox", (), {"__init__": lambda *a, **k: None})
mock_ctk.CTkCheckBox = type("CTkCheckBox", (), {"__init__": lambda *a, **k: None})
mock_ctk.CTkSlider = type("CTkSlider", (), {"__init__": lambda *a, **k: None})
mock_ctk.CTkSegmentedButton = type("CTkSegmentedButton", (), {"__init__": lambda *a, **k: None})
mock_ctk.CTkTextbox = type("CTkTextbox", (), {"__init__": lambda *a, **k: None})
mock_ctk.CTkScrollableFrame = type("CTkScrollableFrame", (), {"__init__": lambda *a, **k: None})
mock_ctk.CTkProgressBar = type("CTkProgressBar", (), {"__init__": lambda *a, **k: None})
mock_ctk.StringVar = type("StringVar", (), {"__init__": lambda *a, **k: None, "get": lambda s: ""})
mock_ctk.BooleanVar = type("BooleanVar", (), {"__init__": lambda *a, **k: None, "get": lambda s: False})
mock_ctk.DoubleVar = type("DoubleVar", (), {"__init__": lambda *a, **k: None, "get": lambda s: 0.0})
mock_ctk.set_appearance_mode = lambda *a: None
mock_ctk.set_default_color_theme = lambda *a: None
sys.modules["customtkinter"] = mock_ctk

# Now import the actual functions we want to test
# We'll import just the function definitions we need, bypassing GUI init
import importlib
import types as _types

# Read the source file and extract just the functions we need
source_path = os.path.join(os.path.dirname(__file__), "..", "clipper_gui_modern.py")
with open(source_path, "r", encoding="utf-8") as f:
    source_code = f.read()

# Create a module to hold extracted functions
test_module = _types.ModuleType("test_target")
test_module.__dict__["__builtins__"] = __builtins__

# Execute just the function definitions we need
# We'll use exec with a minimal namespace
exec_ns = {"__builtins__": __builtins__, "math": math, "re": __import__("re"), "os": os, "sys": sys}
# Add mock objects
exec_ns["cv2"] = mock_cv2
exec_ns["np"] = mock_numpy
exec_ns["mp"] = mock_mediapipe
exec_ns["ctk"] = mock_ctk
exec_ns["logging"] = __import__("logging")

# Extract function definitions from source
import re as _re

# KalmanFilter class
kf_match = _re.search(r"class KalmanFilter:(.+?)(?=\n#|\nclass |\ndef )", source_code, _re.DOTALL)
if kf_match:
    exec(kf_match.group(0), exec_ns)

# get_safe_id function
gsid_match = _re.search(r"def get_safe_id\((.+?)(?=\ndef )", source_code, _re.DOTALL)
if gsid_match:
    exec(gsid_match.group(0), exec_ns)

# time_str_to_seconds function
tss_match = _re.search(r"def time_str_to_seconds\((.+?)(?=\ndef )", source_code, _re.DOTALL)
if tss_match:
    exec(tss_match.group(0), exec_ns)

# SpeakerTracker class (just _match_face)
st_match = _re.search(r"class SpeakerTracker:(.+?)(?=\nclass |\Z)", source_code, _re.DOTALL)
if st_match:
    exec(st_match.group(0), exec_ns)

# compute_speech_segments
css_match = _re.search(r"def compute_speech_segments\((.+?)(?=\ndef )", source_code, _re.DOTALL)
if css_match:
    exec(css_match.group(0), exec_ns)

# detect_emphasis_words
dew_match = _re.search(r"def detect_emphasis_words\((.+?)(?=\ndef )", source_code, _re.DOTALL)
if dew_match:
    exec(dew_match.group(0), exec_ns)


class TestKalmanFilter:
    def test_initial_estimate(self):
        kf = exec_ns["KalmanFilter"]()
        assert kf.estimate == 0

    def test_update_converges_to_measurement(self):
        kf = exec_ns["KalmanFilter"](process_noise=1e-5, measurement_noise=1e-2)
        # Feed constant measurement, estimate should converge
        for _ in range(100):
            result = kf.update(10.0)
        assert abs(result - 10.0) < 0.1

    def test_smooth_noisy_measurements(self):
        kf = exec_ns["KalmanFilter"](process_noise=1e-5, measurement_noise=1e-1)
        measurements = [5.0, 5.1, 4.9, 5.05, 4.95, 5.02]
        results = []
        for m in measurements:
            results.append(kf.update(m))
        # Final estimate should be close to the mean
        assert abs(results[-1] - 5.0) < 0.5


class TestGetSafeId:
    def test_standard_youtube_url(self):
        gsid = exec_ns["get_safe_id"]
        assert gsid("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_shorts_url(self):
        gsid = exec_ns["get_safe_id"]
        assert gsid("https://youtube.com/shorts/abc123XYZ") == "abc123XYZ"

    def test_embed_url(self):
        gsid = exec_ns["get_safe_id"]
        assert gsid("https://youtube.com/embed/xyz789") == "xyz789"

    def test_youtu_be_short(self):
        gsid = exec_ns["get_safe_id"]
        assert gsid("https://youtu.be/abc-123") == "abc123"

    def test_invalid_url_returns_default(self):
        gsid = exec_ns["get_safe_id"]
        result = gsid("not a url at all")
        assert result == "video" or len(result) > 0

    def test_alphanumeric_only(self):
        gsid = exec_ns["get_safe_id"]
        result = gsid("https://youtube.com/watch?v=test_123-ABC")
        assert result.isalnum()


class TestTimeStrToSeconds:
    def test_hh_mm_ss(self):
        tss = exec_ns["time_str_to_seconds"]
        assert tss("01:30:00") == 5400.0

    def test_mm_ss(self):
        tss = exec_ns["time_str_to_seconds"]
        assert tss("05:30") == 330.0

    def test_ss_only(self):
        tss = exec_ns["time_str_to_seconds"]
        assert tss("45") == 45.0

    def test_zero(self):
        tss = exec_ns["time_str_to_seconds"]
        assert tss("00:00:00") == 0.0

    def test_fallback_to_float(self):
        tss = exec_ns["time_str_to_seconds"]
        assert tss("3.14") == 3.14


class TestSpeakerTrackerMatchFace:
    def setup_method(self):
        self.tracker = exec_ns["SpeakerTracker"]()

    def test_no_faces_returns_none(self):
        assert self.tracker._match_face(100, 100, 50, 50) is None

    def test_match_close_face(self):
        # Add a face first
        exec_ns["FaceState"] = exec_ns.get("FaceState", type("FaceState", (), {
            "__init__": lambda s, cx=0, cy=0, w=0, h=0, **kw: None
        }))
        from dataclasses import dataclass
        @dataclass
        class FaceState:
            cx: float = 0.0
            cy: float = 0.0
            w: int = 0
            h: int = 0
            mouth_motion: float = 0.0
            last_active_frame: int = -100
            speaking: bool = False
            smooth_motion: float = 0.0
        self.tracker.faces = [FaceState(cx=100, cy=100, w=50, h=50)]
        result = self.tracker._match_face(110, 110, 50, 50)
        assert result == 0

    def test_no_match_distant_face(self):
        from dataclasses import dataclass
        @dataclass
        class FaceState:
            cx: float = 0.0
            cy: float = 0.0
            w: int = 0
            h: int = 0
            mouth_motion: float = 0.0
            last_active_frame: int = -100
            speaking: bool = False
            smooth_motion: float = 0.0
        self.tracker.faces = [FaceState(cx=100, cy=100, w=50, h=50)]
        result = self.tracker._match_face(500, 500, 50, 50)
        assert result is None


class TestComputeSpeechSegments:
    def test_empty_words(self):
        css = exec_ns["compute_speech_segments"]
        assert css([], 0.6) == []

    def test_single_word(self):
        css = exec_ns["compute_speech_segments"]
        words = [{"start": 0.0, "end": 1.0, "text": "HELLO"}]
        result = css(words, 0.6)
        assert len(result) == 1
        assert result[0] == (0.0, 1.0)

    def test_consecutive_words_merge(self):
        css = exec_ns["compute_speech_segments"]
        words = [
            {"start": 0.0, "end": 0.5, "text": "HELLO"},
            {"start": 0.6, "end": 1.0, "text": "WORLD"},
        ]
        result = css(words, 0.6)
        assert len(result) == 1

    def test_gap_splits_segments(self):
        css = exec_ns["compute_speech_segments"]
        words = [
            {"start": 0.0, "end": 0.5, "text": "HELLO"},
            {"start": 1.5, "end": 2.0, "text": "WORLD"},
        ]
        result = css(words, 0.6)
        assert len(result) == 2


class TestDetectEmphasisWords:
    def test_all_caps(self):
        dew = exec_ns["detect_emphasis_words"]
        words = [{"text": "STOP"}, {"text": "the"}, {"text": "RUNNING"}]
        result = dew(words)
        assert 0 in result
        assert 2 in result
        assert 1 not in result

    def test_exclamation_mark(self):
        dew = exec_ns["detect_emphasis_words"]
        words = [{"text": "Wow!"}, {"text": "normal"}]
        result = dew(words)
        assert 0 in result
        assert 1 not in result

    def test_known_keywords(self):
        dew = exec_ns["detect_emphasis_words"]
        words = [{"text": "Never"}, {"text": "give"}, {"text": "up"}]
        result = dew(words)
        assert 0 in result  # "Never" is in emphasis_words set


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
