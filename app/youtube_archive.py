from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
import json
import os
from pathlib import Path
import re
import shutil
from typing import Any, Callable, Iterable
from uuid import uuid4

from googleapiclient.errors import HttpError

from app.youtube import YouTubeError, youtube_read_services


ARCHIVE_SCHEMA_VERSION = 1
_DEFAULT_MAX_PAGES = 1_000
_MAX_PAGE_SIZE = 50
_SENSITIVE_KEY = re.compile(r"(?:token|secret|cookie|authorization|email|password)", re.IGNORECASE)
_ANALYTICS_METRICS = (
    "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,"
    "likes,comments,shares,subscribersGained,subscribersLost"
)


class YouTubeArchiveError(YouTubeError):
    """Raised when a read-only channel archive cannot be collected safely."""


@dataclass(frozen=True)
class YouTubeArchiveSnapshot:
    path: Path
    account_id: str
    channel_id: str
    collected_at: str
    video_count: int
    analytics_row_count: int
    uploads_pages: int
    analytics_pages: int


def youtube_channel_archive_dir() -> Path:
    input_root = Path(os.getenv("INPUT_DIR", "/workspace/input"))
    return Path(os.getenv("YOUTUBE_CHANNEL_ARCHIVE_DIR", str(input_root / "channel_archive")))


def _max_pages() -> int:
    raw = os.getenv("YOUTUBE_ARCHIVE_MAX_PAGES", str(_DEFAULT_MAX_PAGES))
    try:
        value = int(raw)
    except ValueError as exc:
        raise YouTubeArchiveError("YOUTUBE_ARCHIVE_MAX_PAGES deve ser um número inteiro positivo.") from exc
    if not 1 <= value <= 10_000:
        raise YouTubeArchiveError("YOUTUBE_ARCHIVE_MAX_PAGES deve estar entre 1 e 10000.")
    return value


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_json_lines(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _sanitize(item)
            for key, item in value.items()
            if not _SENSITIVE_KEY.search(str(key))
        }
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def _api_error(action: str, exc: HttpError) -> YouTubeArchiveError:
    status = getattr(getattr(exc, "resp", None), "status", None)
    if status == 400:
        return YouTubeArchiveError(
            f"O YouTube rejeitou a consulta para {action} porque o relatório solicitado não é suportado."
        )
    if status in {401, 403}:
        return YouTubeArchiveError(
            f"O YouTube não autorizou {action}. Reconecte a conta para conceder a leitura analítica e tente novamente."
        )
    if status == 429:
        return YouTubeArchiveError("A cota de leitura do YouTube foi atingida. Tente novamente mais tarde.")
    return YouTubeArchiveError(f"Não foi possível {action} no YouTube (HTTP {status or 'desconhecido'}).")


def _channel(data_service: Any) -> dict[str, Any]:
    try:
        response = data_service.channels().list(
            part="id,snippet,contentDetails,statistics,brandingSettings,status,topicDetails,localizations",
            mine=True,
        ).execute()
    except HttpError as exc:
        raise _api_error("ler o canal", exc) from exc
    items = response.get("items", [])
    if not isinstance(items, list) or not items:
        raise YouTubeArchiveError("A conta conectada não possui um canal disponível para leitura.")
    channel = _sanitize(items[0])
    if not isinstance(channel, dict) or not str(channel.get("id", "")).strip():
        raise YouTubeArchiveError("O YouTube não retornou o identificador do canal.")
    return channel


def _upload_ids(data_service: Any, playlist_id: str, limit: int, report: Callable[[str, float | None], None]) -> tuple[list[str], int, bool]:
    video_ids: list[str] = []
    page_token: str | None = None
    pages = 0
    while True:
        if pages >= limit:
            return video_ids, pages, False
        try:
            response = data_service.playlistItems().list(
                part="contentDetails",
                playlistId=playlist_id,
                maxResults=_MAX_PAGE_SIZE,
                pageToken=page_token,
            ).execute()
        except HttpError as exc:
            raise _api_error("listar os uploads do canal", exc) from exc
        pages += 1
        for item in response.get("items", []):
            video_id = str(item.get("contentDetails", {}).get("videoId", "")).strip()
            if video_id:
                video_ids.append(video_id)
        page_token = response.get("nextPageToken")
        report(f"Lendo uploads do canal: {len(video_ids)} vídeo(s) encontrados…", None)
        if not page_token:
            return video_ids, pages, True


