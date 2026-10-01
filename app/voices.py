from __future__ import annotations


KOKORO_VOICES: tuple[tuple[str, str], ...] = (
    ("Dora — feminina", "pf_dora"),
    ("Alex — masculina", "pm_alex"),
    ("Santa — masculina", "pm_santa"),
)

VOICE_CODES = frozenset(code for _, code in KOKORO_VOICES)
DEFAULT_VOICE = "pf_dora"

TTS_ENGINES: tuple[tuple[str, str], ...] = (
    ("Kokoro pt-BR", "kokoro"),
    ("Chatterbox PT-BR", "chatterbox_ptbr"),
)

TTS_ENGINE_CODES = frozenset(code for _, code in TTS_ENGINES)
DEFAULT_TTS_ENGINE = "kokoro"


def normalize_voice(value: str | None) -> str:
    candidate = (value or "").strip()
    return candidate if candidate in VOICE_CODES else DEFAULT_VOICE


def normalize_tts_engine(value: str | None) -> str:
    candidate = (value or "").strip()
    return candidate if candidate in TTS_ENGINE_CODES else DEFAULT_TTS_ENGINE


def tts_engine_label(code: str) -> str:
    for label, engine_code in TTS_ENGINES:
        if engine_code == code:
            return label
    return "Kokoro pt-BR"


def voice_label(code: str) -> str:
    for label, voice_code in KOKORO_VOICES:
        if voice_code == code:
            return label
    return "Dora — feminina"
