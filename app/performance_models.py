"""Modelos puros para o acompanhamento manual de resultados do canal."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from math import isfinite
import re
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

SAO_PAULO = ZoneInfo("America/Sao_Paulo")
HORIZONS = ("48h", "7d", "custom")
HOOK_TYPES = ("question", "comparison", "contradiction", "story", "other")
EDITORIAL_FORMATS = ("direct_curiosity", "mystery_with_evidence", "small_story", "other")


class PerformanceValidationError(ValueError):
    pass


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def optional_text(value: Any, field_name: str, maximum: int = 2000) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) > maximum:
        raise PerformanceValidationError(f"{field_name} excede {maximum} caracteres.")
    return text


def nonnegative_int(value: Any, field_name: str) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or int(value) != value or int(value) < 0:
        raise PerformanceValidationError(f"{field_name} deve ser um inteiro não negativo.")
    return int(value)


def nonnegative_number(value: Any, field_name: str, *, positive: bool = False) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise PerformanceValidationError(f"{field_name} deve ser numérico.") from exc
    if not isfinite(number) or number < 0 or (positive and number == 0):
        qualifier = "positivo e finito" if positive else "não negativo e finito"
        raise PerformanceValidationError(f"{field_name} deve ser {qualifier}.")
    return number


def normalize_datetime(value: datetime | str | None, field_name: str) -> str | None:
    if value is None or value == "":
        return None
    try:
        parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    except ValueError as exc:
        raise PerformanceValidationError(f"{field_name} possui data/hora inválida.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=SAO_PAULO)
    return parsed.astimezone(SAO_PAULO).isoformat()


def as_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def is_email(value: str) -> bool:
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value))


@dataclass(frozen=True)
class ProductionSnapshot:
    version_hash: str | None = None
    workspace_id: str | None = None
    execution_id: str | None = None
    duration_seconds: float | None = None
    scene_count: int | None = None
    shot_count: int | None = None
    narration_engine: str | None = None
    narration_config: dict[str, Any] = field(default_factory=dict)
    music: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "version_hash", optional_text(self.version_hash, "Hash da versão", 128))
        object.__setattr__(self, "workspace_id", optional_text(self.workspace_id, "Workspace", 128))
        object.__setattr__(self, "execution_id", optional_text(self.execution_id, "Execução", 128))
        object.__setattr__(self, "duration_seconds", nonnegative_number(self.duration_seconds, "Duração", positive=True))
        object.__setattr__(self, "scene_count", nonnegative_int(self.scene_count, "Cenas"))
        object.__setattr__(self, "shot_count", nonnegative_int(self.shot_count, "Planos"))
        # A camada de UI somente fornece dados previamente sanitizados; nunca paths/segredos.
        object.__setattr__(self, "narration_config", dict(self.narration_config or {}))
        object.__setattr__(self, "music", dict(self.music or {}))


@dataclass(frozen=True)
class PerformanceVideo:
    id: str
    title: str
    channel: str
    youtube_video_id: str | None = None
    youtube_url: str | None = None
    published_at: str | None = None
    topic: str | None = None
    series: str | None = None
    hook_text: str | None = None
    hook_type: str | None = None
    editorial_format: str | None = None
    duration_seconds: float | None = None
    scene_count: int | None = None
    shot_count: int | None = None
    production_snapshot: ProductionSnapshot | None = None
    learned: str | None = None
    next_test: str | None = None
    main_variable: str | None = None
    comparison_method: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", self.id or ""):
            raise PerformanceValidationError("ID local inválido.")
        title, channel = optional_text(self.title, "Título"), optional_text(self.channel, "Canal")
        if not title or not channel:
            raise PerformanceValidationError("Título e canal são obrigatórios.")
        if is_email(channel):
            raise PerformanceValidationError("Use um apelido do canal, não um e-mail.")
        object.__setattr__(self, "title", title); object.__setattr__(self, "channel", channel)
        for name in ("youtube_video_id", "youtube_url", "topic", "series", "hook_text", "learned", "next_test", "main_variable", "comparison_method"):
            object.__setattr__(self, name, optional_text(getattr(self, name), name.replace("_", " ")))
        if self.hook_type and self.hook_type not in HOOK_TYPES:
            raise PerformanceValidationError("Tipo de gancho inválido.")
        if self.editorial_format and self.editorial_format not in EDITORIAL_FORMATS:
            raise PerformanceValidationError("Formato editorial inválido.")
        object.__setattr__(self, "published_at", normalize_datetime(self.published_at, "Publicação"))
        object.__setattr__(self, "duration_seconds", nonnegative_number(self.duration_seconds, "Duração", positive=True))
        object.__setattr__(self, "scene_count", nonnegative_int(self.scene_count, "Cenas"))
        object.__setattr__(self, "shot_count", nonnegative_int(self.shot_count, "Planos"))
        object.__setattr__(self, "created_at", normalize_datetime(self.created_at, "Criação"))
        object.__setattr__(self, "updated_at", normalize_datetime(self.updated_at, "Atualização"))


@dataclass(frozen=True)
class Measurement:
    id: str
    video_id: str
    collected_at: str
    horizon: str
    custom_horizon_hours: float | None = None
    views: int | None = None
    engaged_views: int | None = None
    stayed_to_watch_percent: float | None = None
    average_watch_seconds: float | None = None
    average_watch_percent: float | None = None
    subscribers_gained: int | None = None
    retention_observation: str | None = None
    source: str | None = None
    source_account_id: str | None = None

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", self.id or "") or not self.video_id:
            raise PerformanceValidationError("ID de medição ou vídeo inválido.")
        if self.horizon not in HORIZONS:
            raise PerformanceValidationError("Horizonte deve ser 48h, 7d ou personalizado.")
        custom = nonnegative_number(self.custom_horizon_hours, "Horizonte personalizado", positive=True)
        if self.horizon == "custom" and custom is None:
            raise PerformanceValidationError("Informe horas para o horizonte personalizado.")
        object.__setattr__(self, "custom_horizon_hours", custom)
        object.__setattr__(self, "collected_at", normalize_datetime(self.collected_at, "Coleta"))
        for name in ("views", "engaged_views", "subscribers_gained"):
            object.__setattr__(self, name, nonnegative_int(getattr(self, name), name))
        for name in ("stayed_to_watch_percent", "average_watch_seconds", "average_watch_percent"):
            object.__setattr__(self, name, nonnegative_number(getattr(self, name), name))
        if self.stayed_to_watch_percent is not None and self.stayed_to_watch_percent > 100:
            raise PerformanceValidationError("Percentual que continuou assistindo deve ficar entre 0 e 100.")
        object.__setattr__(self, "retention_observation", optional_text(self.retention_observation, "Observação de retenção"))
        object.__setattr__(self, "source", optional_text(self.source, "Origem", 80))
        object.__setattr__(self, "source_account_id", optional_text(self.source_account_id, "Conta de origem", 100))

    @property
    def target_hours(self) -> float:
        return 48.0 if self.horizon == "48h" else 168.0 if self.horizon == "7d" else float(self.custom_horizon_hours or 0)


@dataclass(frozen=True)
class PerformanceFilters:
    channel: str | None = None
    topic: str | None = None
    series: str | None = None
    hook_type: str | None = None
    editorial_format: str | None = None
    min_duration_seconds: float | None = None
    max_duration_seconds: float | None = None
