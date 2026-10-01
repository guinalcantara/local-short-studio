from __future__ import annotations

from pathlib import Path
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


Motion = Literal[
    "slow_push_in",
    "slow_pull_out",
    "pan_left",
    "pan_right",
    "pan_up",
    "pan_down",
    "static",
    "auto",
]


class Captions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    theme: str = "modern_blue"


class Scene(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=40)
    narration: str = Field(min_length=1, max_length=1200)
    image_path: str = Field(min_length=1, max_length=255)
    motion: Motion = "auto"
    seed: int | None = None

    @field_validator("id")
    @classmethod
    def safe_id(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            raise ValueError("use letras, números, hífen e sublinhado no id da cena")
        return value

    @field_validator("image_path")
    @classmethod
    def safe_image_path(cls, value: str) -> str:
        if "\\" in value or "/" in value or value in {".", ".."} or re.match(r"^[A-Za-z]:", value):
            raise ValueError("image_path deve ser somente o nome do arquivo, sem pastas")
        if Path(value).suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise ValueError("image_path deve terminar em .png, .jpg, .jpeg ou .webp")
        return value


class YouTubeStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    privacy_status: Literal["private", "unlisted", "public"] = "private"
    license: Literal["youtube", "creativeCommon"] = "youtube"
    embeddable: bool = True
    public_stats_viewable: bool = True
    self_declared_made_for_kids: bool = False
    contains_synthetic_media: bool = True


class YouTubeCaptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    language: str = Field(default="pt-BR", min_length=2, max_length=20)
    format: Literal["vtt", "srt"] = "vtt"


class YouTubeMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_language: str = Field(default="pt-BR", min_length=2, max_length=20)
    description: str = Field(default="", max_length=5000)
    tags: list[str] = Field(default_factory=list, max_length=500)
    category_id: str = Field(default="27", pattern=r"^[0-9]+$", max_length=4)
    status: YouTubeStatus = Field(default_factory=YouTubeStatus)
    notify_subscribers: bool = True
    captions: YouTubeCaptions = Field(default_factory=YouTubeCaptions)


class VideoProject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=100)
    profile: str = "short_vertical"
    voice: str = "pf_dora"
    speech_speed: float = Field(default=1.0, ge=0.75, le=1.25)
    visual_style: str = Field(default="cinematic digital illustration, coherent blue and white palette", max_length=600)
    captions: Captions = Field(default_factory=Captions)
    music_path: str | None = None
    youtube: YouTubeMetadata | None = None
    scenes: list[Scene] = Field(min_length=1, max_length=20)

    @field_validator("profile")
    @classmethod
    def allowed_profile(cls, value: str) -> str:
        if value not in {"short_vertical", "video_landscape"}:
            raise ValueError("perfil deve ser short_vertical ou video_landscape")
        return value

    @classmethod
    def from_json_file(cls, path: str | Path) -> "VideoProject":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))

    @classmethod
    def from_json_text(cls, content: str) -> "VideoProject":
        return cls.model_validate_json(content)

    def to_json(self) -> str:
        return self.model_dump_json(indent=2)

    def narration_text(self) -> str:
        return "\n\n".join(scene.narration.strip() for scene in self.scenes)


def example_project() -> VideoProject:
    return VideoProject(
        title="Meu primeiro Short",
        profile="short_vertical",
        voice="pf_dora",
        visual_style="cinematic digital illustration, coherent blue and white palette",
        captions=Captions(enabled=False),
        scenes=[
            Scene(
                id="cena_01_gancho",
                narration="Escreva aqui a primeira fala da narração.",
                image_path="cena_01_gancho.png",
                motion="slow_push_in",
            ),
            Scene(
                id="cena_02_contexto",
                narration="Escreva aqui a próxima fala.",
                image_path="cena_02_contexto.png",
                motion="pan_left",
            ),
        ],
    )
