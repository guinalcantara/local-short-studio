"""SQLite local e isolado para resultados editoriais manuais."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
import sqlite3
from typing import Iterable

from app.performance_models import Measurement, PerformanceFilters, PerformanceVideo, ProductionSnapshot, SAO_PAULO


class DuplicatePerformanceVideoError(ValueError):
    pass


class PerformanceStore:
    def __init__(self, input_root: Path) -> None:
        self.path = Path(input_root) / "analytics" / "performance.sqlite3"

    def _connection(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def migrate(self) -> None:
        with self._connection() as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
            if connection.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0] == 0:
                connection.execute("INSERT INTO schema_version(version) VALUES (1)")
            connection.execute("""CREATE TABLE IF NOT EXISTS videos (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, channel TEXT NOT NULL,
                youtube_video_id TEXT, youtube_url TEXT, published_at TEXT, topic TEXT, series_name TEXT,
                hook_text TEXT, hook_type TEXT, editorial_format TEXT, duration_seconds REAL,
                scene_count INTEGER, shot_count INTEGER, production_snapshot TEXT,
                learned TEXT, next_test TEXT, main_variable TEXT, comparison_method TEXT,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
            connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS videos_youtube_id_unique ON videos(youtube_video_id) WHERE youtube_video_id IS NOT NULL")
            connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS videos_version_hash_unique ON videos(json_extract(production_snapshot, '$.version_hash')) WHERE json_extract(production_snapshot, '$.version_hash') IS NOT NULL")
            connection.execute("""CREATE TABLE IF NOT EXISTS measurements (
                id TEXT PRIMARY KEY, video_id TEXT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
                collected_at TEXT NOT NULL, horizon TEXT NOT NULL, custom_horizon_hours REAL,
                views INTEGER, engaged_views INTEGER, stayed_to_watch_percent REAL,
                average_watch_seconds REAL, average_watch_percent REAL, subscribers_gained INTEGER,
                retention_observation TEXT NOT NULL DEFAULT '', source TEXT, source_account_id TEXT)""")
            columns = {row[1] for row in connection.execute("PRAGMA table_info(measurements)")}
            if "source" not in columns:
                connection.execute("ALTER TABLE measurements ADD COLUMN source TEXT")
            if "source_account_id" not in columns:
                connection.execute("ALTER TABLE measurements ADD COLUMN source_account_id TEXT")

    @staticmethod
    def _video_from_row(row: sqlite3.Row) -> PerformanceVideo:
        snapshot = json.loads(row["production_snapshot"]) if row["production_snapshot"] else None
        return PerformanceVideo(id=row["id"], title=row["title"], channel=row["channel"], youtube_video_id=row["youtube_video_id"], youtube_url=row["youtube_url"], published_at=row["published_at"], topic=row["topic"], series=row["series_name"], hook_text=row["hook_text"], hook_type=row["hook_type"], editorial_format=row["editorial_format"], duration_seconds=row["duration_seconds"], scene_count=row["scene_count"], shot_count=row["shot_count"], production_snapshot=ProductionSnapshot(**snapshot) if snapshot else None, learned=row["learned"], next_test=row["next_test"], main_variable=row["main_variable"], comparison_method=row["comparison_method"], created_at=row["created_at"], updated_at=row["updated_at"])

    def save_video(self, video: PerformanceVideo) -> PerformanceVideo:
        self.migrate(); now = datetime.now(SAO_PAULO).isoformat()
        with self._connection() as con:
            prior = con.execute("SELECT * FROM videos WHERE id = ?", (video.id,)).fetchone()
            snapshot = video.production_snapshot
            if prior and prior["production_snapshot"]:  # snapshot de versão nunca é reescrito
                snapshot_json = prior["production_snapshot"]
            else:
                snapshot_json = json.dumps(asdict(snapshot), ensure_ascii=False, sort_keys=True) if snapshot else None
            duplicate = con.execute("SELECT id FROM videos WHERE id != ? AND ((? IS NOT NULL AND youtube_video_id = ?) OR (? IS NOT NULL AND json_extract(production_snapshot, '$.version_hash') = ?))", (video.id, video.youtube_video_id, video.youtube_video_id, snapshot.version_hash if snapshot else None, snapshot.version_hash if snapshot else None)).fetchone()
            if duplicate:
                raise DuplicatePerformanceVideoError("Já existe um acompanhamento para este vídeo do YouTube ou esta versão de MP4.")
            created = prior["created_at"] if prior else (video.created_at or now)
            values = (video.id, video.title, video.channel, video.youtube_video_id, video.youtube_url, video.published_at, video.topic, video.series, video.hook_text, video.hook_type, video.editorial_format, video.duration_seconds, video.scene_count, video.shot_count, snapshot_json, video.learned, video.next_test, video.main_variable, video.comparison_method, created, now)
            con.execute("""INSERT INTO videos VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET title=excluded.title, channel=excluded.channel, youtube_video_id=excluded.youtube_video_id, youtube_url=excluded.youtube_url, published_at=excluded.published_at, topic=excluded.topic, series_name=excluded.series_name, hook_text=excluded.hook_text, hook_type=excluded.hook_type, editorial_format=excluded.editorial_format, duration_seconds=excluded.duration_seconds, scene_count=excluded.scene_count, shot_count=excluded.shot_count, production_snapshot=excluded.production_snapshot, learned=excluded.learned, next_test=excluded.next_test, main_variable=excluded.main_variable, comparison_method=excluded.comparison_method, updated_at=excluded.updated_at""", values)
        return self.get_video(video.id)

    def get_video(self, video_id: str) -> PerformanceVideo | None:
        self.migrate()
        with self._connection() as con:
            row = con.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()
        return self._video_from_row(row) if row else None

    def list_videos(self, filters: PerformanceFilters | None = None) -> list[PerformanceVideo]:
        self.migrate(); filters = filters or PerformanceFilters(); where, params = [], []
        for column, value in (("channel", filters.channel), ("topic", filters.topic), ("series_name", filters.series), ("hook_type", filters.hook_type), ("editorial_format", filters.editorial_format)):
            if value:
                where.append(f"{column} = ?"); params.append(value)
        if filters.min_duration_seconds is not None: where.append("duration_seconds >= ?"); params.append(filters.min_duration_seconds)
        if filters.max_duration_seconds is not None: where.append("duration_seconds <= ?"); params.append(filters.max_duration_seconds)
        query = "SELECT * FROM videos" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY updated_at DESC"
        with self._connection() as con: rows = con.execute(query, params).fetchall()
        return [self._video_from_row(row) for row in rows]

    def save_measurement(self, measurement: Measurement) -> Measurement:
        self.migrate()
        with self._connection() as con:
            if not con.execute("SELECT 1 FROM videos WHERE id = ?", (measurement.video_id,)).fetchone():
                raise ValueError("O vídeo selecionado não existe.")
            con.execute("""INSERT INTO measurements (id, video_id, collected_at, horizon, custom_horizon_hours, views, engaged_views, stayed_to_watch_percent, average_watch_seconds, average_watch_percent, subscribers_gained, retention_observation, source, source_account_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET video_id=excluded.video_id, collected_at=excluded.collected_at, horizon=excluded.horizon, custom_horizon_hours=excluded.custom_horizon_hours, views=excluded.views, engaged_views=excluded.engaged_views, stayed_to_watch_percent=excluded.stayed_to_watch_percent, average_watch_seconds=excluded.average_watch_seconds, average_watch_percent=excluded.average_watch_percent, subscribers_gained=excluded.subscribers_gained, retention_observation=excluded.retention_observation, source=excluded.source, source_account_id=excluded.source_account_id""", (measurement.id, measurement.video_id, measurement.collected_at, measurement.horizon, measurement.custom_horizon_hours, measurement.views, measurement.engaged_views, measurement.stayed_to_watch_percent, measurement.average_watch_seconds, measurement.average_watch_percent, measurement.subscribers_gained, measurement.retention_observation or "", measurement.source, measurement.source_account_id))
        return measurement

    def list_measurements(self, video_id: str | None = None) -> list[Measurement]:
        self.migrate(); query, params = "SELECT * FROM measurements", []
        if video_id: query += " WHERE video_id = ?"; params.append(video_id)
        query += " ORDER BY collected_at DESC"
        with self._connection() as con: rows = con.execute(query, params).fetchall()
        return [Measurement(id=row["id"], video_id=row["video_id"], collected_at=row["collected_at"], horizon=row["horizon"], custom_horizon_hours=row["custom_horizon_hours"], views=row["views"], engaged_views=row["engaged_views"], stayed_to_watch_percent=row["stayed_to_watch_percent"], average_watch_seconds=row["average_watch_seconds"], average_watch_percent=row["average_watch_percent"], subscribers_gained=row["subscribers_gained"], retention_observation=row["retention_observation"], source=row["source"], source_account_id=row["source_account_id"]) for row in rows]
