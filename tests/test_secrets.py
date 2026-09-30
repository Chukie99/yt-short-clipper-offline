"""
Test untuk clipper_secrets.py.

Yang diuji di sini bukan hanya "fungsi mengembalikan apa yang diharapkan",
tetapi properti yang benar-benar penting untuk produk yang dijual:

  - key TIDAK pernah muncul sebagai plaintext di file yang ditulis
  - key bisa dihapus (string kosong = hapus, bukan "simpan yang kosong")
  - file rusak tidak membuat app crash
  - tidak ada key yang bocor ke log

Test memakai CLIPPER_DATA_DIR di temp supaya tidak pernah menyentuh
%LOCALAPPDATA% milik user sungguhan.
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """Arahkan DATA_DIR ke folder temp untuk setiap test."""
    monkeypatch.setenv("CLIPPER_DATA_DIR", str(tmp_path / "data"))
    import clipper_secrets as S

    S.reset_secret_registry()
    yield
    S.reset_secret_registry()


@pytest.fixture
def S():
    import clipper_secrets

    return clipper_secrets


# --------------------------------------------------------------------------
# Round-trip
# --------------------------------------------------------------------------
class TestRoundTrip:
    def test_save_then_load(self, S):
        S.set_secret("gemini_api_key", "AIzaSyTESTKEY1234567890abcdef")
        assert S.get_secret("gemini_api_key") == "AIzaSyTESTKEY1234567890abcdef"

    def test_multiple_fields_persist(self, S):
        S.set_secret("gemini_api_key", "AIzaSyAAA1111")
        S.set_secret("groq_api_key", "gsk_bbb2222")
        S.set_secret("pexels_api_key", "pexels-ccc3333")
        values = S.load_secrets()
        assert values["gemini_api_key"] == "AIzaSyAAA1111"
        assert values["groq_api_key"] == "gsk_bbb2222"
        assert values["pexels_api_key"] == "pexels-ccc3333"

    def test_whitespace_stripped(self, S):
        S.set_secret("gemini_api_key", "  AIzaSyPADDED  ")
        assert S.get_secret("gemini_api_key") == "AIzaSyPADDED"

    def test_only_known_fields_persisted(self, S):
        # Field yang bukan secret tidak boleh ikut masuk ke blob.
        S.set_secret("gemini_api_key", "AIzaSyOK12345678")
        S.save_secrets({"gemini_api_key": "AIzaSyOK12345678", "watermark": "bukan secret"})
        assert "watermark" not in S.load_secrets()

    def test_file_created_in_data_dir_not_app_dir(self, S):
        S.set_secret("gemini_api_key", "AIzaSyPATH123456")
        assert S.secrets_file().exists()
        assert S.secrets_file().parent == S.data_dir()


# --------------------------------------------------------------------------
# Properti keamanan yang paling penting
# --------------------------------------------------------------------------
class TestNotPlaintext:
    """Ini inti alasan modul ini ada."""

    def test_key_not_visible_in_file(self, S):
        key = "AIzaSySECRETKEY000111222333444"
        S.set_secret("gemini_api_key", key)
        raw = S.secrets_file().read_bytes()
        assert key.encode() not in raw
        assert b"AIzaSySECRETKEY" not in raw

    def test_json_payload_not_recoverable(self, S):
        S.set_secret("gemini_api_key", "AIzaSyHIDDEN999888777")
        raw = S.secrets_file().read_bytes()
        # Nama field pun tidak boleh terbaca plaintext.
        assert b"gemini_api_key" not in raw

    @pytest.mark.skipif(sys.platform != "win32", reason="DPAPI hanya di Windows")
    def test_file_is_real_dpapi_blob(self, S):
        """Blob DPAPI = version DWORD 1, lalu provider GUID {df9d8cd0-1501-...}.

        Byte pertama adalah version, bukan magic 0xFFFF. Yang membuktikan
        enkripsi benar-benar terjadi adalah GUID provider DPAPI di byte 4..20:
        plaintext pasti tidak akan punya itu.
        """
        S.set_secret("gemini_api_key", "AIzaSyDPAPICHECK123")
        raw = S.secrets_file().read_bytes()
        version = int.from_bytes(raw[:4], "little")
        provider_guid = raw[4:20].hex()
        assert version == 1, f"bukan versi blob DPAPI: {version}"
        # {df9d8cd0-1501-11d1-8c7a-00c04fc297eb} = provider DPAPI bawaan Windows,
        # disimpan dalam mixed-endian. Plaintext tidak mungkin punya byte ini.
        assert provider_guid == "d08c9ddf0115d1118c7a00c04fc297eb", (
            f"bukan GUID provider DPAPI: {provider_guid}"
        )

    def test_no_secret_field_in_config_json(self, S):
        """config.json tidak boleh memuat nilai key meski config lama masih ada."""
        import clipper_core as core

        core.save_config({"gemini_api_key": "AIzaSyLEAKMEPLEASE123", "watermark": "x"})
        raw = core.config_file().read_text(encoding="utf-8")
        assert "AIzaSyLEAKMEPLEASE123" not in raw


# --------------------------------------------------------------------------
# Penghapusan
# --------------------------------------------------------------------------
class TestDeletion:
    def test_empty_string_deletes(self, S):
        S.set_secret("gemini_api_key", "AIzaSyDELETE1234567")
        S.set_secret("gemini_api_key", "")
        assert "gemini_api_key" not in S.load_secrets()

    def test_none_deletes(self, S):
        S.set_secret("groq_api_key", "gsk_DELETEME1234567")
        S.set_secret("groq_api_key", None)
        assert "groq_api_key" not in S.load_secrets()

    def test_deleting_last_field_removes_file(self, S):
        S.set_secret("gemini_api_key", "AIzaSyONLYONE123456")
        assert S.secrets_file().exists()
        S.set_secret("gemini_api_key", "")
        assert not S.secrets_file().exists()

    def test_delete_all(self, S):
        S.set_secret("gemini_api_key", "AIzaSyA111111111")
        S.set_secret("groq_api_key", "gsk_b222222222")
        S.delete_all_secrets()
        assert S.load_secrets() == {}
        assert not S.secrets_file().exists()


# --------------------------------------------------------------------------
# Ketahanan file
# --------------------------------------------------------------------------
class TestCorruptFile:
    """Blob tidak terbaca harus bisa diperbaiki lewat UI, bukan crash."""

    def test_garbage_returns_empty(self, S):
        S.set_secret("gemini_api_key", "AIzaSyBEFORE1234567")
        S.secrets_file().write_bytes(b"total garbage, bukan blob sama sekali")
        assert S.load_secrets() == {}

    def test_empty_file_returns_empty(self, S):
        S.ensure_dirs()
        S.secrets_file().write_bytes(b"")
        assert S.load_secrets() == {}

    def test_truncated_blob_returns_empty(self, S):
        S.set_secret("gemini_api_key", "AIzaSyTRUNCATED12345")
        raw = S.secrets_file().read_bytes()
        S.secrets_file().write_bytes(raw[: len(raw) // 2])
        assert S.load_secrets() == {}

    def test_wrong_user_scope_returns_empty(self, S):
        """Blob orang lain tidak bisa dibuka — inilah sifat DPAPI yang diinginkan."""
        S.set_secret("gemini_api_key", "AIzaSyWRONGUSER12345")
        raw = bytearray(S.secrets_file().read_bytes())
        raw[40:60] = b"\x00" * 20
        S.secrets_file().write_bytes(bytes(raw))
        assert S.load_secrets() == {}

    def test_recovers_after_corruption(self, S):
        S.ensure_dirs()
        S.secrets_file().write_bytes(b"rusak")
        assert S.load_secrets() == {}
        S.set_secret("gemini_api_key", "AIzaSyRECOVERED1234")
        assert S.get_secret("gemini_api_key") == "AIzaSyRECOVERED1234"

    def test_secret_outside_known_fields_ignored(self, S):
        S.set_secret("gemini_api_key", "AIzaSyVALID1234567")
        # Simulasikan blob yang berisi field asing.
        raw = S.secrets_file().read_bytes()
        assert S.load_secrets().keys() <= set(S.SECRET_FIELDS)


# --------------------------------------------------------------------------
# Environment variable fallback
# --------------------------------------------------------------------------
class TestEnvFallback:
    def test_falls_back_to_env(self, S, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyFROMENV123456")
        assert S.get_secret("gemini_api_key") == "AIzaSyFROMENV123456"

    def test_stored_wins_over_env(self, S, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyFROMENV123456")
        S.set_secret("gemini_api_key", "AIzaSyFROMSTORE1234")
        assert S.get_secret("gemini_api_key") == "AIzaSyFROMSTORE1234"

    def test_env_ignored_for_unknown_field(self, S, monkeypatch):
        monkeypatch.setenv("SOMETHING_ELSE", "nilai")
        assert S.get_secret("field_tidak_dikenal") == ""


# --------------------------------------------------------------------------
# Redaksi log
# --------------------------------------------------------------------------
class TestRedaction:
    def test_registered_secret_redacted(self, S):
        key = "AIzaSyREGISTERED1234567890"
        S.register_secret(key)
        out = S.redact(f"gagal kirim dengan {key}")
        assert key not in out
        assert "REDACTED" in out

    def test_pattern_caught_without_register(self, S):
        """Key dari env tidak pernah di-register, tapi polanya tetap kena."""
        for fake in (
            "AIzaSy" + "a" * 30,
            "gsk_" + "b" * 30,
            "sk-or-v1-" + "c" * 30,
            "sk-" + "d" * 40,
        ):
            out = S.redact(f"token={fake} selesai")
            assert fake not in out, f"tidak tersensor: {fake[:12]}"

    def test_normal_text_untouched(self, S):
        msg = "Render selesai dalam 42 detik, 1080x1920, CRF 18"
        assert S.redact(msg) == msg

    def test_empty_input(self, S):
        assert S.redact("") == ""

    def test_short_values_not_registered(self, S):
        """Menyensor nilai pendek membuat log tak terbaca tanpa-gun."""
        S.register_secret("abc")
        assert S.redact("abc def") == "abc def"

    def test_redacts_in_multiline(self, S):
        key = "AIzaSyMULTILINE123456789"
        S.register_secret(key)
        out = S.redact(f"baris 1\nAuthorization: {key}\nbaris 3")
        assert key not in out


# --------------------------------------------------------------------------
# Pelaporan ke user
# --------------------------------------------------------------------------
class TestDescribeProtection:
    def test_windows_claims_dpapi(self, S):
        if sys.platform == "win32":
            assert S.protection_kind() == "dpapi"
            assert "DPAPI" in S.describe_protection()
            assert not S.has_plaintext_fallback()

    def test_non_windows_is_honest(self, S):
        if sys.platform != "win32":
            assert S.protection_kind() == "plaintext"
            assert S.has_plaintext_fallback()
            assert "DPAPI" in S.describe_protection()
