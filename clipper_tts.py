"""
clipper_tts.py — Unified TTS for YT Short Clipper v1.1.0
Provider chain: OptiClone (LuxTTS clone) -> Edge-TTS (gratis, online) -> Voicebox (legacy) -> fail

- OptiClone: zero-shot clone dari 3 detik audio referensi, LuxTTS 150x realtime, <1GB VRAM
  Repo: ycharfi09/OptiClone (vendor/opticlone), model 5-10GB download on first run (HF cache)
- Edge-TTS: Microsoft Edge TTS gratis tanpa API key, suara id-ID-ArdiNeural/GadisNeural
  pip install edge-tts
- Voicebox: legacy local server http://127.0.0.1:17493 (keep for backward compat)

Semua import lazy — kalau dependency belum install, fallback otomatis, gak bikin crash.
"""
from __future__ import annotations
import asyncio
import logging
import sys
from pathlib import Path

logger = logging.getLogger("clipper.tts")

BASE_DIR = Path(__file__).parent.absolute()
VENDOR_OPTICLONE = BASE_DIR / "vendor" / "opticlone"

# Make vendor/opticlone importable
if str(VENDOR_OPTICLONE) not in sys.path:
    sys.path.insert(0, str(VENDOR_OPTICLONE))

# ---------- Edge-TTS ----------
EDGE_VOICES = {
    "id-ID-ArdiNeural (cowok)": "id-ID-ArdiNeural",
    "id-ID-GadisNeural (cewek)": "id-ID-GadisNeural",
    "en-US-AriaNeural": "en-US-AriaNeural",
    "en-US-GuyNeural": "en-US-GuyNeural",
}
DEFAULT_EDGE_VOICE = "id-ID-ArdiNeural"

async def _edge_save(text: str, voice: str, out: Path):
    import edge_tts  # type: ignore
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(out))

def edge_tts_generate(text: str, output_path: Path, voice: str = DEFAULT_EDGE_VOICE, log_func=None) -> bool:
    """Generate via Edge-TTS (needs internet). Returns True on success."""
    try:
        import edge_tts  # type: ignore  # noqa: F401
    except ImportError:
        if log_func: log_func("[TTS] edge-tts belum install. pip install edge-tts")
        logger.warning("edge-tts not installed")
        return False
    try:
        if log_func: log_func(f"[TTS] Edge-TTS ({voice}) generating...")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        asyncio.run(_edge_save(text, voice, output_path))
        if output_path.exists() and output_path.stat().st_size > 1000:
            if log_func: log_func(f"[TTS] Edge-TTS OK ({output_path.stat().st_size//1024} KB)")
            return True
        return False
    except Exception as e:
        if log_func: log_func(f"[TTS] Edge-TTS gagal: {e}")
        logger.debug("edge_tts fail: %s", e)
        return False

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
        if log_func: log_func(f"[TTS] OptiClone deps belum lengkap: {e}. pip install -r vendor/opticlone/requirements.txt")
        logger.warning("opticlone import fail: %s", e)
        return False
    try:
        if _opticlone_engine is None:
            if log_func: log_func("[TTS] OptiClone loading LuxTTS model (first run download 5-10GB, sabar)...")
            _opticlone_engine = InferenceEngine()
            _opticlone_engine.load_model()
            if log_func: log_func(f"[TTS] OptiClone model ready (device={_opticlone_engine.device})")
        # set reference if provided and not already set or changed
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
      - tts_provider: "opticlone" | "edge" | "voicebox" | "auto" (default auto)
      - tts_reference_path: path wav/mp3 for opticlone (3+ detik)
      - tts_edge_voice: e.g. "id-ID-ArdiNeural"
      - opticlone_steps, opticlone_speed
    Chain auto: opticlone (if ref set) -> edge -> voicebox
    """
    cfg = config or {}
    provider = (cfg.get("tts_provider") or "auto").lower().strip()
    ref = cfg.get("tts_reference_path") or cfg.get("tts_ref") or ""
    edge_voice = cfg.get("tts_edge_voice") or DEFAULT_EDGE_VOICE
    steps = int(cfg.get("opticlone_steps", 4) or 4)
    speed = float(cfg.get("opticlone_speed", 1.0) or 1.0)

    # explicit provider
    if provider == "opticlone":
        return opticlone_generate(text, output_path, ref, num_steps=steps, speed=speed, log_func=log_func)
    if provider == "edge":
        return edge_tts_generate(text, output_path, voice=edge_voice, log_func=log_func)
    if provider == "voicebox":
        from clipper_core import voicebox_generate
        return voicebox_generate(text, output_path, log_func=log_func)

    # auto chain
    # 1. OptiClone if reference exists
    if ref and Path(ref).exists() and Path(ref).stat().st_size > 1000:
        if opticlone_generate(text, output_path, ref, num_steps=steps, speed=speed, log_func=log_func):
            return True
        if log_func: log_func("[TTS] OptiClone fallback ke Edge-TTS...")
    # 2. Edge-TTS
    if edge_tts_generate(text, output_path, voice=edge_voice, log_func=log_func):
        return True
    if log_func: log_func("[TTS] Edge-TTS fallback ke Voicebox...")
    # 3. Voicebox
    try:
        from clipper_core import voicebox_generate
        return voicebox_generate(text, output_path, log_func=log_func)
    except Exception:
        return False
