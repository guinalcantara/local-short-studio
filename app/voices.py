from __future__ import annotations


KOKORO_VOICES: tuple[tuple[str, str], ...] = (
    ("Dora — feminina", "pf_dora"),
    ("Alex — masculina", "pm_alex"),
    ("Santa — masculina", "pm_santa"),
)

VOICE_CODES = frozenset(code for _, code in KOKORO_VOICES)
DEFAULT_VOICE = "pf_dora"


def normalize_voice(value: str | None) -> str:
    candidate = (value or "").strip()
    return candidate if candidate in VOICE_CODES else DEFAULT_VOICE


def voice_label(code: str) -> str:
    for label, voice_code in KOKORO_VOICES:
        if voice_code == code:
            return label
    return "Dora — feminina"
