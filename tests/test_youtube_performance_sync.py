from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from app.performance_models import PerformanceVideo, new_id
from app.performance_store import PerformanceStore
from app.performance_sync import sync_youtube_performance
from app.youtube import YOUTUBE_ANALYTICS_SCOPE, YOUTUBE_SCOPES, YouTubePerformanceVideo
from app.youtube import YouTubeAccount, fetch_youtube_performance


class YouTubePerformanceSyncTests(unittest.TestCase):
    def test_analytics_scope_is_requested_without_monetary_scope(self):
        self.assertIn(YOUTUBE_ANALYTICS_SCOPE, YOUTUBE_SCOPES)
        self.assertNotIn("https://www.googleapis.com/auth/yt-analytics-monetary.readonly", YOUTUBE_SCOPES)

    def test_sync_creates_snapshots_and_preserves_local_editorial_fields(self):
        remote = YouTubePerformanceVideo(video_id="video123", title="Do YouTube", channel_title="Canal", published_at="2026-01-01T12:00:00+00:00", duration_seconds=31, views=100, engaged_views=80, subscribers_gained=4, average_watch_seconds=20, average_watch_percent=110)
        with TemporaryDirectory() as directory:
            store = PerformanceStore(Path(directory))
            local = store.save_video(PerformanceVideo(id=new_id("short"), title="Meu título", channel="Canal", youtube_video_id="video123", topic="história", learned="manter"))
            with patch("app.performance_sync.fetch_youtube_performance", return_value=(remote,)):
                total, created = sync_youtube_performance(store, "a" * 32)
            self.assertEqual((total, created), (1, 0))
            synced = store.get_video(local.id)
            self.assertEqual(synced.topic, "história")
            self.assertEqual(synced.learned, "manter")
            measurement = store.list_measurements(local.id)[0]
            self.assertEqual(measurement.engaged_views, 80)
            self.assertEqual(measurement.source, "youtube_analytics")

    def test_fetch_maps_data_and_analytics_responses_without_network(self):
        class Request:
            def __init__(self, data): self.data = data
            def execute(self): return self.data
        class Data:
            def channels(self): return self
            def playlistItems(self): return self
            def videos(self): return self
            def list(self, **kwargs):
                if "playlistId" in kwargs: return Request({"items": [{"contentDetails": {"videoId": "abc"}}]})
                if kwargs.get("part") == "contentDetails": return Request({"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "uploads"}}}]})
                return Request({"items": [{"id": "abc", "snippet": {"title": "Short", "publishedAt": "2026-01-01T12:00:00Z"}, "contentDetails": {"duration": "PT31S"}, "statistics": {"viewCount": "9"}}]})
        class Analytics:
            def reports(self): return self
            def query(self, **kwargs): return Request({"columnHeaders": [{"name": "views"}, {"name": "engagedViews"}, {"name": "subscribersGained"}, {"name": "averageViewDuration"}, {"name": "averageViewPercentage"}], "rows": [[10, 8, 1, 20, 110]]})
        account = YouTubeAccount(id="a" * 32, label="Teste", channel_id="channel", channel_title="Canal")
        with patch("app.youtube.get_youtube_account", return_value=account), patch("app.youtube._credentials_for_account", return_value=object()), patch("app.youtube._youtube_service", return_value=Data()), patch("app.youtube._youtube_analytics_service", return_value=Analytics()):
            video = fetch_youtube_performance(account.id)[0]
        self.assertEqual((video.views, video.engaged_views, video.average_watch_percent), (10, 8, 110))


if __name__ == "__main__": unittest.main()
