import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.schemas import VideoProject, example_project
from app.youtube import (
    YouTubeAccount,
    YouTubeAlreadyPublishedError,
    _save_account,
    list_youtube_accounts,
    load_youtube_publication,
    publish_to_youtube,
    remove_youtube_account,
    youtube_video_resource,
)


class FakeCredentials:
    def to_json(self):
        return json.dumps({"token": "secret-token", "refresh_token": "secret-refresh-token"})


class FakeUploadStatus:
    def progress(self):
        return 0.5


class FakeUploadRequest:
    def __init__(self):
        self.calls = 0

    def next_chunk(self):
        self.calls += 1
        if self.calls == 1:
            return FakeUploadStatus(), None
        return None, {"id": "video-123"}


class FakeVideosResource:
    def __init__(self, request):
        self.request = request
        self.kwargs = None

    def insert(self, **kwargs):
        self.kwargs = kwargs
        return self.request


class FakeYouTubeService:
    def __init__(self, request):
        self.videos_resource = FakeVideosResource(request)

    def videos(self):
        return self.videos_resource


def project_for_youtube() -> VideoProject:
    data = example_project().model_dump()
    data["youtube"] = {
        "default_language": "pt-BR",
        "description": "Descrição de teste.",
        "tags": ["teste", "shorts"],
        "category_id": "27",
        "status": {
            "privacy_status": "private",
            "license": "youtube",
            "embeddable": True,
            "public_stats_viewable": True,
            "self_declared_made_for_kids": False,
            "contains_synthetic_media": True,
        },
        "notify_subscribers": False,
        "captions": {"enabled": True, "language": "pt-BR", "format": "vtt"},
    }
    return VideoProject.model_validate(data)


class YouTubeTests(unittest.TestCase):
    def test_video_resource_maps_validated_project_metadata(self):
        project = project_for_youtube()

        resource = youtube_video_resource(project)

        self.assertEqual(resource["snippet"]["title"], project.title)
        self.assertEqual(resource["snippet"]["description"], "Descrição de teste.")
        self.assertEqual(resource["snippet"]["tags"], ["teste", "shorts"])
        self.assertEqual(resource["status"]["privacyStatus"], "private")
        self.assertTrue(resource["status"]["containsSyntheticMedia"])

    def test_accounts_are_local_and_token_is_removed_with_account(self):
        account = YouTubeAccount(
            id="a" * 32,
            label="Canal de testes",
            channel_id="UC123",
            channel_title="Canal de testes oficial",
        )
        with tempfile.TemporaryDirectory() as temp_dir, patch("app.youtube.youtube_data_dir", return_value=Path(temp_dir)):
            _save_account(account, FakeCredentials())

            self.assertEqual(list_youtube_accounts(), (account,))
            token_path = Path(temp_dir) / "tokens" / f"{account.id}.json"
            self.assertTrue(token_path.is_file())
            self.assertIn("secret-token", token_path.read_text(encoding="utf-8"))

            remove_youtube_account(account.id)

            self.assertEqual(list_youtube_accounts(), ())
            self.assertFalse(token_path.exists())

    def test_upload_uses_resumable_request_and_prevents_duplicate_video(self):
        project = project_for_youtube()
        account = YouTubeAccount(
            id="b" * 32,
            label="Canal de publicação",
            channel_id="UC456",
            channel_title="Canal de publicação oficial",
        )
        request = FakeUploadRequest()
        service = FakeYouTubeService(request)
        progress = []
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = Path(temp_dir) / "short.mp4"
            video_path.write_bytes(b"mp4-test-content")
            with patch("app.youtube.get_youtube_account", return_value=account), patch(
                "app.youtube._credentials_for_account", return_value=FakeCredentials()
            ), patch("app.youtube._youtube_service", return_value=service):
                publication = publish_to_youtube(
                    project,
                    video_path,
                    account.id,
                    progress=lambda message, fraction=None: progress.append((message, fraction)),
                )

                self.assertEqual(publication.video_id, "video-123")
                self.assertEqual(service.videos_resource.kwargs["part"], "snippet,status")
                self.assertFalse(service.videos_resource.kwargs["notifySubscribers"])
                self.assertEqual(service.videos_resource.kwargs["body"]["snippet"]["title"], project.title)
                self.assertTrue(any(fraction == 0.5 for _, fraction in progress))
                self.assertEqual(load_youtube_publication(video_path), publication)

                with self.assertRaises(YouTubeAlreadyPublishedError):
                    publish_to_youtube(project, video_path, account.id)


if __name__ == "__main__":
    unittest.main()
