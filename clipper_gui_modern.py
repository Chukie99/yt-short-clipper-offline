import os, sys, subprocess, threading, time, json, traceback, re, requests, logging
from dataclasses import dataclass
from typing import List, Tuple
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ---------- Logging Setup ----------
LOG_FILE = Path(__file__).parent / "error.log"
logger = logging.getLogger("clipper")
logger.setLevel(logging.DEBUG)
_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
_fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
_fh.setLevel(logging.DEBUG)
_fh.setFormatter(_fmt)
_sh = logging.StreamHandler()
_sh.setLevel(logging.WARNING)
_sh.setFormatter(_fmt)
logger.addHandler(_fh)
logger.addHandler(_sh)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

import customtkinter as ctk
from tkinter import messagebox, Menu, filedialog, TclError
import cv2
import numpy as np
from PIL import Image as PILImage, ImageDraw, ImageFont
import mediapipe as mp
from mediapipe.tasks.python import vision
from mediapipe.tasks.python import core

class KalmanFilter:
    def __init__(self, process_noise=1e-5, measurement_noise=1e-2):
        self.process_noise = process_noise
        self.measurement_noise = measurement_noise
        self.estimate = 0
        self.error_cov = 1
    
    def update(self, measurement):
        # Prediction
        error_cov = self.error_cov + self.process_noise
        # Correction
        kalman_gain = error_cov / (error_cov + self.measurement_noise)
        self.estimate = self.estimate + kalman_gain * (measurement - self.estimate)
        self.error_cov = (1 - kalman_gain) * error_cov
        return self.estimate

# ---------- Konfigurasi Global ----------
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).parent.absolute()
bundled_bin = BASE_DIR / "bin"
if bundled_bin.exists() and str(bundled_bin) not in os.environ.get("PATH", ""):
    os.environ["PATH"] = str(bundled_bin) + os.pathsep + os.environ.get("PATH", "")
TEMP_DIR = BASE_DIR / "temp"
OUTPUT_DIR = BASE_DIR / "output"
CONFIG_FILE = BASE_DIR / "config.json"
TEMP_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

GENAI_AVAILABLE = False
try:
    from google import genai
    GENAI_AVAILABLE = True
except ImportError:
    genai = None

DEFAULT_CONFIG = {
    "ai_provider": "Gemini (Native)",
    "gemini_api_key": "",
    "gemini_model": "gemini-2.0-flash",
    "openrouter_api_key": "",
    "openrouter_model": "nvidia/nemotron-3-super-120b-a12b:free",
    "groq_api_key": "",
    "groq_model": "llama-3.3-70b-versatile",
    "pexels_api_key": "",
    "cookies_path": "",
    "watermark": "",
    "subtitle_font": "KOMIKAX_.ttf",
    "logo_path": "",
    "bgm_volume": 0.15,
    "render_quality": "normal",
    "template": "cinematic",
    "export_resolution": "1080x1920",
    "end_card": True,
    "end_card_text": "Follow for more!",
    "whisper_provider": "Local (faster-whisper)",
    "whisper_model": "openai/whisper-1",
    "silence_threshold": 0.6,
}

RENDER_PRESETS = {
    "draft":  {"crf": 23, "preset": "ultrafast", "label": "Draft (CEPAT)"},
    "normal": {"crf": 18, "preset": "fast",       "label": "Normal (Seimbang)"},
    "high":   {"crf": 15, "preset": "slow",       "label": "High (Kualitas)"},
}

TEMPLATES = {
    "cinematic": {
        "label": "Cinematic",
        "vignette": 0.5,
        "saturation": 1.05,
        "contrast": 1.02,
        "outline_w": 14,
        "subtitle_y": 0.78,
        "subtitle_scale": 1.0,
        "active_scale": 1.1,
        "active_color": (255, 230, 0),
        "inactive_color": (255, 255, 255),
        "inactive_alpha": 153,
        "shadow": True,
        "grad_start": 0.75,
    },
    "clean": {
        "label": "Clean",
        "vignette": 0.0,
        "saturation": 1.0,
        "contrast": 1.0,
        "outline_w": 8,
        "subtitle_y": 0.80,
        "subtitle_scale": 1.0,
        "active_scale": 1.05,
        "active_color": (255, 255, 255),
        "inactive_color": (200, 200, 200),
        "inactive_alpha": 180,
        "shadow": False,
        "grad_start": 1.0,
    },
    "bold": {
        "label": "Bold",
        "vignette": 0.3,
        "saturation": 1.1,
        "contrast": 1.05,
        "outline_w": 18,
        "subtitle_y": 0.75,
        "subtitle_scale": 1.15,
        "active_scale": 1.2,
        "active_color": (255, 230, 0),
        "inactive_color": (255, 255, 255),
        "inactive_alpha": 130,
        "shadow": True,
        "grad_start": 0.65,
    },
    "story": {
        "label": "Story",
        "vignette": 0.6,
        "saturation": 1.08,
        "contrast": 1.04,
        "outline_w": 12,
        "subtitle_y": 0.82,
        "subtitle_scale": 1.0,
        "active_scale": 1.12,
        "active_color": (100, 200, 255),
        "inactive_color": (255, 255, 255),
        "inactive_alpha": 140,
        "shadow": True,
        "grad_start": 0.70,
    },
}

QUEUE_STATE_FILE = TEMP_DIR / "queue_state.json"

GEMINI_PROMPT = """Kamu adalah **Viral Content Analyst AI** — spesialis menemukan segmen VIRAL dari video edukasi, podcast, wawancara, atau ceramah.

## PRINSIP UTAMA:
Analisis seperti content creator yang paham algoritma TikTok/YouTube Shorts. Cari momen yang bikin orang: **terkejut, tertawa, terinspirasi, atau mikir "kok gue baru tau?!"**

---

## ATURAN KETAT:
1. **DURASI**: 45-75 detik (pendek = retensi tinggi).
2. **STRUKTUR**: Konteks -> Klimaks -> Reaksi. Potong **tepat setelah punchline terasa** (jangan dipotong di tengah napas).
3. **VIBES VIRAL**: Cari momen yang: kontroversial, mind-blowing, relatable banget, atau tips praktis yang langsung bisa dipake.
4. **2 PEMBICARA**: Jika ada 2 orang aktif ngomong, set `"split_screen": true` biar dua-duanya kelihatan.

5. **ARC WAJIB**: Setiap clip HARUS punya struktur: 
   - 0-5 detik: Hook (pertanyaan/pernyataan mengejutkan)
   - 5-40 detik: Penjelasan/konflik membangun
   - 40-akhir: Klimaks/jawaban/punchline yang memuaskan
   JANGAN pilih segmen yang berhenti di tengah penjelasan.

6. **ANTI-FILLER**: Hindari segmen yang diawali dengan "jadi...", "nah...", "ee...", atau basa-basi. 
   Start harus langsung ke inti.

7. **SKOR VIRAL**: Sebelum memilih, beri skor 1-10 untuk setiap kandidat segmen berdasarkan:
   - Apakah ada momen "aha!" atau kejutan? (+3)
   - Apakah bisa berdiri sendiri tanpa konteks video asli? (+3)
   - Apakah ada emosi (tawa/kaget/haru)? (+2)
   - Apakah diakhiri dengan kalimat kuat? (+2)
   Pilih HANYA segmen dengan skor >= 7.

---

## DATA INPUT:
{transcript}

---

## FORMAT OUTPUT (HANYA JSON, NO MARKDOWN):
[
  {{
    "start": "HH:MM:SS",
    "end": "HH:MM:SS",
    "title": "Judul VIRAL (bikin penasaran, pake angka atau pertanyaan)",
    "description": "DESKRIPSI PANJANG & ENGAGING (min 3 paragraf). Ceritakan konteks, kenapa ini penting, ajak diskusi di komen, + 10-15 hashtag relevan.",
    "hook": "Satu kalimat yang bikin orang WAJIB nonton",
    "mood": "inspirasi/tegang/santai/kocak",
    "split_screen": false,
    "judul_opini": "Teks overlay provokatif 2-4 kata (misal: 'STOP OVER THINKING!' atau 'MINDBLOWING!')",
    "voice_hook_script": "Naskah hook 1 kalimat untuk voice over pembuka, langsung ke inti masalah"
  }}
]
Keluarkan HANYA JSON array."""

def load_config():
    config = DEFAULT_CONFIG.copy()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    file_config = json.loads(content)
                    config.update(file_config)
        except (json.JSONDecodeError, IOError):
            pass
    if not config.get("gemini_api_key"):
        config["gemini_api_key"] = os.environ.get("GEMINI_API_KEY", "")
    if not config.get("openrouter_api_key"):
        config["openrouter_api_key"] = os.environ.get("OPENROUTER_API_KEY", "")
    if not config.get("groq_api_key"):
        config["groq_api_key"] = os.environ.get("GROQ_API_KEY", "")
    return config

def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f: json.dump(config, f, indent=2)

