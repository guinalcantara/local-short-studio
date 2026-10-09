"""Conversão limitada de um resultado de render em evidências seguras."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.performance_models import PerformanceVideo, ProductionSnapshot, new_id
from app.workspace import file_sha256


def safe_result_prefill(video_path: Path, project: Any, effective: dict[str, Any]) -> PerformanceVideo:
    """Nunca serializa caminhos, áudio de referência, tokens ou credenciais."""
    scenes = list(getattr(project, "scenes", []) or [])
    shot_count = sum(len(scene.shots) if scene.shots else 1 for scene in scenes)
    engine = effective.get("tts_engine")
    narration: dict[str, Any] = {"engine": engine} if engine else {}
    if engine == "kokoro":
        narration["voice"] = getattr(project, "voice", None)
        narration["speed"] = getattr(project, "speed", None)
    elif engine == "chatterbox":
        narration.update({key: effective.get("chatterbox", {}).get(key) for key in ("exaggeration", "cfg_weight", "temperature") if key in effective.get("chatterbox", {})})
    music = {"source": effective.get("music_source")}
    if effective.get("music_source") in {"catalog", "json"}:
        music["track_id"] = effective.get("catalog_track_id") or getattr(getattr(project, "soundtrack", None), "track_id", None)
        music["volume_percent"] = effective.get("music_volume_percent")
    snapshot = ProductionSnapshot(version_hash=file_sha256(video_path), duration_seconds=effective.get("duration_seconds"), scene_count=len(scenes) or None, shot_count=shot_count or None, narration_engine=engine, narration_config=narration, music=music)
    return PerformanceVideo(id=new_id("short"), title=str(getattr(project, "title", "Short sem título")), channel="Meu canal", duration_seconds=effective.get("duration_seconds"), scene_count=len(scenes) or None, shot_count=shot_count or None, production_snapshot=snapshot)
