from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import shutil
import struct
import tempfile
import unittest
from unittest.mock import patch
import wave

from app.music_catalog import (
    AudioLevelError,
    MusicCatalogError,
    calculate_catalog_gain,
    load_music_catalog,
    measure_integrated_lufs,
)


def track_data(
    *,
    track_id: str = "faixa_teste",
    path: str = "faixas/testes/faixa_teste.mp3",
    selection_status: str = "editorial_candidate",
    volume: int = 4,
    sha256: str | None = None,
) -> dict[str, object]:
    payload = b"fake-mp3-for-catalog-validation"
    return {
        "id": track_id,
        "path": path,
        "title": "Faixa teste",
        "artist_candidate": "Autor provisório",
        "duration_seconds": 42.0,
        "category": "testes",
        "best_for_estimate": "testes locais",
        "measured_lufs": -12.0,
        "recommended_volume_percent": volume,
        "selection_status": selection_status,
        "license_status": "unverified",
        "license_url": None,
        "source_url": None,
        "attribution_text": None,
        "sha256": sha256 or hashlib.sha256(payload).hexdigest(),
    }


def write_catalog(root: Path, tracks: list[dict[str, object]]) -> Path:
    music_root = root / "music_library"
    (music_root / "faixas").mkdir(parents=True, exist_ok=True)
    for track in tracks:
        raw_path = str(track["path"])
        if not raw_path.startswith("/") and ".." not in Path(raw_path).parts:
            target = music_root.joinpath(*raw_path.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"fake-mp3-for-catalog-validation")
    music_root.mkdir(parents=True, exist_ok=True)
    (music_root / "catalog.json").write_text(
        json.dumps({"version": 1, "tracks": tracks}, ensure_ascii=False),
        encoding="utf-8",
    )
    return music_root


class MusicCatalogTests(unittest.TestCase):
    def test_uses_bundled_library_when_input_has_no_override(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_root = root / "input"
            input_root.mkdir()
            bundled_root = write_catalog(root / "bundled", [track_data()])
            with patch.dict("os.environ", {"MUSIC_LIBRARY_DIR": str(bundled_root)}):
                catalog = load_music_catalog(input_root)

        self.assertEqual(catalog.root, bundled_root.resolve())
        self.assertEqual(catalog.get("faixa_teste").id, "faixa_teste")

    def test_loads_safe_catalog_and_verifies_selected_sha256(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_catalog(root, [track_data()])
            catalog = load_music_catalog(root)
            track = catalog.get("faixa_teste", verify_sha256=True)

        self.assertEqual(track.relative_path, "faixas/testes/faixa_teste.mp3")
        self.assertEqual(track.recommended_volume_percent, 4)

    def test_rejects_duplicate_ids_paths_escape_missing_review_and_bad_hash(self):
        cases = [
            ([track_data(), track_data(path="faixas/testes/outra.mp3")], "duplicado"),
            ([track_data(), track_data(track_id="outra")], "Caminho.*duplicado"),
            ([track_data(path="../fora.mp3")], "faixas"),
            ([track_data(path="/tmp/fora.mp3")], "faixas"),
        ]
        for tracks, message in cases:
            with self.subTest(message=message), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                write_catalog(root, tracks)
                with self.assertRaisesRegex(MusicCatalogError, message):
                    load_music_catalog(root)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_catalog(root, [track_data(selection_status="review_required")])
            catalog = load_music_catalog(root)
            with self.assertRaisesRegex(MusicCatalogError, "não pode ser selecionada"):
                catalog.get("faixa_teste")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_catalog(root, [track_data(sha256="0" * 64)])
            catalog = load_music_catalog(root)
            with self.assertRaisesRegex(MusicCatalogError, "SHA-256"):
                catalog.get("faixa_teste", verify_sha256=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_catalog(root, [track_data()])
            (root / "music_library" / "faixas" / "testes" / "faixa_teste.mp3").unlink()
            with self.assertRaisesRegex(MusicCatalogError, "ausente"):
                load_music_catalog(root)

    def test_gain_is_capped_and_drops_when_voice_is_quieter(self):
        loud_voice = calculate_catalog_gain(12, -16.0, -12.0)
        quiet_voice = calculate_catalog_gain(12, -30.0, -12.0)

        self.assertLessEqual(loud_voice, 0.12)
        self.assertLessEqual(loud_voice, 10 ** ((-38.0 + 12.0) / 20.0))
        self.assertLess(quiet_voice, loud_voice)
        self.assertEqual(calculate_catalog_gain(0, -20.0, -12.0), 0.0)
        with self.assertRaises(AudioLevelError):
            calculate_catalog_gain(4, math.nan, -12.0)

    def test_rejects_tracks_directory_symlink_that_escapes_library(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            music_root = write_catalog(root, [track_data()])
            outside = root / "outside"
            outside.mkdir()
            (outside / "faixa_teste.mp3").write_bytes(b"fake-mp3-for-catalog-validation")
            shutil.rmtree(music_root / "faixas")
            (music_root / "faixas").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(MusicCatalogError, "fora da biblioteca"):
                load_music_catalog(root)


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg precisa estar instalado para medir LUFS")
class AudioLevelTests(unittest.TestCase):
    @staticmethod
    def write_tone(path: Path, amplitude: int) -> None:
        rate = 24000
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(rate)
            frames = bytearray()
            for sample in range(rate):
                value = int(amplitude * math.sin(2 * math.pi * 440 * sample / rate))
                frames.extend(struct.pack("<h", value))
            handle.writeframes(frames)

    def test_measure_lufs_accepts_voice_and_rejects_silence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            tone = root / "tone.wav"
            silence = root / "silence.wav"
            self.write_tone(tone, 6000)
            self.write_tone(silence, 0)
            self.assertTrue(math.isfinite(measure_integrated_lufs(tone)))
            with self.assertRaisesRegex(AudioLevelError, "silenciosa"):
                measure_integrated_lufs(silence)


if __name__ == "__main__":
    unittest.main()