def check_dependencies():
    errors = []
    bundled_bin = BASE_DIR / "bin"
    if bundled_bin.exists() and str(bundled_bin) not in os.environ.get("PATH", ""):
        os.environ["PATH"] = str(bundled_bin) + os.pathsep + os.environ["PATH"]
    try: subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as e: errors.append("ffmpeg.exe tidak ditemukan di folder bin/"); logger.debug("ffmpeg check: %s", e)
    try: subprocess.run(["yt-dlp", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as e: errors.append("yt-dlp.exe tidak ditemukan di folder bin/"); logger.debug("yt-dlp check: %s", e)
    try: from faster_whisper import WhisperModel
    except ImportError as e: errors.append("faster-whisper tidak terinstall."); logger.debug("faster-whisper import: %s", e)
    try: import cv2
    except ImportError as e: errors.append("opencv-python tidak terinstall."); logger.debug("opencv import: %s", e)
    try: import numpy
    except ImportError as e: errors.append("numpy tidak terinstall."); logger.debug("numpy import: %s", e)
    return errors

def list_available_fonts():
    fonts = []
    local_fonts = BASE_DIR / "fonts"
    if local_fonts.exists():
        for f in local_fonts.glob("*.[tT][tT][fF]"): fonts.append(f.name)
        for f in local_fonts.glob("*.[oO][tT][fF]"): fonts.append(f.name)
    system_fonts = ["Montserrat-Bold.ttf", "arialbd.ttf", "Impact.ttf"]
    for f in system_fonts:
        if f not in fonts: fonts.append(f)
    return sorted(list(set(fonts)))

def get_safe_id(link):
    vid_id_match = re.search(r"(?:v=|\/shorts\/|\/embed\/|\/v\/|youtu\.be\/|\/watch\?v=|\/watch\?.+&v=)([\w-]+)", link)
    vid_id = vid_id_match.group(1) if vid_id_match else "video"
    return "".join(c for c in vid_id if c.isalnum())

def save_queue_state(segments, config):
    state = {"segments": [], "config": {}}
    for seg in segments:
        s = {k: v for k, v in seg.items() if not k.startswith("_")}
        state["segments"].append(s)
    state["config"] = {
        "render_quality": config.get("render_quality", "normal"),
        "template": config.get("template", "cinematic"),
        "export_resolution": config.get("export_resolution", "1080x1920"),
        "end_card": config.get("end_card", True),
        "end_card_text": config.get("end_card_text", "Follow for more!"),
    }
    QUEUE_STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

def load_queue_state():
    if not QUEUE_STATE_FILE.exists():
        return None
    try:
        return json.loads(QUEUE_STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError):
        return None

def clear_queue_state():
    if QUEUE_STATE_FILE.exists():
        QUEUE_STATE_FILE.unlink(missing_ok=True)

def draw_end_card(img_pil, draw, font, target_w, target_h, text, progress):
    if progress <= 0 or progress >= 1:
        return
    alpha = int(255 * min(1.0, progress / 0.3))
    overlay = PILImage.new('RGBA', (target_w, target_h), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    bg_alpha = int(200 * progress)
    ov_draw.rectangle([0, target_h - 180, target_w, target_h], fill=(0, 0, 0, min(bg_alpha, 220)))
    bbox = ov_draw.textbbox((0, 0), text.upper(), font=font)
    tw = bbox[2] - bbox[0]
    tx = (target_w - tw) // 2
    ty = target_h - 130
    ov_draw.text((tx + 3, ty + 3), text.upper(), font=font, fill=(0, 0, 0, alpha))
    ov_draw.text((tx, ty), text.upper(), font=font, fill=(255, 255, 255, alpha))
    img_pil.paste(ov_draw, (0, 0), ov_draw)

def add_subtitle_animation(draw, text, font, x, y, fill, outline_w, frame_num, fps, template, is_active=False):
    scale = template.get("active_scale", 1.1) if is_active else template.get("subtitle_scale", 1.0)
    if is_active:
        cycle_frame = frame_num % int(fps * 0.6)
        if cycle_frame < int(fps * 0.08):
            bounce = 1.0 + 0.08 * (cycle_frame / (fps * 0.08))
            scale *= bounce
    try:
        if abs(scale - 1.0) > 0.01:
            anim_font = ImageFont.truetype(font.path, int(font.size * scale))
        else:
            anim_font = font
    except (OSError, IOError, ValueError) as e:
        anim_font = font
        logger.debug("Subtitle font scale fallback: %s", e)
    if is_active:
        draw.text((x + 3, y + 3), text, font=anim_font, fill=(0, 0, 0, 200), stroke_width=outline_w, stroke_fill=(0, 0, 0, 200))
        draw.text((x, y), text, font=anim_font, fill=fill, stroke_width=outline_w, stroke_fill=(0, 0, 0, 255))
    else:
        inactive_c = template.get("inactive_color", (255, 255, 255))
        inactive_a = template.get("inactive_alpha", 153)
        draw.text((x, y), text, font=anim_font, fill=(*inactive_c, inactive_a), stroke_width=outline_w // 2, stroke_fill=(0, 0, 0, inactive_a // 2))

def run_cmd(cmd, log_func=None):
    try:
        process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, encoding='utf-8', errors='replace')
        output = []
        if process.stdout:
            for line in process.stdout:
                line = line.strip()
                if line:
                    output.append(line)
                    if log_func and any(x in line.lower() for x in ["%", "fps", "speed", "time=", "download", "error", "failed"]): 
                        log_func(f"   > {line}")
        process.wait()
        if process.returncode != 0:
            full_out = "\n".join(output[-15:])
            err_lower = full_out.lower()
            if "sign in to confirm" in err_lower or "cookies" in err_lower:
                raise Exception("❌ Cookies YouTube expired. Export ulang cookies.txt dari browser:\n   1. Buka YouTube.com, login\n   2. Install extension 'Get cookies.txt'\n   3. Klik extension → Export\n   4. Simpan ke file .txt yang sama di Settings")
            raise Exception(f"❌ Proses gagal (kode {process.returncode}). Detail:\n{full_out}")
    except Exception as e:
        logger.error("run_cmd failed: %s", e)
        raise Exception(str(e)) from e

def safe_generate_content(config, contents, log_func=None):
    provider = config.get("ai_provider", "Gemini (Native)")
    max_retries = 3; retry_delay = 20
    for i in range(max_retries):
        try:
            if provider == "Gemini (Native)":
                if not GENAI_AVAILABLE: raise ImportError("Library Google GenAI tidak tersedia.")
                api_key = config.get("gemini_api_key", "") or os.environ.get("GEMINI_API_KEY", "")
                client = genai.Client(api_key=api_key)
                model = config.get("gemini_model", "gemini-2.0-flash")
                response = client.models.generate_content(model=model, contents=contents)
                return response.text.strip()
            elif provider == "Groq":
                api_key = config.get("groq_api_key", "") or os.environ.get("GROQ_API_KEY", "")
                model = config.get("groq_model", "llama-3.3-70b-versatile")
                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                payload = {"model": model, "messages": [{"role": "user", "content": contents}]}
                resp = requests.post(url, headers=headers, json=payload, timeout=60)
                if resp.status_code == 429: raise Exception("429 RESOURCE_EXHAUSTED")
                resp.raise_for_status(); return resp.json()['choices'][0]['message']['content'].strip()
            else:
                api_key = config.get("openrouter_api_key", "") or os.environ.get("OPENROUTER_API_KEY", "")
                model = config.get("openrouter_model", "nvidia/nemotron-3-super-120b-a12b:free")
                url = "https://openrouter.ai/api/v1/chat/completions"
                headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                payload = {"model": model, "messages": [{"role": "user", "content": contents}]}
                resp = requests.post(url, headers=headers, json=payload, timeout=60)
                if resp.status_code == 429: raise Exception("429 RESOURCE_EXHAUSTED")
                resp.raise_for_status(); return resp.json()['choices'][0]['message']['content'].strip()
        except Exception as e:
            logger.warning("AI provider %s attempt %d failed: %s", provider, i + 1, e)
            if "429" in str(e) and log_func: log_func(f"[!] Quota Habis. Menunggu {retry_delay}s..."); time.sleep(retry_delay); retry_delay += 15
            else: raise e
    raise Exception(f"Gagal menghubungi {provider}.")

def ensure_bgm(mood, log_func, config=None):
    bgm_dir = BASE_DIR / "backsound"; bgm_dir.mkdir(exist_ok=True)
    bgm_path = bgm_dir / f"{mood.lower()}.mp3"
    if bgm_path.exists(): return bgm_path
    
    # Try Pexels API first if key exists
    pexels_key = config.get("pexels_api_key") if config else None
    if pexels_key:
        try:
            log_func(f"[🎵] Mencari backsound di Pexels (Mood: {mood})...")
            url = f"https://api.pexels.com/videos/search?query={mood}+music&per_page=5"
            headers = {"Authorization": pexels_key}
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                vids = resp.json().get("videos", [])
                if vids:
                    # Sort by duration to get shortest/most appropriate
                    vids.sort(key=lambda x: x.get("duration", 999))
                    v_url = vids[0]["video_files"][0]["link"]
                    r_v = requests.get(v_url, stream=True)
                    temp_vid = bgm_dir / f"temp_{mood}.mp4"
                    with open(temp_vid, "wb") as f:
                        for chunk in r_v.iter_content(chunk_size=8192): f.write(chunk)
                    # Extract audio
                    run_cmd(f'ffmpeg -y -i "{temp_vid}" -vn -acodec mp3 "{bgm_path}"')
                    temp_vid.unlink(missing_ok=True)
                    if bgm_path.exists():
                        log_func(f"[✅] Backsound {mood} dari Pexels berhasil.")
                        return bgm_path
        except Exception as e:
            log_func(f"[⚠️] Pexels error: {str(e)}")

    # Fallback to YouTube search
    # WARNING: YouTube search results labeled "no copyright" are NOT guaranteed royalty-free.
    # Using a Pexels API key is strongly recommended for safe, licensed BGM.
    log_func(f"[⚠️] PERINGATAN: BGM dari YouTube belum tentu bebas royalti. "
             "Gunakan Pexels API key untuk BGM berlisensi aman, atau ganti BGM manual.")
    search_map = {
        "kocak": "Funny comedy background music no copyright",
        "tegang": "Suspense cinematic background music no copyright",
        "sedih": "Sad emotional background music no copyright",
        "inspirasi": "Inspirational corporate background music no copyright",
        "santai": "Chill lofi background music no copyright"
    }
    query = search_map.get(mood.lower(), "Chill background music no copyright")
    log_func(f"[🎵] Fallback: Mencari backsound di YouTube (beresiko copyright claim!)...")
    ytdlp_path = "yt-dlp"; local_ytdlp = BASE_DIR / "bin" / "yt-dlp.exe"
    if local_ytdlp.exists(): ytdlp_path = f'"{str(local_ytdlp)}"'
    try:
        cmd = f'{ytdlp_path} --no-update --user-agent "{UA}" --match-filter "duration < 300" --extract-audio --audio-format mp3 --output "{bgm_path}" "ytsearch1:{query}"'
        subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if bgm_path.exists():
            log_func(f"[✅] Backsound {mood} berhasil di-download (⚠️ lisensi tidak dijamin).")
            return bgm_path
    except Exception as e:
        log_func(f"[⚠️] Fallback error: {str(e)}")
    return None

def fetch_pexels_broll(keyword, pexels_api_key, output_dir):
    if not pexels_api_key: return None
    try:
        url = f"https://api.pexels.com/v1/search?query={keyword}&per_page=1"
        headers = {"Authorization": pexels_api_key}
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("photos"):
                img_url = data["photos"][0]["src"]["large"]
                img_path = output_dir / f"broll_{keyword.replace(' ', '_')}.jpg"
                if not img_path.exists():
                    r = requests.get(img_url, timeout=15)
                    with open(img_path, "wb") as f: f.write(r.content)
                return img_path
    except (requests.RequestException, KeyError, IndexError): pass

def extract_keywords_from_transcript(all_words, config, log_func):
    if not all_words: return []
    res = []
    # Process in 5-second chunks
    max_time = all_words[-1]["end"]
    for t in range(0, int(max_time), 5):
        chunk_words = [w["text"] for w in all_words if t <= w["start"] < t + 5]
        if not chunk_words: continue
        
        words_str = " ".join(chunk_words)
        prompt = f"Dari kata-kata ini: '{words_str}', ekstrak 1 kata kunci visual paling konkret (benda/organ/tempat/orang terkenal). Jawab 1 kata saja dalam bahasa Inggris."
        try:
            keyword = safe_generate_content(config, prompt, log_func=None).strip()
            # Clean keyword (remove punctuation, etc.)
            keyword = "".join(c for c in keyword if c.isalnum() or c == ' ').split()[0]
            if keyword and len(keyword) > 2:
                res.append((t, keyword))
        except Exception:
            pass
    return res

def time_str_to_seconds(t):
    try:
        parts = list(map(float, t.split(":")))
        if len(parts) == 3: return parts[0]*3600 + parts[1]*60 + parts[2]
        elif len(parts) == 2: return parts[0]*60 + parts[1]
        else: return parts[0]
    except (ValueError, IndexError, TypeError) as e:
        logger.debug("time_str_to_seconds fallback for '%s': %s", t, e)
        return float(t)

def compute_speech_segments(all_words, silence_threshold=0.6):
    """Compute list of (start, end) time ranges where speech is active.
    Merges consecutive words and splits at gaps > silence_threshold."""
    if not all_words:
        return []
    segments = []
    seg_start = all_words[0]["start"]
    seg_end = all_words[0]["end"]
    for w in all_words[1:]:
        if w["start"] - seg_end > silence_threshold:
            segments.append((seg_start, seg_end))
            seg_start = w["start"]
        seg_end = w["end"]
    segments.append((seg_start, seg_end))
    return segments

def is_in_speech_segment(cur_time, speech_segments):
    """Check if cur_time falls within any speech segment (with small padding)."""
    if not speech_segments:
        return True
    PAD = 0.05
    for s_start, s_end in speech_segments:
        if s_start - PAD <= cur_time <= s_end + PAD:
            return True
    return False

def detect_emphasis_words(all_words):
    """Detect emphasis words: all caps, ending with !, or short punchy words."""
    emphasis_indices = set()
    emphasis_words = {"STOP", "NO", "YES", "WAIT", "REALLY", "LITERALLY",
                      "INSANE", "CRAZY", "MIND", "BLOWING", "UNBELIEVABLE",
                      "SHOCKING", "AMAZING", "INCREDIBLE", "NEVER", "ALWAYS",
                      "BEST", "WORST", "ONLY", "EVER", "NOTHING", "EVERYTHING"}
    for i, w in enumerate(all_words):
        text = w["text"].strip()
        if not text:
            continue
        # All caps word (>2 chars) or ends with !
        if (text.isupper() and len(text) > 2) or text.endswith("!"):
            emphasis_indices.add(i)
        # Known emphasis words
        elif text.upper() in emphasis_words:
            emphasis_indices.add(i)
    return emphasis_indices

def detect_whisper_device():
    """Auto-detect best device for faster-whisper: CUDA > CPU."""
    try:
        import torch
        if torch.cuda.is_available():
            logger.info("GPU detected: %s — using CUDA for Whisper", torch.cuda.get_device_name(0))
            return "cuda", "float16"
    except ImportError:
        pass
    except Exception as e:
        logger.debug("GPU detection failed: %s", e)
    return "cpu", "int8"

def draw_pro_text(draw, text, pos, font, fill=(255, 255, 0), outline_color=(0, 0, 0), outline_width=12, shadow_offset=(5, 7), shadow_alpha=160):
    x, y = pos
    text = text.upper()
    draw.text((x, y), text, font=font, fill=outline_color, stroke_width=outline_width, stroke_fill=outline_color)
    draw.text((x+shadow_offset[0], y+shadow_offset[1]), text, font=font, fill=(0,0,0,shadow_alpha))
    draw.text((x, y), text, font=font, fill=fill)

def apply_vignette(frame, strength=0.5):
    h, w = frame.shape[:2]
    Y, X = np.ogrid[:h, :w]
    cx, cy = w/2, h/2
    dist = np.sqrt(((X-cx)/(w*0.5))**2 + ((Y-cy)/(h*0.5))**2)
    mask = 1.0 - np.clip((dist - 0.5) * strength * 2, 0, 1) * 0.7
    mask = mask[:,:,np.newaxis]
    return (frame.astype("float32") * mask).astype("uint8")

def apply_cinematic_grade(frame):
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB).astype("float32")
    l_chan = lab[:,:,0] / 255.0
    l_chan = l_chan + 0.1 * np.sin(np.pi * l_chan)
    lab[:,:,0] = np.clip(l_chan * 255, 0, 255)
    result = cv2.cvtColor(lab.astype("uint8"), cv2.COLOR_LAB2BGR)
    hsv = cv2.cvtColor(result, cv2.COLOR_BGR2HSV).astype("float32")
    hsv[:,:,1] = np.clip(hsv[:,:,1] * 1.25, 0, 255)
    hsv[:,:,2] = np.clip(hsv[:,:,2] * 1.08, 0, 255)
    return cv2.cvtColor(hsv.astype("uint8"), cv2.COLOR_HSV2BGR)

def render_grid_layout(frame, face_list, target_w, target_h):
    frame_h, frame_w = frame.shape[:2]
    n = len(face_list)
    if n < 2:
        return None
    
    # Use top faces, sorted by X
    max_faces = min(4, n)
    sorted_faces = sorted(face_list[:max_faces], key=lambda f: f[0])

    def get_smart_crop(face_info, tw, th):
        fx, fy, fw, fh, _ = face_info
        aspect = tw / th
        
        # Calculate source crop size (approx 3.5x face height)
        sh = int(fh * 3.5)
        sw = int(sh * aspect)
        
        # Boundary checks
        if sh > frame_h:
            sh = frame_h
            sw = int(sh * aspect)
        if sw > frame_w:
            sw = frame_w
            sh = int(sw / aspect)
            
        cx, cy = int(fx), int(fy - fh * 0.1)
        x1 = max(0, min(cx - sw // 2, frame_w - sw))
        y1 = max(0, min(cy - sh // 2, frame_h - sh))
        
        crop_img = frame[y1:y1+sh, x1:x1+sw]
        if crop_img.size == 0:
            return np.zeros((th, tw, 3), dtype=np.uint8)
        return cv2.resize(crop_img, (tw, th), interpolation=cv2.INTER_CUBIC)

    if n == 2:
        ph = target_h // 2
        p1 = get_smart_crop(sorted_faces[0], target_w, ph)
        p2 = get_smart_crop(sorted_faces[1], target_w, ph)
        result = np.vstack([p1, p2])
        
        # Separator: 3px white opacity 40%
        overlay = result.copy()
        cv2.line(overlay, (0, ph), (target_w, ph), (255, 255, 255), 3)
        cv2.addWeighted(overlay, 0.4, result, 0.6, 0, result)
        return result

    elif n == 3:
        ph = target_h // 2
        pw_half = target_w // 2
        # Top: 2 panels (540x960 each)
        p1 = get_smart_crop(sorted_faces[0], pw_half, ph)
        p2 = get_smart_crop(sorted_faces[1], pw_half, ph)
        top_row = np.hstack([p1, p2])
        # Bottom: 1 panel (1080x960)
        p3 = get_smart_crop(sorted_faces[2], target_w, ph)
        result = np.vstack([top_row, p3])
        
        # Separators
        overlay = result.copy()
        cv2.line(overlay, (0, ph), (target_w, ph), (255, 255, 255), 3)
        cv2.line(overlay, (pw_half, 0), (pw_half, ph), (255, 255, 255), 3)
        cv2.addWeighted(overlay, 0.4, result, 0.6, 0, result)
        return result

    else: # 4 panels
        ph = target_h // 2
        pw_half = target_w // 2
        p1 = get_smart_crop(sorted_faces[0], pw_half, ph)
        p2 = get_smart_crop(sorted_faces[1], pw_half, ph)
        p3 = get_smart_crop(sorted_faces[2], pw_half, ph)
        p4 = get_smart_crop(sorted_faces[3], pw_half, ph)
        top_row = np.hstack([p1, p2])
        bot_row = np.hstack([p3, p4])
        result = np.vstack([top_row, bot_row])
        
        # Separators
        overlay = result.copy()
        cv2.line(overlay, (0, ph), (target_w, ph), (255, 255, 255), 3)
        cv2.line(overlay, (pw_half, 0), (pw_half, target_h), (255, 255, 255), 3)
        cv2.addWeighted(overlay, 0.4, result, 0.6, 0, result)
        return result


def draw_karaoke_line(img_pil, draw, all_words, active_idx, font, target_w, target_h, outline_w=14, frame_num=0, fps=25.0, base_y=None, template=None):
    if not all_words or active_idx < 0 or active_idx >= len(all_words):
        return
    if template is None:
        template = TEMPLATES["cinematic"]

    # 1. Tampilkan maksimal 5 kata sekaligus dalam 1 baris (window ending at active_idx)
    start_idx = max(0, active_idx - 4)
    words_window = all_words[start_idx : active_idx + 1]
    
    # 2. Setup fonts (scale from template)
    active_scale = template.get("active_scale", 1.1)
    try:
        font_active = ImageFont.truetype(font.path, int(font.size * active_scale))
    except (OSError, IOError, ValueError) as e:
        font_active = font
        logger.debug("Karaoke font scale fallback: %s", e)
    
    SPACING = 20
    
    # 3. Calculate total width for centering
    total_w = 0
    word_data = []
    for i, wd in enumerate(words_window):
        global_idx = start_idx + i
        is_active = (global_idx == active_idx)
        w_text = wd["text"].upper()
        f = font_active if is_active else font
        
        # Apply animation bounce for active word
        if is_active:
            cycle_frame = frame_num % int(fps * 0.6)
            if cycle_frame < int(fps * 0.08):
                bounce = 1.0 + 0.08 * (cycle_frame / (fps * 0.08))
                try:
                    f = ImageFont.truetype(font.path, int(font.size * active_scale * bounce))
                except (OSError, IOError, ValueError) as e:
                    f = font_active
                    logger.debug("Bounce font fallback: %s", e)
        
        bbox = draw.textbbox((0, 0), w_text, font=f)
        ww = bbox[2] - bbox[0]
        total_w += ww + (SPACING if i < len(words_window) - 1 else 0)
        word_data.append({"text": w_text, "width": ww, "font": f, "is_active": is_active})
    
    # 4. Posisi: Y from template
    ly = int(target_h * template.get("subtitle_y", 0.78))
    cursor_x = (target_w - total_w) // 2
    
    # Use overlay for transparency handling
    ov = PILImage.new('RGBA', (target_w, target_h), (0,0,0,0))
    d_ov = ImageDraw.Draw(ov)
    
    # 5. Render words
    active_color = template.get("active_color", (255, 230, 0))
    inactive_color = template.get("inactive_color", (255, 255, 255))
    inactive_alpha = template.get("inactive_alpha", 153)
    
    for wd in word_data:
        f = wd["font"]
        w_text = wd["text"]
        is_active = wd["is_active"]
        
        if is_active:
            fill_c = (*active_color, 255)
        else:
            fill_c = (*inactive_color, inactive_alpha)
            
        d_ov.text((cursor_x, ly), w_text, font=f, fill=(0, 0, 0, 255), 
                  stroke_width=outline_w, stroke_fill=(0, 0, 0, 255), anchor="ls")
        d_ov.text((cursor_x, ly), w_text, font=f, fill=fill_c, anchor="ls")
        
        cursor_x += wd["width"] + SPACING
    
    img_pil.paste(ov, (0, 0), ov)

def apply_sharpen(frame, strength=0.3):
    """Gentle unsharp mask to reduce blur from upscaling."""
    if strength <= 0:
        return frame
    blurred = cv2.GaussianBlur(frame, (0, 0), 2.0)
    return cv2.addWeighted(frame, 1.0 + strength, blurred, -strength, 0)

def download_youtube(link, output_path, cookies_path, log_func, max_retries=3):
    """Robust youtube downloader with retry and quality enforcement."""
    ytdlp_path = "yt-dlp"
    local_ytdlp = BASE_DIR / "bin" / "yt-dlp.exe"
    if local_ytdlp.exists():
        ytdlp_path = f'"{str(local_ytdlp)}"'
    base_cmd = f'{ytdlp_path} --user-agent "{UA}" --no-update --js-runtime node --retries 10 --extractor-retries infinite --merge-output-format mp4'
    cp = cookies_path
    cookies_opts = []
    if cp and Path(cp).exists():
        cookies_opts.append(f'--cookies "{cp}"')
    else:
        cookies_opts.append("--cookies-from-browser chrome")
    format_variants = [
        '-f "bv*+ba/b"',
        '-f "bestvideo+bestaudio/best"',
        '-f "best"',
        '-f "best" --extractor-args "youtube:player_client=android"',
    ]
    strategies = []
    for fmt in format_variants:
        for ck in cookies_opts:
            strategies.append(f'{base_cmd} {ck} {fmt} -o "{output_path}" "{link}"')
    for i, cmd in enumerate(strategies[:max_retries], 1):
        try:
            log_func(f"[⬇️] Download attempt {i}/{max_retries}...")
            run_cmd(cmd, log_func=log_func)
            if output_path.exists():
                cap_check = cv2.VideoCapture(str(output_path))
                h = int(cap_check.get(cv2.CAP_PROP_FRAME_HEIGHT))
                cap_check.release()
                if h >= 480:
                    log_func(f"[✅] Downloaded {h}p")
                    return True
                else:
                    log_func(f"[⚠️] Got only {h}p, retrying...")
                    output_path.unlink(missing_ok=True)
            else:
                log_func("[⚠️] Output not created, retrying...")
        except Exception as e:
            err = str(e).lower()
            if "challenge" in err or "sign in" in err or "cookies" in err:
                log_func(f"[⚠️] Download blocked (attempt {i}), trying fallback...")
            else:
                log_func(f"[⚠️] Download error: {str(e)[:100]}")
            if output_path.exists():
                output_path.unlink(missing_ok=True)
    raise Exception("❌ Gagal mendownload video. Tutup Chrome (biar cookies bisa diambil) lalu coba lagi, atau export cookies ke file.")

def get_audio_duration(file_path):
    try:
        cmd = f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{file_path}"'
        result = subprocess.check_output(cmd, shell=True).decode("utf-8").strip()
        return float(result)
    except (subprocess.CalledProcessError, ValueError, FileNotFoundError, OSError) as e:
        logger.debug("get_audio_duration fallback for '%s': %s", file_path, e)
        return 0

VOICEBOX_API = "http://127.0.0.1:17493"

def voicebox_generate(text: str, output_path: Path, log_func=None) -> bool:
    """Generate audio from text using local Voicebox API."""
    try:
        profiles = requests.get(f"{VOICEBOX_API}/profiles", timeout=5).json()
        profile_id = profiles[0]["id"] if profiles else None
        if not profile_id:
            if log_func: log_func("[🎤] Voicebox: No voice profiles found. Create one first.")
            return False
        resp = requests.post(f"{VOICEBOX_API}/generate", json={
            "text": text, "profile_id": profile_id, "language": "en"
        }, timeout=120, stream=True)
        if resp.status_code != 200:
            if log_func: log_func(f"[🎤] Voicebox error {resp.status_code}: {resp.text[:200]}")
            return False
        ct = resp.headers.get("content-type", "")
        if "json" in ct:
            data = resp.json()
            audio_url = data.get("audio_url") or data.get("url") or data.get("path")
            if audio_url:
                if not audio_url.startswith("http"):
                    audio_url = f"{VOICEBOX_API}{audio_url}"
                r = requests.get(audio_url, timeout=60)
                with open(output_path, "wb") as f: f.write(r.content)
            else:
                audio_data = data.get("audio", data.get("data", data.get("base64")))
                if audio_data:
                    import base64
                    with open(output_path, "wb") as f: f.write(base64.b64decode(audio_data))
                else:
                    if log_func: log_func("[🎤] Voicebox: No audio in response.")
                    return False
        else:
            with open(output_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192): f.write(chunk)
        if output_path.exists() and output_path.stat().st_size > 1000:
            if log_func: log_func(f"[🎤] Voicebox OK ({output_path.stat().st_size//1024} KB)")
            return True
        return False
    except requests.ConnectionError:
        if log_func: log_func("[🎤] Voicebox not running. Start Voicebox or record hook manually.")
        return False
    except Exception as e:
        if log_func: log_func(f"[🎤] Voicebox error: {str(e)[:100]}")
        return False

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

class SpeakerTracker:
    def __init__(self):
        self.faces: List[FaceState] = []
        self.active_index: int = -1
        self.both_active: bool = False
        self.hold_split_frames: int = 0
        self.hold_speaker_frames: int = 0
        self.last_active_index: int = -1
        self.MIN_MOTION = 0.8
        self.MOTION_ALPHA = 0.85
        self.NOISE_GATE = 0.15
        self.MIN_STABLE_FRAMES = 3
        self._face_stability: dict = {}

    def _match_face(self, cx, cy, w, h, threshold=200):
        for i, fs in enumerate(self.faces):
            dist = np.hypot(cx - fs.cx, cy - fs.cy)
            if dist < threshold:
                return i
        return None

    def update(self, face_list, frame_num: int, curr_word_active: bool, word_idx: int, fps: float):
        new_faces = []
        for (cx, cy, w, h, score) in face_list:
            match = self._match_face(cx, cy, w, h)
            if match is not None:
                fs = self.faces[match]
                fs.cx, fs.cy, fs.w, fs.h = cx, cy, w, h
                new_faces.append(fs)
            else:
                fs = FaceState(cx=cx, cy=cy, w=w, h=h)
                new_faces.append(fs)
        self.faces = new_faces

        if not self.faces:
            self.active_index = -1
            self.both_active = False
            return -1, False

        if len(self.faces) == 1:
            self.active_index = 0
            self.both_active = False
            return 0, False

        best_score = -1
        best_idx = 0
        both = False
        high_motion_count = 0

        # Apply EMA smoothing to mouth_motion before scoring
        for i, fs in enumerate(self.faces):
            if fs.smooth_motion == 0.0:
                fs.smooth_motion = fs.mouth_motion
            else:
                fs.smooth_motion = fs.smooth_motion * self.MOTION_ALPHA + fs.mouth_motion * (1 - self.MOTION_ALPHA)

        for i, fs in enumerate(self.faces):
            if curr_word_active:
                is_moving = fs.smooth_motion > self.MIN_MOTION and fs.mouth_motion > self.NOISE_GATE
                fs.speaking = is_moving
                if is_moving:
                    fs.last_active_frame = frame_num
            else:
                if frame_num - fs.last_active_frame > int(fps * 0.3):
                    fs.speaking = False
            if fs.speaking:
                high_motion_count += 1

        if high_motion_count >= 2:
            both = True
            self.hold_split_frames = int(fps * 0.8)

        if self.hold_split_frames > 0:
            both = True
            self.hold_split_frames -= 1

        if both:
            self.both_active = True
            scores = [fs.smooth_motion + (1 if fs.speaking else 0) for fs in self.faces]
            self.active_index = int(np.argmax(scores))
            return self.active_index, True

        for i, fs in enumerate(self.faces):
            score = fs.smooth_motion + (5 if fs.speaking else 0)
            if score > best_score:
                best_score = score
                best_idx = i

        # Hold timer: jangan ganti speaker terlalu cepat
        if best_idx != self.last_active_index:
            if self.hold_speaker_frames > 0:
                self.hold_speaker_frames -= 1
                best_idx = self.last_active_index
            else:
                self.hold_speaker_frames = int(fps * 1.2)
                self.last_active_index = best_idx
        else:
            self.hold_speaker_frames = 0
            self.last_active_index = best_idx

        self.both_active = False
        self.active_index = best_idx
        return best_idx, False

def process_single_video(link, start_sec, end_sec, title, lang, model_size, log_func, progress_func, opts=None):
    if opts is None: opts = {}
    safe_id = get_safe_id(link)
    clean_title = title.replace("[", "").replace("]", ""); safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in clean_title).strip()
    if not safe_title: safe_title = f"short_{safe_id}"
    today_folder = time.strftime("%d-%m-%Y"); today_dir = OUTPUT_DIR / today_folder; today_dir.mkdir(exist_ok=True)
    original = TEMP_DIR / f"{safe_id}_full.mp4"; trimmed = TEMP_DIR / f"{safe_id}_{int(start_sec)}_trim.mp4"
    audio_wav = TEMP_DIR / f"{safe_id}_{int(start_sec)}_audio.wav"
    final_out, thumb_path, desc_path = today_dir / f"{safe_title}.mp4", today_dir / f"{safe_title}.jpg", today_dir / f"{safe_title}_desc.txt"

    cookies_path = opts.get("cookies_path")
    watermark = opts.get("watermark", "")
    status_func = opts.get("status_func")
    selected_font = opts.get("selected_font", "KOMIKAX_.ttf")
    logo_path = opts.get("logo_path", "")
    ai_desc = opts.get("ai_desc", "")
    split_screen = opts.get("split_screen", False)
    gen_thumb = opts.get("gen_thumb", True)
    mood = opts.get("mood", "santai")
    bgm_volume = opts.get("bgm_volume", 0.15)
    voice_hook = opts.get("voice_hook", "")
    judul_opini = opts.get("judul_opini", "")
    render_quality = opts.get("render_quality", "normal")
    template_name = opts.get("template", "cinematic")
    export_resolution = opts.get("export_resolution", "1080x1920")
    end_card_enabled = opts.get("end_card", True)
    end_card_text = opts.get("end_card_text", "Follow for more!")
    hook_text = opts.get("hook_text", "")
    tpl = TEMPLATES.get(template_name, TEMPLATES["cinematic"])
    rpreset = RENDER_PRESETS.get(render_quality, RENDER_PRESETS["normal"])

    def update_status(text):
        if status_func: status_func(text)

    try:
        if not original.exists():
            update_status("Downloading...")
            log_func(f"[{safe_id}] ⬇️  Mengunduh video...")
            progress_func(5)
            try:
                download_youtube(link, original, cookies_path, log_func)
            except Exception as e:
                log_func(str(e))
                return False, str(e)

        update_status("Trimming..."); log_func(f"[{safe_id}] ✂️  Memotong segmen..."); progress_func(15); dur = end_sec - start_sec
        run_cmd(f'ffmpeg -y -ss {start_sec} -i "{original}" -t {dur} -c:v libx264 -crf 18 -c:a aac "{trimmed}"')

        update_status("Audio Ext..."); log_func(f"[{safe_id}] 🔊 Ekstrak audio..."); progress_func(20); run_cmd(f'ffmpeg -y -i "{trimmed}" -vn -acodec pcm_s16le -ar 16000 -ac 1 "{audio_wav}"')

        update_status("Transcribing..."); log_func(f"[{safe_id}] 📝 Transkripsi ({model_size})..."); progress_func(25)
        from faster_whisper import WhisperModel
        w_device, w_compute = detect_whisper_device()
        log_func(f"[{safe_id}] 🖥️  Whisper device: {w_device} ({w_compute})")
        lmodel = WhisperModel(model_size, device=w_device, compute_type=w_compute)
        segs, _ = lmodel.transcribe(str(audio_wav), language=lang, beam_size=5, word_timestamps=True)
        all_words = [{"start": w.start, "end": w.end, "text": w.word.strip().upper()} for seg in segs if seg.words for w in seg.words]
        if not all_words:
            log_func(f"[{safe_id}] ⚠️  Tidak ada word-level timestamps, subtitle per kata dinonaktifkan")

        update_status("Rendering..."); log_func(f"[{safe_id}] 🎬 Proses frame..."); cap = cv2.VideoCapture(str(trimmed))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0; frame_w, frame_h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)); total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        res_parts = export_resolution.split("x")
        target_w, target_h = int(res_parts[0]), int(res_parts[1]) if len(res_parts) == 2 else (1080, 1920)

        # Auto-rotate: detect landscape video, rotate to portrait for Shorts
        needs_rotate = frame_w > frame_h
        if needs_rotate:
            log_func(f"[{safe_id}] 🔄 Video landscape ({frame_w}x{frame_h}), auto-rotate ke portrait")
            frame_w, frame_h = frame_h, frame_w  # swap dimensions
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        # Initialize MediaPipe Face Detector
        base_opts = core.base_options.BaseOptions(model_asset_path=str(BASE_DIR / "bin" / "detector.tflite"))
        options = vision.FaceDetectorOptions(base_options=base_opts, running_mode=vision.RunningMode.IMAGE)
        detector = vision.FaceDetector.create_from_options(options)

        zoom = opts.get("zoom", 1.0)
        y_offset_factor = opts.get("y_offset", 0.35)
        # Camera smoothing state with Kalman Filters
        kf_x = KalmanFilter(process_noise=1e-4, measurement_noise=1e-1)
        kf_y = KalmanFilter(process_noise=1e-4, measurement_noise=1e-1)
        smooth_cam_x = None
        smooth_cam_y = None
        CAM_ALPHA = 0.08  # Global smoothing factor
        HOLD_FRAMES = 6
        
        # Internal helper for smooth transition
        def get_stabilized_pos(target_x, target_y):
            nonlocal smooth_cam_x, smooth_cam_y
            val_x = kf_x.update(target_x)
            val_y = kf_y.update(target_y)
            if smooth_cam_x is None:
                smooth_cam_x, smooth_cam_y = val_x, val_y
            else:
                smooth_cam_x = smooth_cam_x * (1 - CAM_ALPHA) + val_x * CAM_ALPHA
                smooth_cam_y = smooth_cam_y * (1 - CAM_ALPHA) + val_y * CAM_ALPHA
            return int(smooth_cam_x), int(smooth_cam_y)

        # Use selected font primarily
        font_path = str(BASE_DIR / "fonts" / selected_font)
        if not os.path.exists(font_path):
            impact_path = "C:/Windows/Fonts/impact.ttf"
            font_path = impact_path if os.path.exists(impact_path) else "C:/Windows/Fonts/arialbd.ttf"
        
        font_path_ff = font_path.replace("\\", "/").replace(":", "\\\\:")
        
        try: 
            pil_font = ImageFont.truetype(font_path, 65) 
            pil_font_wm = ImageFont.truetype(font_path, 35)
            pil_font_opini = ImageFont.truetype(font_path, 75) 
        except Exception as e:
            log_func(f"[{safe_id}] ⚠️  Font '{font_path}' gagal load: {e}, pakai Montserrat-Bold")
            fallback_font = str(BASE_DIR / "fonts" / "Montserrat-Bold.ttf")
            if os.path.exists(fallback_font):
                pil_font = ImageFont.truetype(fallback_font, 65)
                pil_font_wm = ImageFont.truetype(fallback_font, 35)
                pil_font_opini = ImageFont.truetype(fallback_font, 75)
            else:
                pil_font = ImageFont.load_default()
                pil_font_wm = pil_font
                pil_font_opini = pil_font

        img_logo = None
        if logo_path:
            log_func(f"[{safe_id}] 🔍 Cek logo: '{logo_path}' exists={os.path.exists(logo_path)}")
        if logo_path and os.path.exists(logo_path):
            try:
                img_logo = PILImage.open(logo_path).convert("RGBA")
                lw, lh = img_logo.size; nlw = 180; nlh = int(lh * (nlw / lw)); img_logo = img_logo.resize((nlw, nlh), PILImage.Resampling.LANCZOS)
                log_func(f"[{safe_id}] ✅ Logo loaded: {lw}x{lh} -> {nlw}x{nlh}")
            except Exception as e:
                log_func(f"[{safe_id}] ⚠️ Logo gagal: {e}")
                img_logo = None

        # --- DYNAMIC COVER & AUDIO SYNC SETUP ---
        vh_path = Path(voice_hook) if voice_hook else None
        use_hook = vh_path is not None and vh_path.exists() and vh_path.stat().st_size > 1000
        audio_hook_dur = get_audio_duration(str(vh_path)) if use_hook else 0
        user_hook_dur = opts.get("hook_dur", 1.5)
        cover_duration = max(min(user_hook_dur, 5.0), 0.5) if use_hook else 1.0
        delay_ms = int(cover_duration * 1000)

        log_func(f"[Hook] use_hook={use_hook}, path={voice_hook}, audio_dur={audio_hook_dur:.2f}s, cover_dur={cover_duration:.2f}s")
        log_func(f"[Hook] cover_duration={cover_duration:.2f}s, delay_ms={delay_ms}")
        
        # Scan first few frames for auto-cover
        auto_thumb_img = None
        thumb_img_input_path = BASE_DIR / "input_thumbnail.jpg"
        if not thumb_img_input_path.exists(): thumb_img_input_path = BASE_DIR / "input_thumbnail.png"

        if not thumb_img_input_path.exists():
            update_status("Auto-Cover...")
            log_func(f"[{safe_id}] 🖼️  Generating auto-cover from video...")
            temp_cap = cv2.VideoCapture(str(trimmed))
            best_score = -1
            for _ in range(int(fps * 2)): 
                r, f = temp_cap.read()
                if not r: break
                mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
                res = detector.detect(mp_img)
                if res.detections:
                    score = res.detections[0].categories[0].score
                    if score > best_score:
                        best_score = score
                        ch, cw = int(frame_h/zoom), int(frame_h*9/16/zoom); cw, ch = min(cw, frame_w), min(ch, frame_h)
                        y_off = y_offset_factor if y_offset_factor != 0.35 else 0.4
                        cx, cy = f.shape[1]//2, f.shape[0]//2
                        if res.detections:
                            b = res.detections[0].bounding_box
                            cx, cy = b.origin_x + b.width//2, b.origin_y + b.height//2
                        x1, y1 = max(0, min(int(cx)-cw//2, frame_w-cw)), max(0, min(int(cy)-int(ch*y_off), frame_h-ch))
                        crop = apply_sharpen(cv2.resize(f[y1:y1+ch, x1:x1+cw].copy(), (target_w, target_h), interpolation=cv2.INTER_CUBIC), strength=0.25)
                        eff = apply_vignette(crop, strength=0.35)
                        hsv = cv2.cvtColor(eff, cv2.COLOR_BGR2HSV).astype("float32")
                        hsv[:,:,1] *= 1.15; hsv[:,:,2] *= 1.05
                        eff = cv2.cvtColor(np.clip(hsv, 0, 255).astype("uint8"), cv2.COLOR_HSV2BGR)
                        pil_c = PILImage.fromarray(cv2.cvtColor(eff, cv2.COLOR_BGR2RGB)); d_c = ImageDraw.Draw(pil_c)
                        if judul_opini and pil_font_opini:
                            words_op = judul_opini.upper().split()
                            lines_op = []
                            curr_line_op = ""
                            for w in words_op:
                                test_l = curr_line_op + (" " if curr_line_op else "") + w
                                bbox_op = d_c.textbbox((0, 0), test_l, font=pil_font_opini)
                                if (bbox_op[2] - bbox_op[0]) > (target_w - 120):
                                    lines_op.append(curr_line_op); curr_line_op = w
                                else: curr_line_op = test_l
                            if curr_line_op: lines_op.append(curr_line_op)
                            total_h = len(lines_op) * 100 + 40
                            overlay = PILImage.new('RGBA', pil_c.size, (0,0,0,0)); d_ov = ImageDraw.Draw(overlay)
                            d_ov.rectangle([0, 20, target_w, 20 + total_h], fill=(0,0,0,255))
                            pil_c = PILImage.alpha_composite(pil_c.convert('RGBA'), overlay).convert('RGB'); d_c = ImageDraw.Draw(pil_c)
                            for i, line in enumerate(lines_op):
                                bbox_l = d_c.textbbox((0, 0), line, font=pil_font_opini)
                                tx = (target_w - (bbox_l[2] - bbox_l[0])) // 2
                                ty = 40 + i * 100
                                draw_pro_text(d_c, line, (tx, ty), pil_font_opini, fill=(255, 255, 0), outline_width=8)
                        if watermark:
                            w_t = watermark.upper() if watermark.startswith("@") else f"@{watermark.upper()}"
                            bbox_w = d_c.textbbox((0,0), w_t, font=pil_font_wm)
                            draw_pro_text(d_c, w_t, (target_w-(bbox_w[2]-bbox_w[0])-50, 50), pil_font_wm, outline_width=5)
                        auto_thumb_img = cv2.cvtColor(np.array(pil_c), cv2.COLOR_RGB2BGR)
            temp_cap.release()
            # Reset detector for main loop to avoid timestamp errors
            detector.close()
            detector = vision.FaceDetector.create_from_options(options)

        # --- AUDIO FILTERS WITH SEQUENTIAL SYNC ---
        bgm_p = ensure_bgm(mood, log_func, config=opts.get("config"))
        use_bgm = bgm_p and os.path.exists(bgm_p)

        inputs = [
            "-f", "rawvideo", "-vcodec", "rawvideo",
            "-s", f"{target_w}x{target_h}", "-pix_fmt", "bgr24",
            "-r", str(fps), "-i", "-",
            "-i", str(trimmed)
        ]
        filter_parts = []

        # Silence removal config (must be before audio filter block)
        silence_threshold = opts.get("silence_threshold", 0.6)
        speech_segments = compute_speech_segments(all_words, silence_threshold)
        skip_silent = silence_threshold > 0
        if skip_silent and speech_segments:
            log_func(f"[{safe_id}] ✂️  Silence removal: {len(speech_segments)} speech segments (threshold: {silence_threshold}s)")

        if skip_silent and speech_segments:
            # Cut audio at the SAME speech segments used for video frame skipping
            # aselect keeps only audio in speech regions, asetpts resets timestamps
            select_parts = [f"between(t,{s:.3f},{e:.3f})" for s, e in speech_segments]
            select_expr = "+".join(select_parts)
            filter_parts.append(f"[1:a]aselect='{select_expr}',asetpts=N/SR/TB[a_trimmed]")
            filter_parts.append(f"[a_trimmed]adelay={delay_ms}|{delay_ms}[a_delayed]")
            log_func(f"[{safe_id}] 🔊 Audio trimmed to match video silence removal")
        else:
            # No silence removal - just delay audio to sync with cover
            filter_parts.append(f"[1:a]adelay={delay_ms}|{delay_ms}[a_delayed]")
        audio_map = "[a_delayed]"

        if use_hook:
            # Duck original audio during hook to avoid clash (from t=0)
            filter_parts.append(
                f"[a_delayed]volume='if(between(t,0,{cover_duration}),0.08,1)':eval=frame[orig_adj]"
            )
            inputs += ["-i", str(vh_path)]
            hook_idx = 2
            filter_parts.append(f"[{hook_idx}:a]volume=1.5[hook_adj]")
            filter_parts.append(f"[orig_adj][hook_adj]amix=inputs=2:duration=first[a_voice]")
            audio_map = "[a_voice]"

        if use_bgm:
            bgm_idx = len([x for x in inputs if x == "-i"])
            inputs += ["-stream_loop", "-1", "-i", str(bgm_p)]
            bv = min(max(bgm_volume, 0.05), 0.4)
            duck_vol = 0.08  # BGM volume during speech
            if skip_silent and speech_segments:
                # Dynamic ducking: lower BGM during speech segments
                duck_parts = []
                for s_start, s_end in speech_segments:
                    # Add small padding to make ducking smoother
                    pad = 0.1
                    duck_parts.append(f"if(between(t,{max(0, s_start - pad)},{s_end + pad}),{duck_vol},{bv})")
                # OR: duck when in ANY speech segment
                duck_expr = "+".join(duck_parts)
                filter_parts.append(f"[{bgm_idx}:a]volume='{duck_expr}':eval=frame[bgm_vol]")
                log_func(f"[{safe_id}] 🎵 Dynamic BGM ducking: {len(speech_segments)} speech segments")
            else:
                filter_parts.append(f"[{bgm_idx}:a]volume={bv}[bgm_vol]")
            filter_parts.append(f"{audio_map}[bgm_vol]amix=inputs=2:duration=first:dropout_transition=2[a]")
            audio_map = "[a]"

        vf_final = f"scale={target_w}:{target_h},eq=saturation=1.05:contrast=1.02,fade=t=out:st={dur+cover_duration-0.5}:d=0.5"

        if use_hook or use_bgm:
            fc = ";".join(filter_parts)
            ffmpeg_cmd = ["ffmpeg", "-y"] + inputs + [
                "-filter_complex", fc,
                "-map", "0:v:0", "-map", audio_map,
                "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", rpreset["preset"], "-crf", str(rpreset["crf"]),
                "-movflags", "+faststart", "-c:a", "aac", "-b:a", "128k", "-shortest",
                "-vf", vf_final, "-bsf:v", "h264_metadata=video_full_range_flag=1", str(final_out)
            ]
        else:
            ffmpeg_cmd = ["ffmpeg", "-y"] + inputs + [
                "-map", "0:v:0", "-map", "1:a:0",
                "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", rpreset["preset"], "-crf", str(rpreset["crf"]),
                "-movflags", "+faststart", "-c:a", "aac", "-b:a", "128k", "-shortest",
                "-vf", vf_final, "-af", f"adelay={delay_ms}|{delay_ms},afade=t=out:st={dur+cover_duration-0.5}:d=0.5",
                "-bsf:v", "h264_metadata=video_full_range_flag=1", str(final_out)
            ]
            
        try:
            ffmpeg_proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL)
        except (OSError, ValueError) as e:
            logger.warning("ffmpeg Popen list form failed, falling back to shell: %s", e)
            shell_cmd = ' '.join(str(x) if not any(c in str(x) for c in ' ;()') else f'"{str(x)}"' for x in ffmpeg_cmd)
            ffmpeg_proc = subprocess.Popen(shell_cmd, shell=True, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

        import threading, queue as qmod
        ff_err_q = qmod.Queue()
        def _reader(stream, q):
            try:
                for line in iter(stream.readline, b""): q.put(line)
            finally: stream.close()
        ff_stderr_thread = threading.Thread(target=_reader, args=(ffmpeg_proc.stderr, ff_err_q), daemon=True)
        ff_stderr_thread.start()
        ffmpeg_errored = False

        def fallback_crop(fr, face_info, tw, th):
            fx, fy, fw, fh, _ = face_info
            fch = frame_h
            fcw = int(frame_h * 9 / 16)
            if fcw > frame_w:
                fcw = frame_w
                fch = int(frame_w * 16 / 9)
            fy1 = max(0, min(int(fy - fh * 0.1) - int(fch * 0.25), frame_h - fch))
            fx1 = max(0, min(int(fx) - fcw // 2, frame_w - fcw))
            return cv2.resize(fr[fy1:fy1+fch, fx1:fx1+fcw].copy(), (tw, th), interpolation=cv2.INTER_CUBIC)

        # --- B-ROLL PRE-FETCH ---
        broll_map = {}
        use_broll = opts.get("use_broll", False)
        pk = opts.get("config", {}).get("pexels_api_key")
        if use_broll and pk and all_words:
            update_status("B-Roll Fetch...")
            log_func(f"[{safe_id}] 🎨 Mencari visual keywords untuk B-Roll...")
            keywords = extract_keywords_from_transcript(all_words, opts.get("config"), log_func)
            for ts, kw in keywords:
                log_func(f"   > Keyword: {kw}")
                img_path = fetch_pexels_broll(kw, pk, TEMP_DIR)
                if img_path:
                    try:
                        # Pre-load and resize to top overlay size (target_w x target_h*0.55)
                        ov_h = int(target_h * 0.55)
                        bi = PILImage.open(img_path).convert("RGBA")
                        # Cover aspect ratio logic
                        bw, bh = bi.size
                        ratio = target_w / bw
                        if bh * ratio < ov_h:
                            ratio = ov_h / bh
                        bi = bi.resize((int(bw * ratio), int(bh * ratio)), PILImage.Resampling.LANCZOS)
                        # Crop to center
                        left = (bi.width - target_w) // 2
                        top = (bi.height - ov_h) // 2
                        bi = bi.crop((left, top, left + target_w, top + ov_h))
                        broll_map[ts] = (kw, bi)
                    except (IOError, ValueError):
                        pass
            log_func(f"[{safe_id}] ✅ Berhasil fetch & load {len(broll_map)} B-Roll images.")

        prev_gray = None
        lost_frames = 0
        last_face_pos = (frame_w // 2, frame_h // 2)
        best_thumb_frame = None
        best_thumb_score = -1
        tracker = SpeakerTracker()
        # Performance: frame skipping for face detection
        DETECT_EVERY_N = 3  # detect face every N frames
        cached_face_list = []
        cached_gray_small = None
        max_score_in_frame_cached = 0
        render_start_time = time.time()
        avg_frame_time = 0.033  # initial estimate ~30fps

        # Insert Thumbnail (Framing Cover) at Frame 0
        if thumb_img_input_path.exists():
            update_status("Cover Frame...")
            log_func(f"[{safe_id}] 🖼️  Inserting manual thumbnail cover...")
            t_img = cv2.imread(str(thumb_img_input_path))
            if t_img is not None:
                t_resized = cv2.resize(t_img, (target_w, target_h), interpolation=cv2.INTER_CUBIC)
                cover_pil = PILImage.fromarray(cv2.cvtColor(t_resized, cv2.COLOR_BGR2RGB))
                c_draw = ImageDraw.Draw(cover_pil, 'RGBA')
                for row in range(int(target_h * 0.55), target_h):
                    alpha = int(180 * ((row - target_h * 0.55) / (target_h * 0.45)))
                    c_draw.line([(0, row), (target_w, row)], fill=(0, 0, 0, alpha))
                # Blur region where text will go
                blur_region = np.array(cover_pil)[int(target_h*0.65):int(target_h*0.85), :, :3]
                if blur_region.size > 0:
                    blurred = cv2.GaussianBlur(blur_region, (25, 25), 10)
                    cover_np = np.array(cover_pil)
                    cover_np[int(target_h*0.65):int(target_h*0.85), :, :3] = blurred
                else:
                    cover_np = np.array(cover_pil)
                t_resized = cv2.cvtColor(cover_np, cv2.COLOR_RGB2BGR)
                for _ in range(int(fps * cover_duration)): 
                    ffmpeg_proc.stdin.write(t_resized.tobytes())
        elif auto_thumb_img is not None:
            update_status("Auto-Cover...")
            log_func(f"[{safe_id}] 🖼️  Inserting auto-cover...")
            for _ in range(int(fps * cover_duration)):
                ffmpeg_proc.stdin.write(auto_thumb_img.tobytes())

        logo_logged = False
        emphasis_indices = detect_emphasis_words(all_words)
        ZOOM_PUNCH_FACTOR = 1.08
        ZOOM_PUNCH_DURATION = 0.3
        zoom_punch_state = {"active": False, "end_time": 0}
        for frame_num in range(total_frames):
            ret, frame = cap.read()
            if not ret: break
            # Auto-rotate landscape to portrait
            if needs_rotate:
                frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
            cur_time = frame_num / fps

            # Silence removal: skip frames outside speech segments
            if skip_silent and not is_in_speech_segment(cur_time, speech_segments):
                continue

            active_word_idx = -1
            for wi, wd in enumerate(all_words):
                if wd["start"] <= cur_time <= wd["end"]:
                    active_word_idx = wi
                    break
            curr_word = all_words[active_word_idx] if 0 <= active_word_idx < len(all_words) else None

            # Performance: skip face detection every N frames, reuse cached result
            detect_this_frame = (frame_num % DETECT_EVERY_N == 0)
            if detect_this_frame:
                # Downscale for faster detection (use 320px width max)
                det_scale = min(1.0, 320.0 / frame_w)
                det_w, det_h = int(frame_w * det_scale), int(frame_h * det_scale)
                det_frame = cv2.resize(frame, (det_w, det_h), interpolation=cv2.INTER_AREA)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(det_frame, cv2.COLOR_BGR2RGB))
                results = detector.detect(mp_image)

                face_list = []
                max_score_in_frame = 0
                if results.detections:
                    for det in results.detections:
                        score = det.categories[0].score if det.categories else 0
                        if score < 0.5: continue
                        if score > max_score_in_frame: max_score_in_frame = score
                        b = det.bounding_box
                        # Scale back to original resolution
                        face_list.append(((b.origin_x + b.width // 2) / det_scale, (b.origin_y + b.height // 2) / det_scale, b.width / det_scale, b.height / det_scale, score))
                    face_list.sort(key=lambda f: f[4], reverse=True)
                cached_face_list = face_list
                max_score_in_frame_cached = max_score_in_frame
            else:
                face_list = cached_face_list
                max_score_in_frame = max_score_in_frame_cached

            gray_small = cv2.cvtColor(cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), (0,0), fx=0.25, fy=0.25), cv2.COLOR_RGB2GRAY)

            # --- Dynamic camera: 1 person center lock, 2+ speaker cut + grid on overlap ---
            is_grid_mode = False
            # APPLY ZOOM FACTOR with optional zoom punch on emphasis words
            effective_zoom = zoom
            if active_word_idx in emphasis_indices:
                if not zoom_punch_state["active"]:
                    zoom_punch_state["active"] = True
                    zoom_punch_state["end_time"] = cur_time + ZOOM_PUNCH_DURATION
            if zoom_punch_state["active"]:
                if cur_time < zoom_punch_state["end_time"]:
                    # Ease-in-out zoom punch
                    progress = (cur_time - (zoom_punch_state["end_time"] - ZOOM_PUNCH_DURATION)) / ZOOM_PUNCH_DURATION
                    if progress < 0.5:
                        punch = 1.0 + (ZOOM_PUNCH_FACTOR - 1.0) * (progress * 2)
                    else:
                        punch = ZOOM_PUNCH_FACTOR - (ZOOM_PUNCH_FACTOR - 1.0) * ((progress - 0.5) * 2)
                    effective_zoom = zoom * punch
                else:
                    zoom_punch_state["active"] = False
            ch = int(frame_h / effective_zoom)
            cw = int(ch * 9 / 16)
            if cw > frame_w:
                cw = frame_w
                ch = int(frame_w * 16 / 9)
            x1 = (frame_w - cw) // 2
            y1 = 0
            if len(face_list) >= 1:
                lost_frames = 0
                if len(face_list) == 1:
                    fx, fy, fw, fh, _ = face_list[0]
                    # Dynamic crop based on face and zoom
                    y1 = max(0, min(int(fy - fh * 0.1) - int(ch * 0.35), frame_h - ch))
                    x1 = max(0, min(int(fx) - cw // 2, frame_w - cw))
                    face_top = fy - fh * 0.5
                    if y1 > face_top - 60:
                        y1 = max(0, int(face_top) - 60)
                    # Stabilize camera position
                    x1, y1 = get_stabilized_pos(x1, y1)
                    resized = apply_sharpen(cv2.resize(frame[y1:y1+ch, x1:x1+cw].copy(), (target_w, target_h), interpolation=cv2.INTER_CUBIC), strength=0.25)
                else:
                    motions = []
                    for fx2, fy2, fw2, fh2, _ in face_list:
                        mx1 = max(0, int((fx2-fw2*0.4)*0.5))
                        mx2 = min(gray_small.shape[1], int((fx2+fw2*0.4)*0.5))
                        my1 = max(0, int((fy2+fh2*0.2)*0.5))
                        my2 = min(gray_small.shape[0], int((fy2+fh2*0.5)*0.5))
                        mot = 0
                        if prev_gray is not None and my2 > my1 and mx2 > mx1:
                            flow = cv2.calcOpticalFlowFarneback(prev_gray[my1:my2, mx1:mx2], gray_small[my1:my2, mx1:mx2], None, 0.5, 3, 15, 3, 5, 1.2, 0)
                            mag, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1]); mv = mag[mag > 0.3]
                            mot = float(np.mean(mv)) if len(mv) > 0 else 0
                        motions.append(mot)
                    
                    curr_word_active = curr_word is not None
                    for i, fs in enumerate(tracker.faces):
                        if i < len(motions): fs.mouth_motion = motions[i]
                    best_idx, both_active = tracker.update(face_list, frame_num, curr_word_active, active_word_idx, fps)

                    if both_active or (split_screen and len(face_list) >= 2):
                        is_grid_mode = True
                        grid_result = render_grid_layout(frame, face_list, target_w, target_h)
                        resized = grid_result if grid_result is not None else fallback_crop(frame, face_list[0], target_w, target_h)
                        resized = apply_sharpen(resized, strength=0.25)
                    else:
                        target_face = face_list[best_idx]
                        fx, fy, fw, fh, _ = target_face
                        y1 = max(0, min(int(fy - fh * 0.1) - int(ch * 0.35), frame_h - ch))
                        x1 = max(0, min(int(fx) - cw // 2, frame_w - cw))
                        if y1 > (fy - fh * 0.5) - 60: y1 = max(0, int(fy - fh * 0.5) - 60)
                        # Stabilize camera position
                        x1, y1 = get_stabilized_pos(x1, y1)
                        resized = apply_sharpen(cv2.resize(frame[y1:y1+ch, x1:x1+cw].copy(), (target_w, target_h), interpolation=cv2.INTER_CUBIC), strength=0.25)
                    last_face_pos = (fx, fy)
                prev_gray = gray_small
            else:
                lost_frames += 1; prev_gray = gray_small
                if lost_frames < int(fps * 1.5):
                    fx, fy = last_face_pos
                    y1 = max(0, min(int(fy) - int(ch * 0.35), frame_h - ch))
                    x1 = max(0, min(int(fx) - cw // 2, frame_w - cw))
                    # Stabilize camera position
                    x1, y1 = get_stabilized_pos(x1, y1)
                    resized = apply_sharpen(cv2.resize(frame[y1:y1+ch, x1:x1+cw].copy(), (target_w, target_h), interpolation=cv2.INTER_CUBIC), strength=0.25)
                else:
                    x1, y1 = (frame_w - cw) // 2, (frame_h - ch) // 2
                    x1, y1 = get_stabilized_pos(x1, y1)
                    resized = apply_sharpen(cv2.resize(frame[y1:y1+ch, x1:x1+cw].copy(), (target_w, target_h), interpolation=cv2.INTER_CUBIC), strength=0.25)

            # Apply Cinematic Effects (Vignette + Color Grading)
            frame_effects = apply_vignette(resized, strength=tpl.get("vignette", 0.5))
            frame_effects = apply_cinematic_grade(frame_effects)

            img_pil = PILImage.fromarray(cv2.cvtColor(frame_effects, cv2.COLOR_BGR2RGB)); draw = ImageDraw.Draw(img_pil)

            # Black gradient bottom 3/4 layar
            grad_ov = PILImage.new('RGBA', (target_w, target_h), (0,0,0,0))
            gd = ImageDraw.Draw(grad_ov)
            grad_start = int(target_h * tpl.get("grad_start", 0.75))
            for row in range(grad_start, target_h):
                progress = (row - grad_start) / (target_h - grad_start)
                alpha = int(200 * progress ** 2.5)
                if alpha > 0:
                    gd.line([(0, row), (target_w, row)], fill=(0, 0, 0, alpha))
            img_pil = PILImage.alpha_composite(img_pil.convert('RGBA'), grad_ov).convert('RGB')
            draw = ImageDraw.Draw(img_pil)
            
            # --- B-ROLL OVERLAY ---
            for ts, (kw, b_img) in broll_map.items():
                if ts <= cur_time < ts + 4.0:
                    # Fade in/out 0.5s
                    b_alpha = 255
                    if cur_time < ts + 0.5:
                        b_alpha = int(255 * (cur_time - ts) / 0.5)
                    elif cur_time > ts + 3.5:
                        b_alpha = int(255 * (ts + 4.0 - cur_time) / 0.5)
                    
                    # Overlay at top (0 to 55%)
                    b_ov = PILImage.new('RGBA', img_pil.size, (0,0,0,0))
                    b_ov.paste(b_img, (0, 0))
                    
                    # Apply alpha
                    if b_alpha < 255:
                        # Simple way to apply alpha to whole image
                        b_ov_np = np.array(b_ov)
                        b_ov_np[..., 3] = (b_ov_np[..., 3].astype(float) * (b_alpha / 255)).astype(np.uint8)
                        b_ov = PILImage.fromarray(b_ov_np)
                    
                    img_pil = PILImage.alpha_composite(img_pil.convert('RGBA'), b_ov).convert('RGB')
                    draw = ImageDraw.Draw(img_pil)
                    
                    # Label keyword in corner
                    draw_pro_text(draw, kw, (30, 30), pil_font_wm, fill=(255, 255, 255), outline_width=4)
                    break # Only one B-roll at a time

            # Render Judul Opini — ALL frames, fade-out after 5s
            judul_alpha = 255
            if cur_time > 5.0:
                fade_progress = min(1.0, (cur_time - 5.0) / 1.5)
                judul_alpha = int(255 * (1.0 - fade_progress))
            if judul_opini and pil_font_opini and judul_alpha > 0:
                words_op = judul_opini.upper().split()
                lines_op = []
                curr_line_op = ""
                try:
                    pil_font_opini_small = ImageFont.truetype(pil_font_opini.path, 65)
                except (OSError, IOError, ValueError) as e:
                    pil_font_opini_small = pil_font_opini
                    logger.debug("Opini font fallback: %s", e)
                for w in words_op:
                    test_l = curr_line_op + (" " if curr_line_op else "") + w
                    bbox_op = draw.textbbox((0, 0), test_l, font=pil_font_opini)
                    if (bbox_op[2] - bbox_op[0]) > (target_w - 120):
                        lines_op.append(curr_line_op)
                        curr_line_op = w
                    else:
                        curr_line_op = test_l
                if curr_line_op: lines_op.append(curr_line_op)

                line_heights = []
                max_line_w = 0
                for line in lines_op:
                    bl = draw.textbbox((0,0), line, font=pil_font_opini)
                    line_heights.append(bl[3]-bl[1])
                    max_line_w = max(max_line_w, bl[2]-bl[0])

                total_text_h = sum(line_heights) + (len(lines_op)-1) * 15
                # Center text vertically around 40% from top, no black background
                text_start_y = int(target_h * 0.38) - total_text_h // 2
                if text_start_y < 20:
                    text_start_y = 20

                for i, line in enumerate(lines_op):
                    if i == 0:
                        f = pil_font_opini
                        color = "#FFE600"
                        outline = 12
                    else:
                        f = pil_font_opini_small
                        color = "#FFFFFF"
                        outline = 10
                    bbox_l = draw.textbbox((0, 0), line, font=f)
                    tx_op = (target_w - (bbox_l[2] - bbox_l[0])) // 2
                    ty_op = text_start_y + i * int((bbox_l[3] - bbox_l[1]) + 15)
                    draw_pro_text(draw, line, (tx_op, ty_op), f, fill=color, outline_width=outline,
                                  shadow_offset=(5, 7), shadow_alpha=160)

            # Hook text overlay: render AI hook in first 3 seconds
            HOOK_DISPLAY_DURATION = 3.0
            if hook_text and cur_time < HOOK_DISPLAY_DURATION:
                # Fade out in last 0.5s
                hook_alpha = 255
                if cur_time > HOOK_DISPLAY_DURATION - 0.5:
                    hook_alpha = int(255 * (HOOK_DISPLAY_DURATION - cur_time) / 0.5)
                hook_words = hook_text.upper().split()
                hook_lines = []
                curr_hook_line = ""
                try:
                    hook_font = ImageFont.truetype(pil_font.path, 55)
                except (OSError, IOError):
                    hook_font = pil_font
                for w in hook_words:
                    test_l = curr_hook_line + (" " if curr_hook_line else "") + w
                    bbox_h = draw.textbbox((0, 0), test_l, font=hook_font)
                    if (bbox_h[2] - bbox_h[0]) > (target_w - 100):
                        hook_lines.append(curr_hook_line)
                        curr_hook_line = w
                    else:
                        curr_hook_line = test_l
                if curr_hook_line: hook_lines.append(curr_hook_line)
                hook_total_h = len(hook_lines) * 70
                hook_y_start = int(target_h * 0.25) - hook_total_h // 2
                hook_ov = PILImage.new('RGBA', img_pil.size, (0, 0, 0, 0))
                hook_draw = ImageDraw.Draw(hook_ov)
                # Background pill
                hook_draw.rounded_rectangle(
                    [40, hook_y_start - 20, target_w - 40, hook_y_start + hook_total_h + 20],
                    radius=20, fill=(0, 0, 0, int(180 * hook_alpha / 255))
                )
                img_pil = PILImage.alpha_composite(img_pil.convert('RGBA'), hook_ov).convert('RGB')
                draw = ImageDraw.Draw(img_pil)
                for i, line in enumerate(hook_lines):
                    bbox_hl = draw.textbbox((0, 0), line, font=hook_font)
                    hx = (target_w - (bbox_hl[2] - bbox_hl[0])) // 2
                    hy = hook_y_start + i * 70
                    # Yellow text with black outline
                    draw.text((hx, hy), line, font=hook_font, fill=(0, 0, 0), stroke_width=8, stroke_fill=(0, 0, 0))
                    draw.text((hx, hy), line, font=hook_font, fill=(*tpl.get("active_color", (255, 230, 0)), hook_alpha))

            # Watermark with pill background + optional logo
            wm_text = ""
            if watermark:
                wm_text = watermark.upper() if watermark.startswith("@") else f"@{watermark.upper()}"
            if img_logo or wm_text:
                wm_ov = PILImage.new('RGBA', img_pil.size, (0,0,0,0))
                wm_d = ImageDraw.Draw(wm_ov)
                logo_w = 80 if img_logo else 0
                if wm_text:
                    bw = draw.textbbox((0, 0), wm_text, font=pil_font_wm)
                    tw = bw[2] - bw[0]
                else:
                    tw = 0
                pill_w = logo_w + (12 if logo_w > 0 and wm_text else 0) + tw + 30
                pill_h = logo_w + 10 if img_logo else 50
                pill_x = target_w - pill_w - 20
                pill_y = 20

                if not logo_logged and img_logo:
                    log_func(f"[Logo] size={img_logo.size}, pos=({pill_x},{pill_y})")
                    logo_logged = True

                wm_d.rounded_rectangle([pill_x, pill_y, pill_x + pill_w, pill_y + pill_h],
                                       radius=25, fill=(0, 0, 0, 77))
                img_pil = PILImage.alpha_composite(img_pil.convert('RGBA'), wm_ov).convert('RGB')
                draw = ImageDraw.Draw(img_pil)
                cur_x = pill_x + 15
                if img_logo:
                    logo_small = img_logo.resize((logo_w, logo_w), PILImage.Resampling.LANCZOS)
                    img_pil_rgba = img_pil.convert('RGBA')
                    img_pil_rgba.paste(logo_small, (cur_x, pill_y + 5), logo_small)
                    img_pil = img_pil_rgba.convert('RGB')
                    draw = ImageDraw.Draw(img_pil)
                    cur_x += logo_w + 12
                if wm_text:
                    bw = draw.textbbox((0, 0), wm_text, font=pil_font_wm)
                    th = bw[3] - bw[1]
                    wy = pill_y + (pill_h - th) // 2
                    draw_pro_text(draw, wm_text, (cur_x, wy), pil_font_wm, outline_width=4,
                                  shadow_offset=(3, 4), shadow_alpha=120)
            
            if pil_font is not None and active_word_idx >= 0:
                draw_karaoke_line(img_pil, draw, all_words, active_word_idx, pil_font, target_w, target_h, outline_w=tpl.get("outline_w", 14), frame_num=frame_num, fps=fps, template=tpl)
            
            # Render Pro Progress Bar at the bottom
            bar_h = 6
            bar_w = int((frame_num / total_frames) * target_w)
            draw.rectangle([0, target_h - bar_h, target_w, target_h], fill=(40, 40, 60))
            draw.rectangle([0, target_h - bar_h, bar_w, target_h], fill=(255, 230, 0))

            # End-card overlay in last 3 seconds
            if end_card_enabled and cur_time > dur - 3.0:
                ec_progress = min(1.0, (cur_time - (dur - 3.0)) / 1.0)
                draw_end_card(img_pil, draw, pil_font_wm, target_w, target_h, end_card_text, ec_progress)

            if max_score_in_frame > best_thumb_score and frame_num < int(fps * 10):
                best_thumb_score = max_score_in_frame
                best_thumb_frame = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)

            if ffmpeg_proc.poll() is not None:
                if not ffmpeg_errored:
                    ffmpeg_errored = True
                    stderr_lines = []
                    while not ff_err_q.empty(): stderr_lines.append(ff_err_q.get_nowait().decode("utf-8", errors="replace"))
                    log_func(f"[{safe_id}] ❌ FFmpeg died at frame {frame_num}/{total_frames}. Error: {''.join(stderr_lines)[-300:]}")
                break
            ffmpeg_pil = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
            ffmpeg_proc.stdin.write(ffmpeg_pil.tobytes())
            if frame_num % 20 == 0:
                elapsed = time.time() - render_start_time
                avg_frame_time = elapsed / (frame_num + 1)
                eta_sec = avg_frame_time * (total_frames - frame_num)
                eta_min = int(eta_sec // 60)
                eta_s = int(eta_sec % 60)
                progress_func(int((frame_num/total_frames)*100))
                update_status(f"Rendering... ETA {eta_min}m {eta_s}s")
                try:
                    root = opts.get("root")
                    if root: root.after(0, root.update_idletasks)
                except (RuntimeError, TclError) as e:
                    logger.debug("GUI update skipped: %s", e)

        cap.release()
        if not ffmpeg_errored:
            try: ffmpeg_proc.stdin.close()
            except (OSError, BrokenPipeError) as e:
                logger.debug("ffmpeg stdin close: %s", e)
            
            # SAVE SMART THUMBNAIL (optional)
            gen_thumb = opts.get("gen_thumb", True)
            if gen_thumb and best_thumb_frame is not None:
                log_func(f"[{safe_id}] 🖼️  Saving smart thumbnail...")
                cv2.imwrite(str(thumb_path), best_thumb_frame)

        ffmpeg_proc.wait(timeout=30)
        ff_stderr_thread.join(timeout=2)

        for f in [trimmed, audio_wav]:
            if f.exists(): f.unlink()

        if ffmpeg_errored or ffmpeg_proc.returncode != 0:
            log_func(f"[{safe_id}] ❌ Rendering gagal.")
            return False, "FFmpeg error"

        with open(desc_path, "w", encoding="utf-8") as df:
            df.write(f"{'='*50}\n")
            df.write(f"📌 JUDUL: {title.upper()}\n")
            df.write(f"{'='*50}\n\n")
            df.write(f"📝 DESKRIPSI:\n{ai_desc}\n\n")
            df.write(f"{'─'*40}\n")
            df.write(f"🔗 LINK ASLI: {link}\n")
            df.write(f"⏱ TIMESTAMP: {start_sec}s - {end_sec}s\n")
            df.write(f"📅 DIBUAT: {time.strftime('%d-%m-%Y %H:%M')}\n")
            df.write(f"{'─'*40}\n")
            df.write(f"\n#Shorts #Viral #Edukasi #FYP #Trending\n")
        log_func(f"[{safe_id}] ✅ Selesai -> {final_out.name}"); return True, str(final_out)
    except Exception as e:
        logger.error("process_single_video failed [%s]: %s", safe_id, traceback.format_exc())
        log_func(f"[{safe_id}] ❌ {str(e)}"); return False, str(e)

class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, parent, config, on_save):
        super().__init__(parent); self.title("Settings"); self.geometry("620x950"); self.config = config; self.on_save = on_save
        self.configure(fg_color="#1e1e2e")
        self.grid_columnconfigure(1, weight=1); r = 0
        ctk.CTkLabel(self, text="AI Provider:", font=("Arial", 14, "bold"), text_color="#ddd").grid(row=r, column=0, padx=20, pady=10, sticky="w")
        self.p_var = ctk.StringVar(value=config.get("ai_provider", "Gemini (Native)")); self.p_cb = ctk.CTkComboBox(self, values=["Gemini (Native)", "OpenRouter (DeepSeek/GPT/etc)", "Groq"], variable=self.p_var, command=self.toggle_ai, width=300, corner_radius=8); self.p_cb.grid(row=r, column=1, padx=20, pady=10, sticky="ew"); r += 1
        self.g_f = ctk.CTkFrame(self, fg_color="transparent"); self.g_f.grid(row=r, column=0, columnspan=2, sticky="ew", padx=20, pady=5); self.g_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self.g_f, text="Gemini API Key:", text_color="#aaa").grid(row=0, column=0, padx=10, pady=5, sticky="w"); self.gk_var = ctk.StringVar(value=config.get("gemini_api_key", "")); ctk.CTkEntry(self.g_f, textvariable=self.gk_var, width=300, show="*", corner_radius=8).grid(row=0, column=1, padx=10, pady=5, sticky="ew")
        ctk.CTkLabel(self.g_f, text="Gemini Model:", text_color="#aaa").grid(row=1, column=0, padx=10, pady=5, sticky="w"); self.gm_var = ctk.StringVar(value=config.get("gemini_model", "gemini-2.0-flash")); ctk.CTkComboBox(self.g_f, values=["gemini-2.0-flash", "gemini-1.5-flash"], variable=self.gm_var, width=300, corner_radius=8).grid(row=1, column=1, padx=10, pady=5, sticky="ew")
        self.o_f = ctk.CTkFrame(self, fg_color="transparent"); self.o_f.grid(row=r, column=0, columnspan=2, sticky="ew", padx=20, pady=5); self.o_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self.o_f, text="OpenRouter Key:", text_color="#aaa").grid(row=0, column=0, padx=10, pady=5, sticky="w"); self.ok_var = ctk.StringVar(value=config.get("openrouter_api_key", "")); ctk.CTkEntry(self.o_f, textvariable=self.ok_var, width=300, show="*", corner_radius=8).grid(row=0, column=1, padx=10, pady=5, sticky="ew")
        ctk.CTkLabel(self.o_f, text="Model ID:", text_color="#aaa").grid(row=1, column=0, padx=10, pady=5, sticky="w"); self.om_var = ctk.StringVar(value=config.get("openrouter_model", "nvidia/nemotron-3-super-120b-a12b:free")); ctk.CTkEntry(self.o_f, textvariable=self.om_var, width=300, corner_radius=8).grid(row=1, column=1, padx=10, pady=5, sticky="ew")
        self.gr_f = ctk.CTkFrame(self, fg_color="transparent"); self.gr_f.grid(row=r, column=0, columnspan=2, sticky="ew", padx=20, pady=5); self.gr_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self.gr_f, text="Groq API Key:", text_color="#aaa").grid(row=0, column=0, padx=10, pady=5, sticky="w"); self.grk_var = ctk.StringVar(value=config.get("groq_api_key", "")); ctk.CTkEntry(self.gr_f, textvariable=self.grk_var, width=300, show="*", corner_radius=8).grid(row=0, column=1, padx=10, pady=5, sticky="ew")
        ctk.CTkLabel(self.gr_f, text="Model ID:", text_color="#aaa").grid(row=1, column=0, padx=10, pady=5, sticky="w"); self.grm_var = ctk.StringVar(value=config.get("groq_model", "llama-3.3-70b-versatile")); ctk.CTkEntry(self.gr_f, textvariable=self.grm_var, width=300, corner_radius=8).grid(row=1, column=1, padx=10, pady=5, sticky="ew"); r += 1
        ctk.CTkLabel(self, text="Whisper Provider:", font=("Arial", 13, "bold"), text_color="#ddd").grid(row=r, column=0, padx=20, pady=10, sticky="w")
        self.wp_var = ctk.StringVar(value=config.get("whisper_provider", "Local (faster-whisper)"))
        ctk.CTkComboBox(self, values=["OpenRouter", "Local (faster-whisper)"], variable=self.wp_var, width=300, corner_radius=8).grid(row=r, column=1, padx=20, pady=10, sticky="ew"); r += 1
        ctk.CTkLabel(self, text="Whisper Model (API):", font=("Arial", 13), text_color="#aaa").grid(row=r, column=0, padx=20, pady=5, sticky="w")
        self.wm_var = ctk.StringVar(value=config.get("whisper_model", "openai/whisper-1"))
        ctk.CTkEntry(self, textvariable=self.wm_var, width=300, corner_radius=8).grid(row=r, column=1, padx=20, pady=5, sticky="ew"); r += 1
        ctk.CTkLabel(self, text="Cookies:", font=("Arial", 13), text_color="#ddd").grid(row=r, column=0, padx=20, pady=10, sticky="w"); self.c_var = ctk.StringVar(value=config.get("cookies_path", "")); f_c = ctk.CTkFrame(self, fg_color="transparent"); f_c.grid(row=r, column=1, padx=20, pady=10, sticky="ew"); f_c.grid_columnconfigure(0, weight=1); ctk.CTkEntry(f_c, textvariable=self.c_var, corner_radius=8).grid(row=0, column=0, padx=(0,5), sticky="ew"); ctk.CTkButton(f_c, text="📁", width=50, command=self.browse_cookies, fg_color="#3a3d4e", corner_radius=8).grid(row=0, column=1); r += 1
        ctk.CTkLabel(self, text="Watermark:", font=("Arial", 13), text_color="#ddd").grid(row=r, column=0, padx=20, pady=10, sticky="w"); self.w_var = ctk.StringVar(value=config.get("watermark", "")); ctk.CTkEntry(self, textvariable=self.w_var, width=300, corner_radius=8).grid(row=r, column=1, padx=20, pady=10, sticky="ew"); r += 1
        ctk.CTkLabel(self, text="Pexels API Key:", font=("Arial", 13), text_color="#ddd").grid(row=r, column=0, padx=20, pady=10, sticky="w"); self.pk_var = ctk.StringVar(value=config.get("pexels_api_key", "")); ctk.CTkEntry(self, textvariable=self.pk_var, width=300, corner_radius=8, show="*").grid(row=r, column=1, padx=20, pady=10, sticky="ew"); r += 1
        ctk.CTkLabel(self, text="BGM Volume:", font=("Arial", 13), text_color="#ddd").grid(row=r, column=0, padx=20, pady=10, sticky="w"); self.bv_var = ctk.DoubleVar(value=config.get("bgm_volume", 0.15)); ctk.CTkSlider(self, from_=0, to=1, variable=self.bv_var, width=300).grid(row=r, column=1, padx=20, pady=10, sticky="ew"); r += 1
        ctk.CTkLabel(self, text="Logo:", font=("Arial", 13), text_color="#ddd").grid(row=r, column=0, padx=20, pady=10, sticky="w"); self.l_var = ctk.StringVar(value=config.get("logo_path", "")); f_l = ctk.CTkFrame(self, fg_color="transparent"); f_l.grid(row=r, column=1, padx=20, pady=10, sticky="ew"); f_l.grid_columnconfigure(0, weight=1); ctk.CTkEntry(f_l, textvariable=self.l_var, corner_radius=8).grid(row=0, column=0, padx=(0,5), sticky="ew"); ctk.CTkButton(f_l, text="🖼️", width=50, command=self.browse_logo, fg_color="#3a3d4e", corner_radius=8).grid(row=0, column=1); r += 1
        ctk.CTkLabel(self, text="Font:", font=("Arial", 13), text_color="#ddd").grid(row=r, column=0, padx=20, pady=10, sticky="w");         self.f_opts = list_available_fonts(); self.f_var = ctk.StringVar(value=config.get("subtitle_font", "KOMIKAX_.ttf")); ctk.CTkComboBox(self, values=self.f_opts, variable=self.f_var, width=300, corner_radius=8).grid(row=r, column=1, padx=20, pady=10, sticky="ew"); r += 1
        # --- Render Settings ---
        ctk.CTkLabel(self, text="Render Quality:", font=("Arial", 14, "bold"), text_color="#ddd").grid(row=r, column=0, padx=20, pady=10, sticky="w")
        self.rq_var = ctk.StringVar(value=config.get("render_quality", "normal"))
        ctk.CTkComboBox(self, values=["draft", "normal", "high"], variable=self.rq_var, width=300, corner_radius=8).grid(row=r, column=1, padx=20, pady=10, sticky="ew"); r += 1
        ctk.CTkLabel(self, text="Template:", font=("Arial", 14, "bold"), text_color="#ddd").grid(row=r, column=0, padx=20, pady=10, sticky="w")
        self.tpl_var = ctk.StringVar(value=config.get("template", "cinematic"))
        ctk.CTkComboBox(self, values=list(TEMPLATES.keys()), variable=self.tpl_var, width=300, corner_radius=8).grid(row=r, column=1, padx=20, pady=10, sticky="ew"); r += 1
        ctk.CTkLabel(self, text="Export Resolusi:", font=("Arial", 13), text_color="#ddd").grid(row=r, column=0, padx=20, pady=10, sticky="w")
        self.er_var = ctk.StringVar(value=config.get("export_resolution", "1080x1920"))
        ctk.CTkComboBox(self, values=["1080x1920", "720x1280"], variable=self.er_var, width=300, corner_radius=8).grid(row=r, column=1, padx=20, pady=10, sticky="ew"); r += 1
        ctk.CTkLabel(self, text="Silence Threshold (detik):", font=("Arial", 13), text_color="#ddd").grid(row=r, column=0, padx=20, pady=10, sticky="w")
        self.st_var = ctk.DoubleVar(value=config.get("silence_threshold", 0.6))
        ctk.CTkSlider(self, from_=0.0, to=1.5, variable=self.st_var, width=200).grid(row=r, column=1, padx=20, pady=10, sticky="w")
        ctk.CTkLabel(self, textvariable=self.st_var, text_color="#aaa", width=40).grid(row=r, column=1, padx=(220,0), pady=10, sticky="w"); r += 1
        self.ec_var = ctk.BooleanVar(value=config.get("end_card", True))
        ctk.CTkCheckBox(self, text="End Card (CTA di akhir video)", variable=self.ec_var, fg_color="#4b6e9c").grid(row=r, column=0, columnspan=2, padx=20, pady=5, sticky="w"); r += 1
        ctk.CTkLabel(self, text="End Card Text:", font=("Arial", 13), text_color="#ddd").grid(row=r, column=0, padx=20, pady=5, sticky="w")
        self.ec_text_var = ctk.StringVar(value=config.get("end_card_text", "Follow for more!"))
        ctk.CTkEntry(self, textvariable=self.ec_text_var, width=300, corner_radius=8).grid(row=r, column=1, padx=20, pady=5, sticky="ew"); r += 1

        # Subtitle Preview Button
        ctk.CTkButton(self, text="👁️ Preview Subtitle Style", command=self.preview_subtitle, fg_color="#4b6e9c", hover_color="#3a5a7a", corner_radius=8).grid(row=r, column=0, columnspan=2, padx=20, pady=10); r += 1

        b_f = ctk.CTkFrame(self, fg_color="transparent"); b_f.grid(row=r, column=0, columnspan=2, pady=30); ctk.CTkButton(b_f, text="💾 Save", command=self.save, fg_color="#2e8b57", hover_color="#236b43", corner_radius=8, width=100).pack(side="left", padx=20); ctk.CTkButton(b_f, text="Cancel", fg_color="#555", hover_color="#444", corner_radius=8, width=100, command=self.destroy).pack(side="left", padx=20); self.toggle_ai(self.p_var.get())
    def toggle_ai(self, c):
        self.g_f.grid_remove(); self.o_f.grid_remove(); self.gr_f.grid_remove()
        if c == "Gemini (Native)": self.g_f.grid()
        elif c == "Groq": self.gr_f.grid()
        else: self.o_f.grid()
    def browse_logo(self):
        p = filedialog.askopenfilename(filetypes=[("Image", "*.png *.jpg *.jpeg"), ("PNG", "*.png"), ("JPEG", "*.jpg *.jpeg")])
        if p: self.l_var.set(p)
    def browse_cookies(self):
        p = filedialog.askopenfilename(filetypes=[("TXT", "*.txt")])
        if p: self.c_var.set(p)
    def preview_subtitle(self):
        try:
            font_name = self.f_var.get()
            font_path = str(BASE_DIR / "fonts" / font_name)
            if not os.path.exists(font_path):
                font_path = "C:/Windows/Fonts/impact.ttf"
            tpl_name = self.tpl_var.get()
            tpl = TEMPLATES.get(tpl_name, TEMPLATES["cinematic"])
            preview = PILImage.new('RGB', (400, 700), (30, 30, 50))
            draw = ImageDraw.Draw(preview)
            font = ImageFont.truetype(font_path, 40)
            font_small = ImageFont.truetype(font_path, 28)
            sample = "CONTOH SUBTITLE KARAOKE"
            words = sample.split()
            cx = 200
            y_pos = 500
            for w in words:
                is_a = w == "KARAOKE"
                c = tpl.get("active_color", (255, 230, 0)) if is_a else tpl.get("inactive_color", (255, 255, 255))
                f = font if is_a else font_small
                bbox = draw.textbbox((0, 0), w, font=f)
                ww = bbox[2] - bbox[0]
                draw.text((cx - ww//2 + 2, y_pos + 2), w, font=f, fill=(0, 0, 0))
                draw.text((cx - ww//2, y_pos), w, font=f, fill=c)
                cx += ww + 15
            draw.text((10, 10), f"Template: {tpl_name}", font=font_small, fill=(150, 150, 150))
            draw.text((10, 50), f"Font: {font_name}", font=font_small, fill=(150, 150, 150))
            draw.text((10, 90), f"Aktif: {tpl.get('active_color')}", font=font_small, fill=tpl.get("active_color", (255,255,255)))
            draw.text((10, 130), f"Non-aktif: {tpl.get('inactive_color')}", font=font_small, fill=tpl.get("inactive_color", (200,200,200)))
            preview.show()
        except Exception as e:
            messagebox.showerror("Preview Error", str(e))
    def save(self):
        nc = {"ai_provider": self.p_var.get(), "gemini_api_key": self.gk_var.get().strip(), "gemini_model": self.gm_var.get(), "openrouter_api_key": self.ok_var.get().strip(), "openrouter_model": self.om_var.get().strip(), "groq_api_key": self.grk_var.get().strip(), "groq_model": self.grm_var.get().strip(), "pexels_api_key": self.pk_var.get().strip(), "cookies_path": self.c_var.get().strip(), "watermark": self.w_var.get().strip(), "subtitle_font": self.f_var.get(), "logo_path": self.l_var.get().strip(), "bgm_volume": self.bv_var.get(), "render_quality": self.rq_var.get(), "template": self.tpl_var.get(), "export_resolution": self.er_var.get(), "end_card": self.ec_var.get(), "end_card_text": self.ec_text_var.get().strip(), "whisper_provider": self.wp_var.get(), "whisper_model": self.wm_var.get().strip(), "silence_threshold": self.st_var.get()}
        self.on_save(nc); self.destroy()

class VideoItem(ctk.CTkFrame):
    def __init__(self, master, index, remove_cb, log_func, config, get_link):
        super().__init__(master, fg_color="#2a2d3e", corner_radius=12, border_width=1, border_color="#3a3d4e")
        self.index, self.remove_cb, self.log_func, self.config, self.get_link = index, remove_cb, log_func, config, get_link; self.is_json = False; self.sel_var = ctk.BooleanVar(value=True); ctk.CTkCheckBox(self, text="", variable=self.sel_var, width=20, fg_color="#4b6e9c", hover_color="#3a5a7a").grid(row=0, column=0, rowspan=2, padx=15, pady=10)
        self.l_f = ctk.CTkFrame(self, fg_color="transparent", width=70); self.l_f.grid(row=0, column=1, rowspan=2, padx=10, pady=10, sticky="nsew"); self.idx_lbl = ctk.CTkLabel(self.l_f, text=f"#{index+1}", font=("Arial", 18, "bold"), text_color="#4b6e9c"); self.idx_lbl.pack(); self.st_lbl = ctk.CTkLabel(self.l_f, text="Ready", font=("Arial", 11), text_color="#aaa"); self.st_lbl.pack()
        self.top = ctk.CTkFrame(self, fg_color="transparent"); self.top.grid(row=0, column=2, sticky="ew", padx=10, pady=(10,0)); self.m_sw = ctk.CTkSegmentedButton(self.top, values=["Manual", "JSON"], command=self.toggle_mode); self.m_sw.set("Manual"); self.m_sw.pack(side="left")
        self.cont = ctk.CTkFrame(self, fg_color="transparent"); self.cont.grid(row=1, column=2, sticky="ew", padx=10, pady=(0,10)); self.man_f = ctk.CTkFrame(self.cont, fg_color="transparent"); self.man_f.pack(fill="x"); r1 = ctk.CTkFrame(self.man_f, fg_color="transparent"); r1.pack(fill="x", pady=2)
        ctk.CTkLabel(r1, text="Mulai:", text_color="#aaa").pack(side="left", padx=3); self.s_var = ctk.StringVar(value="00:00:00"); ctk.CTkEntry(r1, textvariable=self.s_var, width=70, corner_radius=6).pack(side="left", padx=3)
        ctk.CTkLabel(r1, text="Selesai:", text_color="#aaa").pack(side="left", padx=3); self.e_var = ctk.StringVar(value="00:00:10"); ctk.CTkEntry(r1, textvariable=self.e_var, width=70, corner_radius=6).pack(side="left", padx=3)
        self.l_var = ctk.StringVar(value="id"); ctk.CTkEntry(r1, textvariable=self.l_var, width=45, corner_radius=6).pack(side="left", padx=3)
        self.mo_var = ctk.StringVar(value="small"); ctk.CTkComboBox(r1, values=["tiny", "base", "small", "medium", "large-v3"], variable=self.mo_var, width=90, corner_radius=6).pack(side="left", padx=3)
        ctk.CTkLabel(r1, text="Z:", text_color="#aaa").pack(side="left", padx=2); self.z_var = ctk.StringVar(value="1.0"); ctk.CTkEntry(r1, textvariable=self.z_var, width=40, corner_radius=6).pack(side="left", padx=2)
        ctk.CTkLabel(r1, text="Y:", text_color="#aaa").pack(side="left", padx=2); self.y_var = ctk.StringVar(value="0.35"); ctk.CTkEntry(r1, textvariable=self.y_var, width=40, corner_radius=6).pack(side="left", padx=2)
        self.sp_var = ctk.BooleanVar(value=False); ctk.CTkCheckBox(r1, text="Split", variable=self.sp_var, width=60, fg_color="#4b6e9c").pack(side="left", padx=5)
        r2 = ctk.CTkFrame(self.man_f, fg_color="transparent"); r2.pack(fill="x", pady=(5,0))
        ctk.CTkLabel(r2, text="Judul:", text_color="#aaa").pack(side="left", padx=3)
        self.t_var = ctk.StringVar(); ctk.CTkEntry(r2, textvariable=self.t_var, width=160, corner_radius=6).pack(side="left", padx=5)
        ctk.CTkLabel(r2, text="Opini:", text_color="#aaa").pack(side="left", padx=3)
        self.thumb_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(r2, text="IMG", variable=self.thumb_var, width=50, fg_color="#4b6e9c").pack(side="left", padx=3)
        self.op_var = ctk.StringVar(value="Masukkan teks judul opini"); ctk.CTkEntry(r2, textvariable=self.op_var, width=250, corner_radius=6).pack(side="left", padx=5)
        self.gem_b = ctk.CTkButton(r2, text="✨ Analisis", width=90, command=self.analyze_with_ai, fg_color="#4b6e9c", hover_color="#3a5a7a", corner_radius=8); self.gem_b.pack(side="left", padx=10)
        r3 = ctk.CTkFrame(self.man_f, fg_color="transparent")
        r3.pack(fill="x", pady=(2,0))
        self.br_var = ctk.BooleanVar(value=False)
        self.br_cb = ctk.CTkCheckBox(r3, text="🎨 B-Roll Pexels (otomatis)", variable=self.br_var, fg_color="#4b6e9c")
        self.br_cb.pack(side="left", padx=5)
        
        pk = self.config.get("pexels_api_key")
        if not pk:
            self.br_cb.configure(state="disabled")
            self.br_var.set(False)

        ctk.CTkLabel(r3, text="Voice Hook MP3:", text_color="#aaa").pack(side="left", padx=(15,3))
        self.vh_var = ctk.StringVar(value="Pilih file MP3 hook..."); ctk.CTkEntry(r3, textvariable=self.vh_var, width=300, corner_radius=6).pack(side="left", padx=5)
        ctk.CTkButton(r3, text="📂", width=40, command=self.browse_voice_hook, fg_color="#3a3d4e", corner_radius=6).pack(side="left", padx=2)
        ctk.CTkLabel(r3, text="Hook Durasi:", text_color="#aaa").pack(side="left", padx=(10,3))
        self.hook_dur_var = ctk.DoubleVar(value=1.5)
        ctk.CTkSlider(r3, from_=0.5, to=5.0, variable=self.hook_dur_var, width=100).pack(side="left", padx=3)
        ctk.CTkLabel(r3, textvariable=self.hook_dur_var, text_color="#aaa", width=35).pack(side="left", padx=2)
        self.js_f = ctk.CTkFrame(self.cont, fg_color="transparent"); self.js_t = ctk.CTkTextbox(self.js_f, width=500, height=80, corner_radius=8, fg_color="#1e1e2e", text_color="#ccc"); self.js_t.pack(side="left", padx=10)
        ctk.CTkButton(self, text="✕", width=35, fg_color="#c44", hover_color="#a33", corner_radius=8, command=lambda: remove_cb(self)).grid(row=0, column=3, padx=15, pady=10, rowspan=2); self.update_ai_button(); self.toggle_mode("Manual")
    def toggle_mode(self, m):
        if m == "Manual": self.js_f.pack_forget(); self.man_f.pack(fill="x"); self.is_json = False
        else: self.man_f.pack_forget(); self.js_f.pack(fill="x"); self.is_json = True
    def set_status(self, s, c=None): self.st_lbl.configure(text=s, text_color=c if c else "#aaa")
    def set_active(self, a=True): self.configure(border_color="#4b6e9c" if a else "#3a3d4e", border_width=2 if a else 1)
    def update_ai_button(self):
        p = self.config.get("ai_provider")
        if p == "Gemini (Native)": k = self.config.get("gemini_api_key")
        elif p == "Groq": k = self.config.get("groq_api_key")
        else: k = self.config.get("openrouter_api_key")
        self.gem_b.configure(state="normal" if k else "disabled")
    def get_data(self):
        lk = self.get_link()
        try:
            z = float(self.z_var.get() or 1.0)
            y = float(self.y_var.get() or 0.35)
        except (ValueError, TypeError) as e:
            z, y = 1.0, 0.35
            logger.debug("Zoom/Y-offset parse fallback: %s", e)
        hook_dur = self.hook_dur_var.get()
        
        if not self.is_json: return [{ "link": lk, "start": self.s_var.get(), "end": self.e_var.get(), "title": self.t_var.get(), "lang": self.l_var.get() or "id", "model": self.mo_var.get(), "selected": self.sel_var.get(), "split": self.sp_var.get(), "thumb": self.thumb_var.get(), "mood": getattr(self, "_mood", "santai"), "zoom": z, "y_offset": y, "voice_hook": self.vh_var.get().strip(), "judul_opini": self.op_var.get().strip(), "use_broll": self.br_var.get(), "hook_dur": hook_dur, "_thumb_time": getattr(self, "_thumb_time", None), "_ai_desc": getattr(self, "_ai_desc", ""), "_hook_text": getattr(self, "_hook_text", "") }]
        try:
            segs = json.loads(self.js_t.get("1.0", "end").strip())
            if isinstance(segs, dict): segs = [segs]
            for s in segs: 
                s.update({"link": lk, "selected": self.sel_var.get()})
                # Map split_screen from AI to split
                if "split_screen" in s:
                    s["split"] = s.pop("split_screen")
                s.setdefault("split", self.sp_var.get()); s.setdefault("mood", "santai"); s.setdefault("model", self.mo_var.get()); s.setdefault("lang", self.l_var.get() or "id")
                s.setdefault("zoom", z); s.setdefault("y_offset", y)
                s.setdefault("voice_hook", self.vh_var.get().strip()); s.setdefault("judul_opini", self.op_var.get().strip())
                s.setdefault("use_broll", self.br_var.get())
            return segs
        except (json.JSONDecodeError, TypeError, AttributeError) as e:
            logger.warning("JSON segment parse failed: %s", e)
            return []
    def browse_voice_hook(self):
        p = filedialog.askopenfilename(filetypes=[("MP3", "*.mp3")])
        if p: self.vh_var.set(p)
    def analyze_with_ai(self):
        lk = self.get_link()
        if not lk: return
        self.log_func("[#] Analisis segmen...")
        try:
            rt = safe_generate_content(self.config, f"{GEMINI_PROMPT}\nLink: {lk}", self.log_func)
            jm = re.search(r'(\[.*\]|\{.*\})', rt, re.DOTALL)
            if jm:
                raw_json = re.sub(r'[\x00-\x1f]', '', jm.group(1))
                d = json.loads(raw_json)
            else:
                d = []
            if isinstance(d, dict): d = [d]
            if d:
                if len(d) > 1: self.m_sw.set("JSON"); self.toggle_mode("JSON"); self.js_t.delete("1.0", "end"); self.js_t.insert("1.0", json.dumps(d, indent=2))
                else:
                    s = d[0]
                    self.s_var.set(s.get("start","00:00:00")); self.e_var.set(s.get("end","00:00:10"))
                    self.t_var.set(s.get("title","")); self._mood = s.get("mood","santai"); self._ai_desc = s.get("description","")
                    self._hook_text = s.get("hook","")
                    self.op_var.set(s.get("judul_opini",""))
                    if s.get("split_screen", False):
                        self.sp_var.set(True)
                    if not s.get("thumb", True):
                        self.thumb_var.set(False)
                    vhs = s.get("voice_hook_script","")
                    if vhs:
                        hook_path = TEMP_DIR / f"voicehook_{int(time.time())}.mp3"
                        self.log_func(f"\n🎤=== VOICE HOOK SCRIPT ===\n{vhs}\n==========================")
                        if voicebox_generate(vhs, hook_path, self.log_func):
                            self.vh_var.set(str(hook_path))
                            self.log_func(f"[✅] Voice hook generated -> {hook_path.name}")
                        else:
                            self.log_func("🎤 Rekam manual dan upload MP3-nya!\n")
        except Exception as e: messagebox.showerror("Error", str(e))

class App(ctk.CTk):
    def __init__(self):
        super().__init__(); self.title("YT Short Clipper v3.0"); self.geometry("1100x850"); 
        ctk.set_appearance_mode("dark"); ctk.set_default_color_theme("blue")
        de = check_dependencies(); self.dependency_failed = len(de) > 0
        self.config = load_config(); self.v_items = []; self.proc = False; self.proc_lock = threading.Lock()
        self.grid_columnconfigure(0, weight=1); [self.grid_rowconfigure(i, weight=0) for i in range(6)]; self.grid_rowconfigure(6, weight=1)
        # Header menu
        m = ctk.CTkFrame(self, height=40, fg_color="#1e1e2e", corner_radius=0); m.grid(row=0, column=0, sticky="ew"); m.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(m, text="⚙️ Settings", command=self.open_settings, fg_color="transparent", hover_color="#3a3d4e").pack(side="left", padx=10, pady=5)
        ctk.CTkButton(m, text="ℹ️ About", command=lambda: messagebox.showinfo("About", "YT Short Clipper v3.0\nAI-powered video segment clipper.\n\nFeatures: Templates, Auto-split, Queue Persist, Subtitle Animation, End Cards"), fg_color="transparent", hover_color="#3a3d4e").pack(side="right", padx=10, pady=5)
        # Judul
        ctk.CTkLabel(self, text="YT Shorts Clipper Pro", font=("Arial", 26, "bold"), text_color="#fff").grid(row=1, column=0, pady=15)
        # Link input
        f_l = ctk.CTkFrame(self, fg_color="#2a2d3e", corner_radius=10); f_l.grid(row=2, column=0, padx=30, pady=5, sticky="ew"); f_l.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(f_l, text="🎬 Link YouTube:", font=("Arial", 14, "bold"), text_color="#ddd").pack(side="left", padx=(15,10), pady=10)
        self.l_var = ctk.StringVar(); ctk.CTkEntry(f_l, textvariable=self.l_var, width=500, corner_radius=8).pack(side="left", padx=10, fill="x", expand=True, pady=10)
        ctk.CTkButton(f_l, text="🔍 Ambil & Analisis", command=self.start_analysis, fg_color="#4b6e9c", hover_color="#3a5a7a", corner_radius=8).pack(side="left", padx=(10,15), pady=10)
        # Scrollable item list
        self.scr = ctk.CTkScrollableFrame(self, width=1050, height=350, fg_color="#13141c", corner_radius=12); self.scr.grid(row=3, column=0, padx=30, pady=10, sticky="nsew"); self.scr.grid_columnconfigure(0, weight=1)
        # Bottom buttons & progress
        f_b = ctk.CTkFrame(self, fg_color="transparent"); f_b.grid(row=4, column=0, pady=15)
        ctk.CTkButton(f_b, text="➕ Tambah Segmen Manual", command=self.add_video_item, width=180, fg_color="#3a3d4e", hover_color="#2a2d3e", corner_radius=8).pack(side="left", padx=10)
        self.p_btn = ctk.CTkButton(f_b, text="▶ PROSES TERPILIH", fg_color="#2e8b57", hover_color="#236b43", width=200, command=self.start_processing, corner_radius=8).pack(side="left", padx=30)
        self.p_bar = ctk.CTkProgressBar(self, width=1050, corner_radius=5, fg_color="#2a2d3e", progress_color="#4b6e9c"); self.p_bar.grid(row=5, column=0, pady=5, padx=30); self.p_bar.set(0)
        # Log box
        self.log_t = ctk.CTkTextbox(self, width=1050, height=180, fg_color="#13141c", text_color="#ddd", corner_radius=12, border_width=1, border_color="#3a3d4e"); self.log_t.grid(row=6, column=0, padx=30, pady=(5,20), sticky="nsew")
        sys.stdout = self
        self._stdout_lock = threading.Lock()
        # Recover queue from previous session
        saved = load_queue_state()
        if saved and saved.get("segments"):
            self.log("[📂] Queue sebelumnya ditemukan, memulihkan...")
            for s in saved["segments"]:
                self.add_video_item()
                it = self.v_items[-1]
                it.s_var.set(s.get("start", "00:00:00"))
                it.e_var.set(s.get("end", "00:00:10"))
                it.t_var.set(s.get("title", ""))
                it.l_var.set(s.get("lang", "id"))
                it.mo_var.set(s.get("model", "small"))
                it.op_var.set(s.get("judul_opini", ""))
                if s.get("split"): it.sp_var.set(True)
                if s.get("voice_hook"): it.vh_var.set(s["voice_hook"])
                if s.get("link"): self.l_var.set(s["link"])
            self.log(f"[📂] {len(saved['segments'])} segmen dipulihkan.")
        else:
            self.add_video_item()
    def write(self, m):
        with self._stdout_lock:
            try:
                self.log_t.configure(state="normal")
                self.log_t.insert("end", m)
                self.log_t.see("end")
                self.log_t.configure(state="disabled")
            except Exception:
                pass
    def flush(self): pass
    def open_settings(self): SettingsDialog(self, self.config, self.on_settings_save).grab_set()
    def on_settings_save(self, nc): self.config = nc; save_config(nc); [setattr(it, 'config', nc) for it in self.v_items]; [it.update_ai_button() for it in self.v_items]
    def add_video_item(self): i = len(self.v_items); it = VideoItem(self.scr, i, self.remove_video_item, self.log, self.config, lambda: self.l_var.get()); it.grid(row=i, column=0, pady=8, padx=15, sticky="ew"); self.v_items.append(it)
    def remove_video_item(self, item):
        if len(self.v_items) > 1:
            item.destroy()
            self.v_items.remove(item)
            for i, v in enumerate(self.v_items):
                v.idx_lbl.configure(text=f"#{i+1}")
    def log(self, m): self.write(m + "\n")
    def start_analysis(self):
        lk = self.l_var.get().strip()
        if lk: threading.Thread(target=self.run_analysis, args=(lk,), daemon=True).start()
    def run_analysis(self, link):
        try:
            self.log("[#] Fetching metadata..."); vid_id = get_safe_id(link); sid = vid_id
            y_p = "yt-dlp"; local_y = BASE_DIR / "bin" / "yt-dlp.exe"; 
            if local_y.exists(): y_p = f'"{str(local_y)}"'
            cp = self.config.get("cookies_path", ""); c_o = f'--cookies "{cp}"' if cp and os.path.exists(cp) else "--cookies-from-browser chrome"
            # Gunakan sid yang konsisten dengan get_safe_id
            cmd_info = f'{y_p} {c_o} --user-agent "{UA}" --extractor-args "youtube:player_client=android" --skip-download --write-info-json -o "{TEMP_DIR}/{sid}_full" "{link}"'
            subprocess.run(cmd_info, shell=True, capture_output=True, timeout=30)
            info_f = TEMP_DIR / f"{sid}_full.info.json"; title, desc = sid, ""
            if info_f.exists():
                with open(info_f, "r", encoding="utf-8") as f: m = json.load(f); title = m.get("title", sid); desc = m.get("description","")[:500]
            self.log(f"[#] Video: {title}")
            cmd_subs = f'{y_p} {c_o} --user-agent "{UA}" --extractor-args "youtube:player_client=android" --skip-download --write-auto-subs --sub-langs "id,en" --convert-subs srt -o "{TEMP_DIR}/{sid}_full" "{link}"'
            try: subprocess.run(cmd_subs, shell=True, capture_output=True, timeout=60)
            except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError) as e:
                self.log("[!] Subtitle tidak tersedia, lanjut tanpa transkrip.")
                logger.debug("Subtitle download failed: %s", e)
            orig = TEMP_DIR / f"{sid}_full.mp4"
            if not orig.exists():
                self.log("[#] Downloading...")
                try:
                    download_youtube(link, orig, self.config.get("cookies_path"), self.log)
                except Exception as e:
                    logger.error("YouTube download failed: %s", e)
                    self.log(f"❌ {str(e)}")
                    return
            srt = list(TEMP_DIR.glob(f"{sid}_full.*.srt")); txt = ""
            if srt:
                self.log("[#] Parsing subtitle...")
                with open(srt[0], "r", encoding="utf-8", errors="replace") as f:
                    for l in f:
                        if "-->" not in l and l.strip() and not l.strip().isdigit(): txt += l.strip() + " "
            ctx = f"TITLE: {title}\nDESC: {desc}\nTRANSCRIPT: {txt[:20000]}"
            self.log("[#] Menganalisis dengan AI...")
            rt = safe_generate_content(self.config, f"{GEMINI_PROMPT.format(transcript=ctx)}\nLink: {link}", self.log)
            jm = re.search(r'(\[.*\]|\{.*\})', rt, re.DOTALL)
            if jm:
                raw_json = re.sub(r'[\x00-\x1f]', '', jm.group(1))
                d = json.loads(raw_json)
            else:
                d = []
            self.after(0, lambda: self.populate_segments(d))
        except Exception as e:
            logger.error("Analysis failed: %s", e)
            self.log(f"❌ Error: {str(e)}")
    def populate_segments(self, d):
        [i.destroy() for i in self.v_items]; self.v_items.clear()
        if isinstance(d, dict): d = [d]
        for s in d:
            self.add_video_item(); it = self.v_items[-1]
            it.s_var.set(s.get("start","00:00:00")); it.e_var.set(s.get("end","00:00:10"))
            it.t_var.set(s.get("title","")); it._mood = s.get("mood","santai"); it._ai_desc = s.get("description","")
            it.op_var.set(s.get("judul_opini",""))
            if s.get("split_screen", False):
                it.sp_var.set(True)
            if not s.get("thumb", True):
                it.thumb_var.set(False)
            vhs = s.get("voice_hook_script","")
            if vhs:
                hook_path = TEMP_DIR / f"voicehook_{int(time.time())}.mp3"
                self.log(f"\n🎤=== VOICE HOOK SCRIPT ===\n{vhs}\n==========================")
                if voicebox_generate(vhs, hook_path, self.log):
                    it.vh_var.set(str(hook_path))
                    self.log(f"[✅] Voice hook generated -> {hook_path.name}")
                else:
                    self.log("🎤 Rekam manual dan upload MP3-nya!\n")
    def start_processing(self):
        al = []
        for it in self.v_items:
            for d in it.get_data():
                if d.get("selected"): d["_item"] = it; al.append(d)
        if not al:
            self.log("[!] Tidak ada segmen dipilih.")
            return
        save_queue_state(al, self.config)
        with self.proc_lock:
            if self.proc:
                return
            self.proc = True
        self.p_bar.set(0)
        threading.Thread(target=self.run_batch, args=(al,), daemon=True).start()
    def run_batch(self, segs):
        total = len(segs)
        for i, v in enumerate(segs):
            it = v["_item"]; it.set_active(True); it.set_status("Processing..."); ss = time_str_to_seconds(v["start"]); es = time_str_to_seconds(v["end"])
            o = { 
                "cookies_path": self.config.get("cookies_path"), 
                "watermark": self.config.get("watermark"), 
                "status_func": it.set_status, 
                "selected_font": self.config.get("subtitle_font"), 
                "logo_path": self.config.get("logo_path"), 
                "ai_desc": v.get("_ai_desc"), 
                "split_screen": v.get("split"), 
                "mood": v.get("mood"), 
                "bgm_volume": self.config.get("bgm_volume", 0.15),
                "zoom": v.get("zoom", 1.0),
                "y_offset": v.get("y_offset", 0.35),
                "voice_hook": v.get("voice_hook", ""),
                "judul_opini": v.get("judul_opini", ""),
                "use_broll": v.get("use_broll", False),
                "hook_dur": v.get("hook_dur", 1.5),
                "hook_text": v.get("_hook_text", ""),
                "gen_thumb": v.get("thumb", True),
                "root": self,
                "config": self.config,
                "render_quality": self.config.get("render_quality", "normal"),
                "template": self.config.get("template", "cinematic"),
                "export_resolution": self.config.get("export_resolution", "1080x1920"),
                "end_card": self.config.get("end_card", True),
                "end_card_text": self.config.get("end_card_text", "Follow for more!"),
                "silence_threshold": self.config.get("silence_threshold", 0.6),
            }
            success, msg = process_single_video(v["link"], ss, es, v["title"], v["lang"], v["model"], self.log, lambda p, idx=i: self.p_bar.set((idx*100+p)/(total*100)), opts=o)
            it.set_status("Done" if success else "Error"); it.set_active(False)
        clear_queue_state()
        self.log("✅ Finished."); self.p_bar.set(1)
        with self.proc_lock:
            self.proc = False

if __name__ == "__main__": app = App(); app.mainloop()