def _videos(data_service: Any, video_ids: list[str], report: Callable[[str, float | None], None]) -> list[dict[str, Any]]:
    videos: list[dict[str, Any]] = []
    for index in range(0, len(video_ids), _MAX_PAGE_SIZE):
        batch = video_ids[index:index + _MAX_PAGE_SIZE]
        try:
            response = data_service.videos().list(
                part=(
                    "id,snippet,contentDetails,status,statistics,topicDetails,liveStreamingDetails,localizations,"
                    "fileDetails,processingDetails,recordingDetails,suggestions,paidProductPlacementDetails,player"
                ),
                id=",".join(batch),
                maxResults=_MAX_PAGE_SIZE,
            ).execute()
        except HttpError as exc:
            raise _api_error("ler os metadados dos vídeos", exc) from exc
        videos.extend(_sanitize(item) for item in response.get("items", []) if isinstance(item, dict))
        report(f"Lendo metadados dos vídeos: {min(index + len(batch), len(video_ids))}/{len(video_ids)}…", None)
    return videos


def _analytics_start_date(channel: dict[str, Any], fallback: date) -> str:
    published_at = str(channel.get("snippet", {}).get("publishedAt", ""))
    try:
        return datetime.fromisoformat(published_at.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return fallback.isoformat()


def _analytics_rows(
    analytics_service: Any,
    channel: dict[str, Any],
    video_ids: list[str],
    now: datetime,
    limit: int,
    report: Callable[[str, float | None], None],
) -> tuple[list[dict[str, Any]], int, bool, dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    pages = 0
    complete = True
    coverage: dict[str, Any] = {
        "videos_requested": len(video_ids),
        "videos_with_rows": [],
        "videos_without_rows": [],
        "failed_videos": [],
    }
    for video_position, video_id in enumerate(video_ids, start=1):
        columns: list[str] | None = None
        start_index = 1
        video_rows = 0
        while True:
            if pages >= limit:
                complete = False
                coverage["skipped_videos"] = video_ids[video_position - 1:]
                return rows, pages, complete, coverage
            try:
                response = analytics_service.reports().query(
                    ids="channel==MINE",
                    startDate=_analytics_start_date(channel, now.date()),
                    endDate=now.date().isoformat(),
                    metrics=_ANALYTICS_METRICS,
                    dimensions="day",
                    filters=f"video=={video_id}",
                    maxResults=200,
                    startIndex=start_index,
                ).execute()
            except HttpError as exc:
                error = _api_error(f"ler os dados analíticos do vídeo {video_id}", exc)
                if getattr(getattr(exc, "resp", None), "status", None) in {400, 401, 403, 429}:
                    raise error from exc
                complete = False
                coverage["failed_videos"].append({"video_id": video_id, "error": str(error)})
                break
            pages += 1
            if columns is None:
                columns = [str(column.get("name", "")) for column in response.get("columnHeaders", [])]
            page_rows = response.get("rows", [])
            if not isinstance(page_rows, list):
                page_rows = []
            for values in page_rows:
                if isinstance(values, list) and columns:
                    rows.append({"video_id": video_id, **{column: value for column, value in zip(columns, values, strict=False)}})
                    video_rows += 1
            report(f"Lendo dados analíticos: vídeo {video_position}/{len(video_ids)}…", None)
            if len(page_rows) < 200:
                break
            start_index += len(page_rows)
        if video_rows:
            coverage["videos_with_rows"].append(video_id)
        elif not any(item["video_id"] == video_id for item in coverage["failed_videos"]):
            coverage["videos_without_rows"].append(video_id)
    return rows, pages, complete, coverage


def collect_youtube_channel_archive(
    account_id: str,
    progress: Callable[[str, float | None], None] | None = None,
    *,
    collected_at: datetime | None = None,
    max_pages: int | None = None,
) -> YouTubeArchiveSnapshot:
    """Collect a user-requested, immutable, local snapshot of one channel.

    Nothing is fetched on import or page rendering.  Data is first collected in
    memory and then committed from a staging directory, so an API failure never
    leaves a completed-looking partial snapshot behind.
    """
    report = progress or (lambda _message, _fraction=None: None)
    now = (collected_at or datetime.now(UTC)).astimezone(UTC)
    page_limit = max_pages if max_pages is not None else _max_pages()
    if page_limit < 1:
        raise YouTubeArchiveError("O limite de páginas da coleta deve ser positivo.")
    try:
        account, data_service, analytics_service = youtube_read_services(account_id)
    except YouTubeError as exc:
        raise YouTubeArchiveError(str(exc)) from exc

    report("Lendo o canal autorizado…", 0.05)
    channel = _channel(data_service)
    uploads_id = str(channel.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads", "")).strip()
    if not uploads_id:
        raise YouTubeArchiveError("O YouTube não informou a playlist de uploads do canal.")
    report("Listando todos os uploads acessíveis…", 0.15)
    upload_ids, uploads_pages, uploads_complete = _upload_ids(data_service, uploads_id, page_limit, report)
    report("Lendo metadados e estatísticas dos vídeos…", 0.45)
    videos = _videos(data_service, upload_ids, report)
    report("Lendo dados analíticos não monetários…", 0.7)
    analytics_rows, analytics_pages, analytics_complete, analytics_coverage = _analytics_rows(
        analytics_service, channel, upload_ids, now, page_limit, report
    )

    day_directory = youtube_channel_archive_dir() / account.id / now.strftime("%Y") / now.strftime("%m") / now.strftime("%d")
    snapshot_name = now.strftime("%Y%m%dT%H%M%S%fZ") + f"-{uuid4().hex[:8]}"
    final_path = day_directory / snapshot_name
    staging_path = day_directory / f".{snapshot_name}.pending"
    if staging_path.exists() or final_path.exists():
        raise YouTubeArchiveError("Não foi possível reservar um nome único para o snapshot analítico.")
    try:
        staging_path.mkdir(parents=True, exist_ok=False)
        _write_json(staging_path / "channel.json", channel)
        _write_json_lines(staging_path / "videos.jsonl", videos)
        _write_json_lines(staging_path / "analytics_daily_video.jsonl", analytics_rows)
        manifest = {
            "schema_version": ARCHIVE_SCHEMA_VERSION,
            "collected_at": now.isoformat(),
            "account": {"id": account.id, "label": account.label, "channel_id": account.channel_id, "channel_title": account.channel_title},
            "sources": {
                "youtube_data_api": {"uploads_pages": uploads_pages, "uploads_complete": uploads_complete, "uploads_found": len(upload_ids), "videos_returned": len(videos)},
                "youtube_analytics_api": {
                    "dimensions": ["day"],
                    "video_filter": True,
                    "metrics": _ANALYTICS_METRICS.split(","),
                    "pages": analytics_pages,
                    "complete": analytics_complete,
                    "rows": len(analytics_rows),
                    "coverage": analytics_coverage,
                },
            },
            "limits": {"max_pages_per_collection": page_limit},
            "missing_data_policy": "Campos ausentes não foram inferidos; a API não os retornou nesta coleta.",
        }
        _write_json(staging_path / "manifest.json", manifest)
        staging_path.replace(final_path)
    except OSError as exc:
        raise YouTubeArchiveError("Não foi possível salvar o snapshot analítico local.") from exc
    finally:
        if staging_path.exists():
            shutil.rmtree(staging_path)
    report("Snapshot analítico salvo localmente.", 1.0)
    return YouTubeArchiveSnapshot(
        path=final_path,
        account_id=account.id,
        channel_id=account.channel_id,
        collected_at=now.isoformat(),
        video_count=len(videos),
        analytics_row_count=len(analytics_rows),
        uploads_pages=uploads_pages,
        analytics_pages=analytics_pages,
    )
