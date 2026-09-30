"""
clipper_ai.py — Lapisan parsing & validasi output AI.

Konteks
-------
Output AI dipakai sebagai sumber data aplikasi: judul, hook, timestamp, mood,
keyword B-roll. Semuanya berakhir jadi argumen ffmpeg, nama file, atau teks yang
ditampilkan user. Jadi output AI adalah INPUT YANG TIDAK DIPERCAYA, sama seperti
input user — bedanya hanya datang lewat jaringan.

Tiga masalah nyata yang modul ini tangani:

1. JSON rusak. Model sering membungkus JSON di ```json ... ```, menambahkan
   penjelasan di depan, atau trailing comma. `json.loads` langsung
   gagal dan seluruh hasil analisis hilang.

2. JSON valid tapi salah bentuk. `{ "start": "abc" }` lolos `json.loads` lalu
   meledak di `time_str_to_seconds` jauh dari tempat masalahnya. Validasi
   di Output.from_ai_result mengembalikan error yang bisa ditampilkan.

3. Prompt dengan placeholder yang lupa diisi. Gemini_PROMPT punya `{transcript}`;
   kalau caller mengirim apa adanya, model menerima string literal `{transcript}`
   dan mengarang analisis dari nol. `build_prompt` menolak hal ini.

Prinsip: lebih baik dapat 1 hasil yang Valid dengan field yang hilang diisi default,
daripada mendapat 15 hasil yang perlu processing 13 di antaranya gagal diam-diam.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

logger = logging.getLogger("clipper")


# --------------------------------------------------------------------------
# Ekstraksi JSON dari teks bebas
# --------------------------------------------------------------------------
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def strip_fences(text: str) -> str:
    """Ambil isi blok ``` ``` pertama kalau ada."""
    if not text:
        return ""
    m = _FENCE.search(text)
    return m.group(1) if m else text


def strip_control_chars(text: str) -> str:
    """Buang karakter kontrol. Newline (\n) dan tab (\t) sengaja disimpan.

    Karakter kontrol sering membuat `json.loads` gagal tanpa pesan
    dari output model sering membuat `json.loads` gagal tanpa pesan yang berguna.
    """
    return _CONTROL.sub("", text)


def extract_json(text: str):
    """Coba parse JSON dari output model. Kembalikan None kalau tidak ketemu.

    Mencoba urutan dari yang paling ketat ke yang paling longgar:
      1. apa adanya setelah fence dibuang
      2. setelah karakter kontrol dibuang
      3. potongan pertama yang mulai dengan [ atau { dan berakhir seimbang
    """
    if not text:
        return None

    for candidate in (strip_fences(text), text):
        for variant in (candidate, strip_control_chars(candidate)):
            try:
                return json.loads(variant.strip())
            except (json.JSONDecodeError, ValueError):
                continue

    # Fallback: ambil substring yang struktur kurung kurawalnya seimbang.
    balanced = _first_balanced(text)
    if balanced:
        try:
            return json.loads(balanced)
        except (json.JSONDecodeError, ValueError):
            return None
    return None


def _first_balanced(text: str) -> str | None:
    """Potongan pertama yang diawali [ atau { dan berakhir di pasangan yang benar.

    Menangani kasus umum: model menulis penjelasan lalu JSON-nya di belakang,
    misalnya "Berikut hasilnya:\\n```\\n[{...}]\\n```".
    """
    start = None
    opener = closer = ""
    for i, ch in enumerate(text):
        if ch in "[{":
            start = i
            opener = ch
            closer = "]" if ch == "[" else "}"
            break
    if start is None:
        return None

    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


# --------------------------------------------------------------------------
# Normalisasi waktu
# --------------------------------------------------------------------------
_TIME_RE = re.compile(r"^\s*(\d{1,2}):(\d{2})(?::(\d{2}))?\s*$")


def parse_timestamp(value) -> float | None:
    """Terjemahkan "00:01:23", "1:23", atau angka (detik) ke float detik.

    Kembalikan None kalau tidak bisa dibaca — pemanggil decides apakah itu fatal.
    Model sering mengembalikan "1m23s" atau "83" atau "start"; semuanya lebih baik
    dianggap "tidak ada" daripada dipaksa jadi angka yang salah.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value) if value >= 0 else None
    if not isinstance(value, str):
        return None
    m = _TIME_RE.match(value)
    if not m:
        return None
    if m.group(3) is None:
        minutes, seconds = int(m.group(1)), int(m.group(2))
        if minutes > 59 or seconds > 59:
            return None
        return minutes * 60 + seconds
    hours, minutes, seconds = int(m.group(1)), int(m.group(2)), int(m.group(3))
    # Menit/ detik > 59 bukan timestamp yang masuk akal. Tanpa cek ini
    # "00:99:99" diam-diam jadi 6039 detik — clip sepanjang 100 menit yang
    # tidak akan pernah dirender berhasil.
    if minutes > 59 or seconds > 59:
        return None
    return hours * 3600 + minutes * 60 + seconds


def format_timestamp(seconds: float) -> str:
    """Balik ke "HH:MM:SS" untuk ditampilkan di UI."""
    seconds = max(0, int(seconds))
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


# --------------------------------------------------------------------------
# Skema & validasi
# --------------------------------------------------------------------------
# Field yang dipakai render. Default dipakai kalau AI tidak mengirim.
_SEGMENT_DEFAULTS = {
    "start": "00:00:00",
    "end": "00:00:10",
    "title": "",
    "title_alt": [],
    "description": "",
    "hashtags": [],
    "seo_tags": "",
    "viral_score": 5,
    "hook": "",
    "mood": "santai",
    "split_screen": False,
    "judul_opini": "",
    "voice_hook_script": "",
}

_VALID_MOODS = {"inspirasi", "tegang", "santai", "kocak", "sedih"}


@dataclass
class Segment:
    """Satu segmen short, sudah divalidasi dan siap dipakai render."""

    start: float
    end: float
    title: str
    title_alt: list = None
    description: str = ""
    hashtags: list = None
    seo_tags: str = ""
    viral_score: int = 5
    viral_score_valid: bool = True
    hook: str = ""
    mood: str = "santai"
    split_screen: bool = False
    judul_opini: str = ""
    voice_hook_script: str = ""

    def __post_init__(self):
        if self.title_alt is None:
            self.title_alt = []
        if self.hashtags is None:
            self.hashtags = []

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def to_dict(self) -> dict:
        """Bentuk yang dikembalikan ke UI (timestamp sebagai string)."""
        return {
            "start": format_timestamp(self.start),
            "end": format_timestamp(self.end),
            "title": self.title,
            "title_alt": list(self.title_alt),
            "description": self.description,
            "hashtags": list(self.hashtags),
            "seo_tags": self.seo_tags,
            "viral_score": self.viral_score,
            "hook": self.hook,
            "mood": self.mood,
            "split_screen": self.split_screen,
            "judul_opini": self.judul_opini,
            "voice_hook_script": self.voice_hook_script,
        }


def _as_float(value, fallback: float) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return fallback
    return out if out == out and out not in (float("inf"), float("-inf")) else fallback


def _as_int(value, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "1", "iya")
    return bool(value)


def _as_str_list(value) -> list:
    """Terjemahkan hashtag dari str / list / comma-string menjadi list of str."""
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        return [p.strip() for p in value.split(",") if p.strip()]
    return []


def normalize_mood(value) -> str:
    """Paksa mood ke salah satu nilai yang dikenal; default 'santai'.

    Mood menentukan file BGM. Nilai dari luar daftar berarti ensure_bgm akan
    melakukan request yang pasti gagal atau, lebih buruk, diam-diam memakai BGM
    salah.
    """
    text = str(value or "").strip().lower()
    return text if text in _VALID_MOODS else "santai"


def segment_from_dict(raw: dict) -> Segment:
    """Bangun Segment dari dict hasil AI. Tidak pernah melempar exception.

    Field yang hilang/tidak terbaca diisi default. Timestamp yang tidak terbaca
    dijatuhkan ke 0, dan `end` dipaksa lebih besar dari `start` supaya render tidak pernah
    menerima rentang terbalik (AUDIT.md G3).
    """
    if not isinstance(raw, dict):
        raw = {}

    start = parse_timestamp(raw.get("start"))
    end = parse_timestamp(raw.get("end"))
    if start is None:
        start = 0.0
    if end is None:
        end = start + 10.0
    if end <= start:
        # Jangan diam-diam tukar: durasi 0 memberi hasil render kosong. Naikkan
        # `end` saja supaya user masih dapat sesuatu yang bisa dilihat.
        end = start + 10.0

    score = _as_int(raw.get("viral_score"), _SEGMENT_DEFAULTS["viral_score"])
    return Segment(
        start=start,
        end=end,
        title=str(raw.get("title") or "").strip(),
        title_alt=_as_str_list(raw.get("title_alt")),
        description=str(raw.get("description") or "").strip(),
        hashtags=_as_str_list(raw.get("hashtags")),
        seo_tags=str(raw.get("seo_tags") or "").strip(),
        viral_score=max(1, min(10, score)),
        viral_score_valid=_as_int(raw.get("viral_score"), 0) == score,
        hook=str(raw.get("hook") or "").strip(),
        mood=normalize_mood(raw.get("mood")),
        split_screen=_as_bool(raw.get("split_screen")),
        judul_opini=str(raw.get("judul_opini") or "").strip(),
        voice_hook_script=str(raw.get("voice_hook_script") or "").strip(),
    )


def segments_from_response(text: str, *, log_func=None) -> list:
    """Parse output AI jadi list Segment.

    Kembalikan [] kalau tidak ada JSON yang bisa dibaca — pemanggil wajib
    menampilkan pesan, bukan diam-diam memakai hasil kosong.
    """
    data = extract_json(text)
    if data is None:
        logger.warning("AI response tidak berisi JSON yang bisa dibaca")
        if log_func:
            log_func("[!] Balasan AI tidak bisa dibaca sebagai JSON. Coba lagi.")
        return []

    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        logger.warning("Struktur AI response tidak dikenal: %s", type(data).__name__)
        if log_func:
            log_func("[!] Struktur balasan AI tidak dikenali. Coba lagi.")
        return []

    segments = []
    for item in data:
        if not isinstance(item, dict):
            continue
        segments.append(segment_from_dict(item))
    if not segments and log_func:
        log_func("[!] AI tidak mengembalikan segmen yang bisa dipakai.")
    return segments


# --------------------------------------------------------------------------
# Prompt
# --------------------------------------------------------------------------
_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def build_prompt(template: str, **values) -> str:
    """Isi placeholder prompt. Menolak kalau ada placeholder yang tidak terisi.

    Ini menangkap bug AUDIT.md G1 dari sisi pemanggil: `GEMINI_PROMPT` punya
    `{transcript}`, dan tombol "Analisis" pernah mengirim apa adanya sehingga model
    menerima string literal dan mengarang hasil dari nol. Sekarang itu jadi
    error yang terlihat, bukan hasil yang meyakinkan tapi salah.
    """
    missing = [m.group(1) for m in _PLACEHOLDER.finditer(template or "")
               if m.group(1) not in values]
    if missing:
        raise ValueError(
            "Prompt punya placeholder yang belum diisi: "
            + ", ".join("{" + m + "}" for m in missing)
            + ". Ini akan membuat AI mengarang isi dari tidak ada."
        )
    return (template or "").format(**values)
