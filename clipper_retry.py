"""
clipper_retry.py — Retry AI/HTTP dengan backoff yang benar.

Konteks
-------
`safe_generate_content()` versi lama punya loop 3 percobaan, tapi hanya
`sleep()` pada error 429 — semua error lain langsung `raise` di percobaan
pertama. Artinya loop itu tidak pernah percobaan kedua kalau penyebabnya
timeout, 502, atau connection reset. Untuk error rate limit, perilakunya juga
salah: menunggu 20 detik tetap lalu `raise` kalau percobaan ketiga gagal, tanpa
membaca header `Retry-After` yang biasanya ada.

Yang ada di sini:
  - Backoff eksponensial + jitter, supaya banyak request bersamaan tidak
    menyambar server di detik yang sama.
  - `Retry-After` diprioritaskan kalau server mengirimnya.
  - Klasifikasi error: mana yang layak dicoba lagi, mana yang tidak. 401 (API key
    salah) dicoba lagi hanya akan membuang kuota dan menipu user dengan spinner.
"""
from __future__ import annotations

import logging
import random
import time
from typing import Callable

from clipper_secrets import redact

logger = logging.getLogger("clipper")

# Error yang MAYAKIN membaik kalau dicoba lagi: rate limit, network, server.
RETRYABLE_STATUS = frozenset({408, 409, 425, 429, 500, 502, 503, 504, 522, 524})

# Error yang TIDAK akan membaik dengan mencoba lagi.
FATAL_STATUS = frozenset({400, 401, 403, 404, 405, 413, 422, 501})


class AIError(Exception):
    """Kegagalan memanggil AI, sudah dibungkus dengan pesan yang bisa ditampilkan."""

    def __init__(self, message: str, *, provider: str = "", status: int | None = None,
                 attempts: int = 0):
        super().__init__(message)
        self.provider = provider
        self.status = status
        self.attempts = attempts


def is_retryable(exc: BaseException) -> bool:
    """Apakah error ini layak dicoba lagi?

    Error tanpa status (timeout, connection reset, DNS) dianggap retryable —
    itu kasus yang paling sering terjadi di pemakaian nyata. Error bertanda
    4xx selain rate limit dianggap fatal: mencoba lagi tidak memperbaiki API key
    yang salah.
    """
    status = getattr(exc, "status", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    if status is None:
        text = str(exc)
        for code in list(RETRYABLE_STATUS) + list(FATAL_STATUS):
            if str(code) in text:
                status = code
                break
    if status is None:
        return True
    if status in FATAL_STATUS:
        return False
    return status in RETRYABLE_STATUS or status >= 500


def retry_after_seconds(exc: BaseException) -> float | None:
    """Baca header Retry-After kalau ada (detik atau tanggal HTTP)."""
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    raw = None
    try:
        raw = headers.get("Retry-After") or headers.get("retry-after")
    except Exception:  # noqa: BLE001 — header aneh tidak boleh membuat lempar
        return None
    if not raw:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        pass
    # Format tanggal HTTP (mis. "Wed, 21 Oct 2026 07:28:00 GMT").
    try:
        from email.utils import parsedate_to_datetime

        delta = parsedate_to_datetime(raw) - _utcnow()
        return max(0.0, delta.total_seconds())
    except Exception:  # noqa: BLE001
        return None


def _utcnow():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


def compute_delay(attempt: int, base: float = 2.0, cap: float = 60.0,
                  jitter: float = 0.3) -> float:
    """Backoff eksponensial dengan jitter.

    `attempt` mulai dari 0. Jitter penting karena tanpa itu, beberapa request
    yang gagal bersamaan akan mencoba lagi persis di detik yang sama — pola yang
    justru memperlambat pemulihan rate limit.
    """
    delay = min(cap, base * (2 ** attempt))
    spread = delay * jitter
    return max(0.0, delay + random.uniform(-spread, spread))


def call_with_retry(
    fn: Callable,
    *,
    attempts: int = 3,
    base_delay: float = 2.0,
    cap: float = 60.0,
    provider: str = "",
    log_func: Callable[[str], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    jitter: bool = True,
) -> str:
    """Panggil `fn()` sampai berhasil atau kehabisan percobaan.

    `fn` harus mengembalikan teks. Error yang tidak retryable langsung dilempar
    tanpa menunggu — tidak ada gunanya membuat user menunggu 4 detik untuk
    ditolak lagi karena API key salah.
    """
    last_exc: BaseException | None = None

    for attempt in range(attempts):
        try:
            return fn()
        except BaseException as exc:  # noqa: BLE001 — diklasifikasi di bawah
            # Jangan swallow KeyboardInterrupt/SystemExit jadi "gagal".
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            last_exc = exc
            if not is_retryable(exc):
                raise AIError(
                    _explain_fatal(exc, provider),
                    provider=provider,
                    status=getattr(exc, "status", None),
                    attempts=attempt + 1,
                ) from exc
            if attempt == attempts - 1:
                break
            delay = retry_after_seconds(exc)
            if delay is None:
                delay = compute_delay(
                    attempt, base_delay, cap, jitter=0.3 if jitter else 0.0
                )
            delay = min(delay, cap)
            if log_func:
                log_func(
                    f"[!] Gagal ({type(exc).__name__}), mencoba lagi dalam {delay:.0f}s "
                    f"[{attempt + 1}/{attempts}]"
                )
            logger.warning(
                "AI attempt %d/%d gagal (%s), tunggu %.1fs",
                attempt + 1, attempts, type(exc).__name__, delay,
            )
            sleep(delay)

    assert last_exc is not None
    raise AIError(
        _explain_exhausted(last_exc, provider, attempts),
        provider=provider,
        attempts=attempts,
    ) from last_exc


def _explain_fatal(exc: BaseException, provider: str) -> str:
    """Pesan yang mengarahkan user ke tindakan yang benar."""
    status = getattr(exc, "status", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    who = provider or "AI"
    if status in (401, 403):
        return (
            f"{who} menolak API key (HTTP {status}). Cek key di Settings — "
            "key salah atau kuota akun habis."
        )
    if status == 404:
        return f"{who}: model tidak ditemukan (HTTP 404). Cek nama model di Settings."
    if status == 429:
        return f"{who}: kuota rate limit habis (HTTP 429). Tunggu sebentar atau ganti provider."
    return f"{who} menolak permintaan: {redact(str(exc))[:200]}"


def _explain_exhausted(exc: BaseException, provider: str, attempts: int) -> str:
    who = provider or "AI"
    status = getattr(exc, "status", None)
    suffix = f" (HTTP {status})" if status else ""
    return (
        f"{who} gagal setelah {attempts} percobaan{suffix}: "
        f"{redact(str(exc))[:200]}"
    )


def ai_required_fields_present(config: dict, provider: str) -> str:
    """Cek apakah credential untuk provider yang dipilih benar-benar ada.

    Mengembalikan pesan error, atau string kosong kalau siap. Dipakai wizard
    first-run dan sebelum analisis supaya user dapat pesan jelas, bukan HTTP 401
    setelah menunggu 20 detik.
    """
    field_by_provider = {
        "Gemini (Native)": "gemini_api_key",
        "Groq": "groq_api_key",
        "OpenRouter (DeepSeek/GPT/etc)": "openrouter_api_key",
    }
    field = field_by_provider.get(provider)
    if field is None:
        return f"Provider AI tidak dikenal: {provider!r}"
    if not (config.get(field) or "").strip():
        return f"API key untuk {provider} belum diisi. Buka Settings."
    return ""
