from __future__ import annotations

from pathlib import Path
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
_WORD_RE = re.compile(r"\w+", flags=re.UNICODE)


def _safe_image_path(value: str) -> str:
    if "\\" in value or "/" in value or value in {".", ".."} or re.match(r"^[A-Za-z]:", value):
        raise ValueError("image_path deve ser somente o nome do arquivo, sem pastas")
    if Path(value).suffix.lower() not in _IMAGE_EXTENSIONS:
        raise ValueError("image_path deve terminar em .png, .jpg, .jpeg ou .webp")
    return value


def normalized_words(text: str) -> tuple[str, ...]:
    """Normalize only case, whitespace and punctuation for lexical matching."""
    return tuple(match.group(0).casefold() for match in _WORD_RE.finditer(text))


def phrase_word_span(narration: str, phrase: str) -> tuple[int, int]:
    """Return the unique contiguous word span for an anchor phrase."""
    narration_words = normalized_words(narration)
    phrase_words = normalized_words(phrase)
    if not phrase_words:
        raise ValueError("a frase ancora precisa conter palavras")
    size = len(phrase_words)
    matches = [
        index
        for index in range(len(narration_words) - size + 1)
        if narration_words[index:index + size] == phrase_words
    ]
    if not matches:
        raise ValueError("a frase ancora nao aparece como sequencia contigua na narracao")
    if len(matches) > 1:
        raise ValueError("a frase ancora aparece mais de uma vez na narracao")
    return matches[0], matches[0] + size


def _sentence_word_indices(text: str) -> tuple[int, ...]:
    sentence_by_word: list[int] = []
    sentence_index = 0
    cursor = 0
    for match in _WORD_RE.finditer(text):
        between = text[cursor:match.start()]
        if sentence_by_word and re.search(r"[.!?…]", between):
            sentence_index += 1
        sentence_by_word.append(sentence_index)
        cursor = match.end()
    return tuple(sentence_by_word)


class Captions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    theme: str = "modern_blue"


class Soundtrack(BaseModel):
    model_config = ConfigDict(extra="forbid")

    track_id: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9_]+$")
    volume_percent: int = Field(ge=0, le=12, strict=True)


class Shot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_path: str = Field(min_length=1, max_length=255)
    start_phrase: str | None = Field(default=None, max_length=400)
    motion: Motion | None = None

    @field_validator("image_path")
    @classmethod
    def safe_image_path(cls, value: str) -> str:
        return _safe_image_path(value)


class SceneTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["cut", "crossfade", "fade_black"]
    duration_seconds: float | None = Field(default=None, ge=0.15, le=0.45)

    @model_validator(mode="after")
    def validate_duration(self) -> "SceneTransition":
        if self.type == "cut" and self.duration_seconds is not None:
            raise ValueError("duration_seconds deve ser omitido quando type for cut")
        return self


class Scene(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=40)
    narration: str = Field(min_length=1, max_length=1200)
    image_path: str = Field(min_length=1, max_length=255)
    motion: Motion = "auto"
    seed: int | None = None
    shots: list[Shot] | None = None
    transition_to_next: SceneTransition | None = None

    @field_validator("id")
    @classmethod
    def safe_id(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            raise ValueError("use letras, números, hífen e sublinhado no id da cena")
        return value

    @field_validator("image_path")
    @classmethod
    def safe_image_path(cls, value: str) -> str:
        return _safe_image_path(value)

    @model_validator(mode="after")
    def validate_shots(self) -> "Scene":
        if self.shots is None:
            return self
        if not 2 <= len(self.shots) <= 4:
            raise ValueError(f"cena {self.id}: shots deve conter de 2 a 4 planos")
        if self.shots[0].start_phrase is not None:
            raise ValueError(f"cena {self.id}, plano 1: o primeiro plano deve omitir start_phrase")
        if self.shots[0].image_path != self.image_path:
            raise ValueError(
                f"cena {self.id}, plano 1: image_path deve ser exatamente igual ao image_path da cena"
            )

        seen_images: dict[str, int] = {}
        previous_start = -1
        sentence_indices = _sentence_word_indices(self.narration)
        for index, shot in enumerate(self.shots):
            image_key = shot.image_path.casefold()
            if image_key in seen_images:
                raise ValueError(
                    f"cena {self.id}, plano {index + 1}: image_path repete o plano "
                    f"{seen_images[image_key] + 1}"
                )
            seen_images[image_key] = index
            if index == 0:
                continue
            if shot.start_phrase is None or not shot.start_phrase.strip():
                raise ValueError(f"cena {self.id}, plano {index + 1}: start_phrase e obrigatoria e nao pode ser vazia")
            try:
                start, end = phrase_word_span(self.narration, shot.start_phrase)
            except ValueError as exc:
                raise ValueError(
                    f"cena {self.id}, plano {index + 1}, frase {shot.start_phrase!r}: {exc}"
                ) from exc
            if not sentence_indices or sentence_indices[start] != sentence_indices[end - 1]:
                raise ValueError(
                    f"cena {self.id}, plano {index + 1}, frase {shot.start_phrase!r}: "
                    "a frase ancora nao pode atravessar duas frases"
                )
            if start <= previous_start:
                raise ValueError(
                    f"cena {self.id}, plano {index + 1}, frase {shot.start_phrase!r}: "
                    "as frases ancora devem seguir a ordem da narracao"
                )
            previous_start = start
        return self

    def visual_shots(self) -> tuple[Shot, ...]:
        if self.shots is not None:
            return tuple(self.shots)
        return (Shot(image_path=self.image_path, motion=self.motion),)


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
    soundtrack: Soundtrack | None = None
    music_path: str | None = None
    youtube: YouTubeMetadata | None = None
    scenes: list[Scene] = Field(min_length=1, max_length=20)

    @field_validator("profile")
    @classmethod
    def allowed_profile(cls, value: str) -> str:
        if value not in {"short_vertical", "video_landscape"}:
            raise ValueError("perfil deve ser short_vertical ou video_landscape")
        return value

    @model_validator(mode="after")
    def validate_scene_transitions(self) -> "VideoProject":
        if self.soundtrack is not None and self.music_path is not None:
            raise ValueError("soundtrack e music_path não podem ser usados ao mesmo tempo")
        if self.scenes[-1].transition_to_next is not None:
            raise ValueError(
                f"cena {self.scenes[-1].id}: transition_to_next não é permitido na última cena"
            )
        return self

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
