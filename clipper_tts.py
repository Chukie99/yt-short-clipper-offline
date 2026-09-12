"""
clipper_tts.py — TTS for YT Short Clipper (inside)
Provider chain: OptiClone (LuxTTS clone) -> Voicebox (legacy) -> fail

- OptiClone: zero-shot clone dari 3 detik audio referensi, LuxTTS 150x realtime, <1GB VRAM
  Repo: ycharfi09/OptiClone (vendor/opticlone), model 5-10GB download on first run (HF cache)
- Voicebox: legacy local server http://127.0.0.1:17493 (keep for backward compat)

Semua import lazy — kalau deps belum install, fallback otomatis, gak bikin crash.
"""
from __future__ import annotations
import logging
import sys
from pathlib import Path

logger = logging.getLogger("clipper.tts")

BASE_DIR = Path(__file__).parent.absolute()
VENDOR_OPTICLONE = BASE_DIR / "vendor" / "opticlone"

if str(VENDOR_OPTICLONE) not in sys.path:
    sys.path.insert(0, str(VENDOR_OPTICLONE))

# ---------- OptiClone ----------
_opticlone_engine = None  # lazy singleton

def opticlone_generate(text: str, output_path: Path, reference_path: str | Path | None = None,
                       num_steps: int = 4, speed: float = 1.0, log_func=None) -> bool:
    """
    Generate via OptiClone/LuxTTS. Needs reference audio 3+ detik (wav/mp3).
    Model auto-download 5-10GB on first run (HF hub).
    Works on CUDA <1GB VRAM, CPU also (slower).
    """
    global _opticlone_engine
    try:
        from opticlone.inference_engine import InferenceEngine  # type: ignore
        from opticlone.config import SAMPLE_RATE  # type: ignore
        import soundfile as sf  # type: ignore
    except ImportError as e:
        if log_func: log_func(f"[TTS] OptiClone deps belum lengkap: {e}. pip install -r requirements-tts-opticlone.txt")
        logger.warning("opticlone import fail: %s", e)
        return False
    try:
        if _opticlone_engine is None:
            if log_func: log_func("[TTS] OptiClone loading LuxTTS model (first run download 5-10GB, sabar)...")
            _opticlone_engine = InferenceEngine()
            _opticlone_engine.load_model()
            if log_func: log_func(f"[TTS] OptiClone model ready (device={_opticlone_engine.device})")
        ref = str(reference_path) if reference_path else None
        if ref:
            if _opticlone_engine.reference_path != ref or not _opticlone_engine.has_reference:
                _opticlone_engine.set_reference(ref)
        elif not _opticlone_engine.has_reference:
            if log_func: log_func("[TTS] OptiClone butuh reference audio 3 detik. Upload di Settings -> TTS Reference.")
            return False
        wav = _opticlone_engine.generate(text, num_steps=num_steps, speed=speed)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(output_path), wav, SAMPLE_RATE)
        if log_func: log_func(f"[TTS] OptiClone OK ({output_path.stat().st_size//1024} KB, {len(wav)/SAMPLE_RATE:.1f}s)")
        return True
    except Exception as e:
        if log_func: log_func(f"[TTS] OptiClone gagal: {e}")
        logger.exception("opticlone generate fail")
        return False

# ---------- Unified entry ----------
def tts_generate(text: str, output_path: Path, config: dict | None = None, log_func=None) -> bool:
    """
    Unified TTS. Config keys:
      - tts_provider: "opticlone" | "voicebox" | "auto" (default auto)
      - tts_reference_path: path wav/mp3 for opticlone (3+ detik)
      - opticlone_steps, opticlone_speed
    Chain auto: opticlone (if ref set) -> voicebox
    """
    cfg = config or {}
    provider = (cfg.get("tts_provider") or "auto").lower().strip()
    ref = cfg.get("tts_reference_path") or cfg.get("tts_ref") or ""
    steps = int(cfg.get("opticlone_steps", 4) or 4)
    speed = float(cfg.get("opticlone_speed", 1.0) or 1.0)

    if provider == "opticlone":
        return opticlone_generate(text, output_path, ref, num_steps=steps, speed=speed, log_func=log_func)
    if provider == "voicebox":
        from clipper_core import voicebox_generate
        return voicebox_generate(text, output_path, log_func=log_func)

    # auto: opticlone jika ada ref -> voicebox
    if ref and Path(ref).exists() and Path(ref).stat().st_size > 1000:
        if opticlone_generate(text, output_path, ref, num_steps=steps, speed=speed, log_func=log_func):
            return True
        if log_func: log_func("[TTS] OptiClone gagal, fallback ke Voicebox...")
    elif ref:
        # ref path set tapi file belum ada -> coba opticlone tanpa ref check (akan minta ref)
        if opticlone_generate(text, output_path, ref, num_steps=steps, speed=speed, log_func=log_func):
            return True
    else:
        # tanpa ref, opticlone akan gagal dengan pesan — langsung voicebox
        pass
    try:
        from clipper_core import voicebox_generate
        return voicebox_generate(text, output_path, log_func=log_func)
    except Exception:
        return False
