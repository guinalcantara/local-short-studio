from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.performance_analysis import choose_comparable, group_medians, subscribers_per_1000
from app.performance_models import Measurement, PerformanceValidationError, PerformanceVideo, ProductionSnapshot, SAO_PAULO, new_id
from app.performance_store import DuplicatePerformanceVideoError, PerformanceStore
from app.performance_snapshot import safe_result_prefill


class PerformanceTrackingTests(unittest.TestCase):
    def video(self, **changes):
        values = {"id": new_id("short"), "title": "Teste", "channel": "Canal teste", "published_at": "2026-01-01T12:00:00-03:00"}
        values.update(changes)
        return PerformanceVideo(**values)

    def measurement(self, video_id, **changes):
        values = {"id": new_id("measurement"), "video_id": video_id, "collected_at": "2026-01-03T12:00:00-03:00", "horizon": "48h", "views": 10, "engaged_views": 5, "subscribers_gained": 2}
        values.update(changes)
        return Measurement(**values)

    def test_validation_keeps_unknown_and_rejects_invalid_metrics(self):
        item = self.measurement(new_id("short"), views=None, average_watch_percent=115)
        self.assertIsNone(item.views)
        self.assertEqual(item.average_watch_percent, 115)
        self.assertTrue(self.video(published_at="2026-01-01T15:00:00+00:00").published_at.endswith("-03:00"))
        with self.assertRaises(PerformanceValidationError): self.measurement(new_id("short"), stayed_to_watch_percent=101)
        with self.assertRaises(PerformanceValidationError): self.measurement(new_id("short"), views=-1)
        with self.assertRaises(PerformanceValidationError): self.video(channel="person@example.com")
        with self.assertRaises(PerformanceValidationError): self.video(published_at="não é uma data")

    def test_store_reopens_updates_and_prevents_duplicate_links(self):
        with TemporaryDirectory() as directory:
            store = PerformanceStore(Path(directory))
            video = store.save_video(self.video(youtube_video_id="abc", production_snapshot=ProductionSnapshot(version_hash="hash-one")))
            again = store.save_video(PerformanceVideo(**{**video.__dict__, "title": "Atualizado"}))
            self.assertEqual(again.title, "Atualizado")
            self.assertEqual(store.get_video(video.id).production_snapshot.version_hash, "hash-one")
            with self.assertRaises(DuplicatePerformanceVideoError): store.save_video(self.video(youtube_video_id="abc"))
            with self.assertRaises(DuplicatePerformanceVideoError): store.save_video(self.video(production_snapshot=ProductionSnapshot(version_hash="hash-one")))
            measurement = self.measurement(video.id)
            store.save_measurement(measurement)
            store.save_measurement(Measurement(**{**measurement.__dict__, "views": 12}))
            reopened = PerformanceStore(Path(directory))
            self.assertEqual(reopened.list_measurements(video.id)[0].views, 12)

    def test_selection_uses_age_and_tie_breaks_with_newest_collection(self):
        video = self.video()
        old = self.measurement(video.id, collected_at="2026-01-03T11:00:00-03:00")
        newer = self.measurement(video.id, collected_at="2026-01-03T13:00:00-03:00")
        unknown = self.video(published_at=None)
        unknown_measurement = self.measurement(unknown.id)
        selected, excluded = choose_comparable([video, unknown], [old, newer, unknown_measurement], "48h", 2)
        self.assertEqual(selected[0].measurement.id, newer.id)
        self.assertIn(unknown_measurement, excluded)
        self.assertEqual(subscribers_per_1000(self.measurement(video.id)), 400)
        self.assertIsNone(subscribers_per_1000(self.measurement(video.id, engaged_views=0)))
        self.assertEqual(group_medians(selected, "channel")["Canal teste"]["views_n"], 1)

    def test_result_snapshot_never_copies_private_effective_values(self):
        from types import SimpleNamespace
        with TemporaryDirectory() as directory:
            mp4 = Path(directory) / "result.mp4"; mp4.write_bytes(b"video")
            project = SimpleNamespace(title="Resultado", voice="pf_dora", speed=1.1, scenes=[SimpleNamespace(shots=None)], soundtrack=None)
            prefill = safe_result_prefill(mp4, project, {"tts_engine": "chatterbox", "chatterbox": {"temperature": 0.7, "reference_audio_path": "C:/private.wav", "token": "secret"}, "music_source": "upload", "music_volume_percent": 4})
            snapshot = prefill.production_snapshot
            encoded = str(snapshot.narration_config) + str(snapshot.music)
            self.assertIn("temperature", encoded)
            self.assertNotIn("private.wav", encoded)
            self.assertNotIn("secret", encoded)


if __name__ == "__main__": unittest.main()
