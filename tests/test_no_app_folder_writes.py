"""
Regresi untuk bug pengemasan yang ketahuan di fase 5.

Bug ini berasal dari refactor sendiri, bukan dari kode lama: sebuah blok
"Platform-Aware" yang tertinggal di clipper_core.py menimpa BASE_DIR/TEMP_DIR/
OUTPUT_DIR/CONFIG_FILE dengan path di dalam folder aplikasi — membatalkan
seluruh clipper_paths.py yang dibangun di fase 1.

Efeknya nyata, bukan teoritis:
  - `import clipper_core` membuat folder `temp/` dan `output/` di folder aplikasi
  - saat frozen, semuanya jatuh ke `sys._MEIPASS` yang dihapus saat app ditutup
  - alias module-level yang "terverifikasi benar" di fase 1 ternyata menunjuk ke
    tempat yang salah, karena ditimpa 70 baris di bawahnya

Test di bawah mengunci dua hal yang membuat bug ini lolos: nilai path, dan efek
samping saat import. Nilai saja tidak cukup — bug ini persis kasus di mana nilai
benar di satu tempat dan salah di tempat lain.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT))


class TestNoWriteIntoAppFolder:
    """Folder aplikasi harus tetap bersih setelah import."""

    def test_import_creates_nothing_in_app_folder(self):
        """`import clipper_core` tidak boleh membuat temp/ atau output/ di repo."""
        code = (
            "import clipper_core, os;"
            "app = os.path.dirname(clipper_core.__file__);"
            "bad = [n for n in ('temp','output','temp_analyze')"
            " if os.path.isdir(os.path.join(app, n))];"
            "print('|'.join(bad))"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert result.returncode == 0, result.stderr[-2000:]
        polluted = [x for x in result.stdout.strip().split("|") if x]
        assert not polluted, (
            f"import clipper_core membuat folder di dalam folder aplikasi: {polluted}. "
            "Ini berarti blok legacy masih menimpa path dengan BASE_DIR/..."
        )

    def test_no_meipass_fallback_block_remains(self):
        """Akses sys._MEIPASS hanya boleh ada di clipper_paths.resource_dir().

        Dicek lewat AST, bukan grep: komentar yang menjelaskan kenapa blok itu
        dihapus justru menyebut _MEIPASS, dan grep akan melaporkan temuannya
        sendiri — persis jebakan yang sudah terjadi dua kali di proyek ini.
        """
        import ast

        core_path = ROOT / "clipper_core.py"
        tree = ast.parse(core_path.read_text(encoding="utf-8"))
        offenders = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and node.attr == "_MEIPASS"
        ]
        assert not offenders, (
            f"clipper_core.py masih membaca sys._MEIPASS di baris {offenders}. "
            "Resource dir hanya boleh diputuskan di clipper_paths.resource_dir()"
        )

    def test_no_implicit_fallthrough_to_base_dir(self):
        """Path dari BASE_DIR hanya boleh bila pemanggil menyodorkan base_dir.

        `setup_directories(base_dir=...)` untuk Colab: pemanggil eksplisit memilih
        folder itu, jadi sah. Yang dilarang adalah `BASE_DIR / "temp"` sebagai
        nilai cadangan saat argumen tidak diberikan — itulah yang membuat blok
        lama menulis ke resource dir, dan blok itu tidak pernah menerima
        base_dir dari desktop.
        """
        import ast

        core_path = ROOT / "clipper_core.py"
        tree = ast.parse(core_path.read_text(encoding="utf-8"))

        allowed = set()
        for node in ast.walk(tree):
            # Cari `if base_dir:` lalu tandai seluruh blok-nya sebagai sah.
            if (
                isinstance(node, ast.If)
                and isinstance(node.test, ast.Name)
                and node.test.id == "base_dir"
            ):
                for sub in node.body:
                    allowed.update(
                        range(sub.lineno, (sub.end_lineno or sub.lineno) + 1)
                    )

        offenders = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.BinOp) or not isinstance(node.op, ast.Div):
                continue
            left = node.left
            if isinstance(left, ast.Name) and left.id == "BASE_DIR":
                if node.lineno in allowed:
                    continue
                offenders.append(node.lineno)
        assert not offenders, (
            f"clipper_core.py menghitung path dari BASE_DIR sebagai nilai cadangan "
            f"di baris {offenders}. Pemanggil yang benar-benar memilih folder harus "
            "melewatkan base_dir=; kalau tidak, pakai accessor data_dir()."
        )


class TestAliasValuesAreHonest:
    """Alias module-level harus benar-benar menunjuk ke tujuan yang dijanjikan."""

    def test_aliases_match_accessors(self):
        import clipper_core
        import clipper_paths

        assert str(clipper_core.TEMP_DIR) == str(clipper_paths.temp_dir()), (
            "TEMP_DIR alias tidak sama dengan temp_dir() — ada yang menimpanya"
        )
        assert str(clipper_core.CONFIG_FILE) == str(clipper_paths.config_file())
        assert str(clipper_core.OUTPUT_DIR) == str(clipper_paths.default_output_dir())
        assert str(clipper_core.BASE_DIR) == str(clipper_paths.RESOURCE_DIR)

    def test_config_is_not_in_app_folder(self):
        import clipper_core

        assert clipper_core.CONFIG_FILE.name == "config.json"
        assert clipper_core.CONFIG_FILE.parent == clipper_core.temp_dir().parent, (
            "config harus di DATA_DIR, bukan di folder aplikasi"
        )

    def test_output_is_not_under_app_folder(self):
        import clipper_core

        app_folder = Path(clipper_core.__file__).parent.resolve()
        assert app_folder not in clipper_core.OUTPUT_DIR.parents, (
            "output default tidak boleh di dalam folder aplikasi"
        )

    def test_resource_dir_is_read_only_place_for_bin(self):
        import clipper_core

        assert (clipper_core.RESOURCE_DIR / "bin").name == "bin"
        assert clipper_core.get_ffmpeg_path() in (
            "ffmpeg",
            str(clipper_core.RESOURCE_DIR / "bin" / "ffmpeg.exe"),
        )
