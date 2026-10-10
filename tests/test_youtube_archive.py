from datetime import UTC, datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from googleapiclient.errors import HttpError
from httplib2 import Response

from app.youtube import YouTubeAccount, YouTubeError
from app.youtube_archive import YouTubeArchiveError, _api_error, collect_youtube_channel_archive


class FakeRequest:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        return self.payload


class FakeChannels:
    def list(self, **_kwargs):
        return FakeRequest(
            {
                "items": [
                    {
                        "id": "UC-test",
                        "snippet": {"title": "Canal de testes", "publishedAt": "2024-01-01T00:00:00Z", "email": "private@example.com"},
                        "contentDetails": {"relatedPlaylists": {"uploads": "UU-test"}},
                        "statistics": {"viewCount": "42"},
                    }
                ]
            }
        )


class FakePlaylistItems:
    def list(self, **kwargs):
        if kwargs.get("pageToken"):
            return FakeRequest({"items": [{"contentDetails": {"videoId": "video-2"}}]})
        return FakeRequest(
            {
                "items": [{"contentDetails": {"videoId": "video-1"}}],
                "nextPageToken": "second-page",
            }
        )


class FakeVideos:
    def list(self, **kwargs):
        video_ids = kwargs["id"].split(",")
        return FakeRequest(
            {
                "items": [
                    {
                        "id": video_id,
                        "snippet": {"title": video_id, "email": "private@example.com"},
                        "statistics": {"viewCount": "12", "accessToken": "must-not-be-saved"},
                    }
                    for video_id in video_ids
                ]
            }
        )


class FakeDataService:
    def channels(self):
        return FakeChannels()

    def playlistItems(self):
        return FakePlaylistItems()

    def videos(self):
        return FakeVideos()


class FakeAnalyticsReports:
    def __init__(self):
        self.calls = []

    def query(self, **kwargs):
        self.calls.append(kwargs)
        video_id = kwargs["filters"].split("==", 1)[1]
        if video_id == "video-2":
            return FakeRequest({"columnHeaders": [{"name": "day"}, {"name": "views"}], "rows": []})
        return FakeRequest(
            {
                "columnHeaders": [
                    {"name": "day"},
                    {"name": "views"},
                ],
                "rows": [["2025-01-02", 12]],
            }
        )


class FakeAnalyticsService:
    def __init__(self):
        self.resource = FakeAnalyticsReports()

    def reports(self):
        return self.resource


class YouTubeArchiveTests(unittest.TestCase):
    def setUp(self):
        self.account = YouTubeAccount(
            id="a" * 32,
            label="Canal de testes",
            channel_id="UC-test",
            channel_title="Canal de testes",
        )
        self.collected_at = datetime(2025, 1, 2, 3, 4, 5, 678900, tzinfo=UTC)

    def test_collects_paginated_snapshot_without_sensitive_fields_or_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive_root = Path(temporary) / "channel_archive"
            analytics = FakeAnalyticsService()
            with patch("app.youtube_archive.youtube_channel_archive_dir", return_value=archive_root), patch(
                "app.youtube_archive.youtube_read_services",
                return_value=(self.account, FakeDataService(), analytics),
            ):
                first = collect_youtube_channel_archive(self.account.id, collected_at=self.collected_at)
                second = collect_youtube_channel_archive(self.account.id, collected_at=self.collected_at)

            self.assertNotEqual(first.path, second.path)
            self.assertTrue(first.path.is_dir())
            self.assertEqual(first.video_count, 2)
            self.assertEqual(first.analytics_row_count, 1)
            self.assertEqual(first.uploads_pages, 2)
            manifest = json.loads((first.path / "manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(manifest["sources"]["youtube_data_api"]["uploads_complete"])
            self.assertEqual(manifest["sources"]["youtube_data_api"]["uploads_found"], 2)
            analytics_manifest = manifest["sources"]["youtube_analytics_api"]
            self.assertEqual(analytics_manifest["dimensions"], ["day"])
            self.assertTrue(analytics_manifest["video_filter"])
            self.assertEqual(analytics_manifest["coverage"]["videos_with_rows"], ["video-1"])
            self.assertEqual(analytics_manifest["coverage"]["videos_without_rows"], ["video-2"])
            self.assertTrue(all(call["dimensions"] == "day" for call in analytics.resource.calls))
            self.assertEqual({call["filters"] for call in analytics.resource.calls}, {"video==video-1", "video==video-2"})
            saved = "\n".join(path.read_text(encoding="utf-8") for path in first.path.iterdir())
            self.assertNotIn("private@example.com", saved)
            self.assertNotIn("must-not-be-saved", saved)
            self.assertIn("2025", str(first.path))
            self.assertIn("01", str(first.path))
            self.assertIn("02", str(first.path))

    def test_page_limit_is_recorded_as_incomplete_coverage(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch("app.youtube_archive.youtube_channel_archive_dir", return_value=Path(temporary)), patch(
                "app.youtube_archive.youtube_read_services",
                return_value=(self.account, FakeDataService(), FakeAnalyticsService()),
            ):
                snapshot = collect_youtube_channel_archive(self.account.id, collected_at=self.collected_at, max_pages=1)

            manifest = json.loads((snapshot.path / "manifest.json").read_text(encoding="utf-8"))
            self.assertFalse(manifest["sources"]["youtube_data_api"]["uploads_complete"])
            self.assertEqual(manifest["sources"]["youtube_data_api"]["uploads_found"], 1)

    def test_missing_analytics_scope_creates_no_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive_root = Path(temporary) / "channel_archive"
            with patch("app.youtube_archive.youtube_channel_archive_dir", return_value=archive_root), patch(
                "app.youtube_archive.youtube_read_services",
                side_effect=YouTubeError("reconecte a conta"),
            ):
                with self.assertRaisesRegex(YouTubeArchiveError, "reconecte"):
                    collect_youtube_channel_archive(self.account.id, collected_at=self.collected_at)

            self.assertFalse(archive_root.exists())

    def test_api_errors_have_specific_user_messages(self):
        def error(status: int) -> HttpError:
            payload = json.dumps({"error": {"code": status, "message": "falha"}}).encode("utf-8")
            return HttpError(Response({"status": str(status)}), payload)

        self.assertIn("relatório solicitado não é suportado", str(_api_error("ler dados", error(400))))
        self.assertIn("não autorizou", str(_api_error("ler dados", error(403))))
        self.assertIn("cota", str(_api_error("ler dados", error(429))))


if __name__ == "__main__":
    unittest.main()
