import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app import youtube
from app.schemas import VideoProject, example_project
from app.youtube import (
    YouTubeAccount,
    YouTubeAlreadyPublishedError,
    YouTubeAuthorization,
    _save_account,
    cancel_youtube_authorization,
    list_youtube_accounts,
    load_youtube_publication,
    pending_youtube_authorization,
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
        self.insert_calls = 0

    def insert(self, **kwargs):
        self.insert_calls += 1
        self.kwargs = kwargs
        return self.request


class FakeCaptionRequest:
    def execute(self):
        return {"id": "caption-456"}


class FakeCaptionsResource:
    def __init__(self):
        self.kwargs = None
        self.insert_calls = 0

    def insert(self, **kwargs):
        self.insert_calls += 1
        self.kwargs = kwargs
        return FakeCaptionRequest()


class FakeYouTubeService:
    def __init__(self, request):
        self.videos_resource = FakeVideosResource(request)
        self.captions_resource = FakeCaptionsResource()

    def videos(self):
        return self.videos_resource

    def captions(self):
        return self.captions_resource


class FakeCallbackServer:
    def __init__(self):
        self.shutdown_called = False
        self.server_close_called = False

    def shutdown(self):
        self.shutdown_called = True

    def server_close(self):
        self.server_close_called = True


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

    def test_pending_authorization_can_be_recovered_after_page_refresh_or_cancelled(self):
        authorization = YouTubeAuthorization(
            state="pending-state",
            authorization_url="https://accounts.google.com/example",
            requested_label="Canal de testes",
            flow=None,
        )
        server = FakeCallbackServer()
        with patch.object(youtube, "_PENDING_AUTHORIZATIONS", {authorization.state: authorization}), patch.object(
            youtube, "_CALLBACK_SERVER", server
        ):
            self.assertIs(pending_youtube_authorization(), authorization)

            cancel_youtube_authorization(authorization.state)

            self.assertEqual(authorization.status, "cancelled")
            self.assertIsNone(pending_youtube_authorization())
            self.assertTrue(server.shutdown_called)
            self.assertTrue(server.server_close_called)

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
            video_path.with_suffix(".srt").write_text(
                "1\n00:00:00,000 --> 00:00:01,000\nLEGENDA DE TESTE\n",
                encoding="utf-8",
            )
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
                self.assertIsNotNone(publication.caption)
                self.assertEqual(publication.caption.caption_id, "caption-456")
                self.assertEqual(publication.caption.format, "vtt")
                self.assertEqual(service.captions_resource.kwargs["part"], "snippet")
                self.assertEqual(service.captions_resource.kwargs["body"]["snippet"]["videoId"], "video-123")
                self.assertEqual(service.captions_resource.kwargs["body"]["snippet"]["language"], "pt-BR")
                vtt_path = video_path.with_suffix(".vtt")
                self.assertTrue(vtt_path.is_file())
                self.assertTrue(vtt_path.read_text(encoding="utf-8").startswith("WEBVTT\n\n"))
                self.assertEqual(load_youtube_publication(video_path), publication)

                with self.assertRaises(YouTubeAlreadyPublishedError):
                    publish_to_youtube(project, video_path, account.id)
                self.assertEqual(service.videos_resource.insert_calls, 1)
                self.assertEqual(service.captions_resource.insert_calls, 1)

    def test_pending_caption_can_be_sent_without_reuploading_the_mp4(self):
        project = project_for_youtube()
        project.youtube.captions.enabled = False
        account = YouTubeAccount(
            id="c" * 32,
            label="Canal de publicação",
            channel_id="UC789",
            channel_title="Canal de publicação oficial",
        )
        service = FakeYouTubeService(FakeUploadRequest())
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = Path(temp_dir) / "short.mp4"
            video_path.write_bytes(b"mp4-test-content")
            with patch("app.youtube.get_youtube_account", return_value=account), patch(
                "app.youtube._credentials_for_account", return_value=FakeCredentials()
            ), patch("app.youtube._youtube_service", return_value=service):
                initial_publication = publish_to_youtube(project, video_path, account.id)

                project.youtube.captions.enabled = True
                project.youtube.captions.format = "srt"
                video_path.with_suffix(".srt").write_text(
                    "1\n00:00:00,000 --> 00:00:01,000\nLEGENDA DE TESTE\n",
                    encoding="utf-8",
                )
                recovered_publication = publish_to_youtube(project, video_path, account.id)

        self.assertEqual(recovered_publication.video_id, initial_publication.video_id)
        self.assertIsNotNone(recovered_publication.caption)
        self.assertEqual(recovered_publication.caption.format, "srt")
        self.assertEqual(service.videos_resource.insert_calls, 1)
        self.assertEqual(service.captions_resource.insert_calls, 1)


if __name__ == "__main__":
    unittest.main()
