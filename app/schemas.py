from __future__ import annotations

from pathlib import Path
import json
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator


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
    enabled: bool = False
    theme: str = "modern_blue"


class Scene(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    narration: str = Field(min_length=1, max_length=1200)
    image_prompt: str = Field(min_length=1, max_length=1600)
    motion: Motion = "auto"
    image_path: str | None = None
    seed: int | None = None

    @field_validator("id")
    @classmethod
    def safe_id(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            raise ValueError("use letras, números, hífen e sublinhado no id da cena")
        return value


class VideoProject(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    profile: str = "short_vertical"
    voice: str = "pf_dora"
    speech_speed: float = Field(default=1.0, ge=0.75, le=1.25)
    visual_style: str = Field(default="cinematic digital illustration, coherent blue and white palette", max_length=600)
    captions: Captions = Field(default_factory=Captions)
    music_path: str | None = None
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
                id="scene_01",
                narration="Escreva aqui a primeira fala da narração.",
                image_prompt="Cena vertical cinematográfica com iluminação azul suave; deixe espaço para o movimento de câmera.",
                motion="slow_push_in",
            ),
            Scene(
                id="scene_02",
                narration="Escreva aqui a próxima fala.",
                image_prompt="Segunda cena vertical no mesmo estilo visual, com enquadramento diferente.",
                motion="pan_left",
            ),
        ],
    )
