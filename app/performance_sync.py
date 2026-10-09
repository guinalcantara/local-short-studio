"""Reconcilia dados online comprovados com o acompanhamento local."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.performance_models import Measurement, PerformanceVideo, SAO_PAULO, as_datetime, new_id
from app.performance_store import PerformanceStore
from app.youtube import YouTubePerformanceVideo, fetch_youtube_performance


def sync_youtube_performance(store: PerformanceStore, account_id: str, max_results: int = 50) -> tuple[int, int]:
    remote = fetch_youtube_performance(account_id, max_results=max_results)
    existing = {item.youtube_video_id: item for item in store.list_videos() if item.youtube_video_id}
    collected_at = datetime.now(SAO_PAULO).replace(microsecond=0).isoformat()
    created = 0
    for item in remote:
        video = existing.get(item.video_id)
        if video is None:
            video = PerformanceVideo(id=new_id("short"), title=item.title, channel=item.channel_title, youtube_video_id=item.video_id, youtube_url=f"https://www.youtube.com/watch?v={item.video_id}", published_at=item.published_at, duration_seconds=item.duration_seconds)
            created += 1
        else:
            # Preserve all local editorial fields and the immutable production snapshot.
            video = PerformanceVideo(**{**video.__dict__, "title": item.title or video.title, "channel": item.channel_title or video.channel, "youtube_url": f"https://www.youtube.com/watch?v={item.video_id}", "published_at": item.published_at or video.published_at, "duration_seconds": item.duration_seconds or video.duration_seconds})
        stored = store.save_video(video)
        published = as_datetime(stored.published_at)
        collected = as_datetime(collected_at)
        age = (collected - published).total_seconds() / 3600 if published and collected >= published else None
        store.save_measurement(Measurement(id=new_id("measurement"), video_id=stored.id, collected_at=collected_at, horizon="custom", custom_horizon_hours=age or 0.01, views=item.views, engaged_views=item.engaged_views, subscribers_gained=item.subscribers_gained, average_watch_seconds=item.average_watch_seconds, average_watch_percent=item.average_watch_percent, source="youtube_analytics", source_account_id=account_id))
    return len(remote), created
