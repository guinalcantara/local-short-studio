from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
from typing import Any


CATALOG_VERSION = 1
CATALOG_FILENAME = "catalog.json"
BUNDLED_LIBRARY_ROOT = Path("/workspace/assets/music_library")
TRACKS_RELATIVE_ROOT = PurePosixPath("faixas")
DEFAULT_MAX_CATALOG_BYTES = 5 * 1024 * 1024
DEFAULT_MAX_TRACK_BYTES = 100 * 1024 * 1024
TRACK_ID_RE = re.compile(r"^[a-z0-9_]{1,100}$")
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")


class MusicCatalogError(ValueError):
    pass


class AudioLevelError(RuntimeError):
    pass


@dataclass(frozen=True)
class CatalogTrack:
    id: str
    path: Path
    relative_path: str
    title: str
    artist_candidate: str | None
    category: str
    best_for_estimate: str | None
    duration_seconds: float
    measured_lufs: float
    recommended_volume_percent: int
    selection_status: str
    license_status: str
    license_url: str | None
    source_url: str | None
    attribution_text: str | None
    sha256: str


@dataclass(frozen=True)
class MusicCatalog:
    root: Path
    tracks: tuple[CatalogTrack, ...]

    def get(self, track_id: str, *, editorial_only: bool = True, verify_sha256: bool = False) -> CatalogTrack:
        track = next((item for item in self.tracks if item.id == track_id), None)
        if track is None:
            raise MusicCatalogError(f"Faixa desconhecida no catálogo: {track_id!r}.")
        if editorial_only and track.selection_status != "editorial_candidate":
            raise MusicCatalogError(
                f"A faixa {track_id!r} não pode ser selecionada: "
                f"selection_status={track.selection_status!r}."
            )
        if verify_sha256:
            digest = _sha256(track.path)
            if digest != track.sha256:
                raise MusicCatalogError(
                    f"O arquivo da faixa {track_id!r} não corresponde ao SHA-256 do catálogo."
                )
        return track

    def editorial_tracks(self) -> tuple[CatalogTrack, ...]:
        return tuple(
            sorted(
                (track for track in self.tracks if track.selection_status == "editorial_candidate"),
                key=lambda track: (track.category.casefold(), track.title.casefold(), track.id),
            )
        )


def _require_mapping(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MusicCatalogError(f"{context} deve ser um objeto JSON.")
    return value


def _require_string(data: dict[str, Any], key: str, context: str, *, allow_empty: bool = False) -> str:
    value = data.get(key)
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise MusicCatalogError(f"{context}.{key} deve ser texto não vazio.")
    return value


def _optional_string(data: dict[str, Any], key: str, context: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise MusicCatalogError(f"{context}.{key} deve ser texto não vazio ou null.")
    return value


def _finite_number(data: dict[str, Any], key: str, context: str) -> float:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MusicCatalogError(f"{context}.{key} deve ser numérico.")
    result = float(value)
    if not math.isfinite(result):
        raise MusicCatalogError(f"{context}.{key} deve ser finito.")
    return result


def _integer(data: dict[str, Any], key: str, context: str, minimum: int, maximum: int) -> int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise MusicCatalogError(
            f"{context}.{key} deve ser inteiro entre {minimum} e {maximum}."
        )
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_track_path(raw_path: str, catalog_root: Path, tracks_root: Path, context: str) -> tuple[Path, str]:
    if "\\" in raw_path:
        raise MusicCatalogError(f"{context}.path deve usar barras normais e ser relativo a faixas/.")
    relative = PurePosixPath(raw_path)
    if relative.is_absolute() or not relative.parts or relative.parts[0] != TRACKS_RELATIVE_ROOT.name:
        raise MusicCatalogError(f"{context}.path deve ficar dentro de faixas/.")
    if any(part in {"", ".", ".."} for part in relative.parts):
        raise MusicCatalogError(f"{context}.path contém segmento inseguro.")
    if relative.suffix.lower() != ".mp3":
        raise MusicCatalogError(f"{context}.path deve apontar para um arquivo MP3.")

    candidate = catalog_root.joinpath(*relative.parts)
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise MusicCatalogError(f"Arquivo ausente para {context}: {raw_path}.") from exc
    try:
        resolved.relative_to(tracks_root)
    except ValueError as exc:
        raise MusicCatalogError(f"{context}.path escapa da raiz faixas/ da biblioteca.") from exc
    if not resolved.is_file():
        raise MusicCatalogError(f"{context}.path não é um arquivo regular.")
    max_bytes = int(os.getenv("MUSIC_MAX_TRACK_BYTES", str(DEFAULT_MAX_TRACK_BYTES)))
    size = resolved.stat().st_size
    if size <= 0 or size > max_bytes:
        raise MusicCatalogError(
            f"{context}.path deve ter entre 1 e {max_bytes} bytes; tamanho encontrado: {size}."
        )
    return resolved, relative.as_posix()


def resolve_music_library_root(input_root: str | Path) -> Path:
    """Prefer an explicit local override, then use the library bundled in the image."""
    local_override = Path(input_root).resolve() / "music_library"
    if local_override.exists():
        return local_override
    return Path(os.getenv("MUSIC_LIBRARY_DIR", str(BUNDLED_LIBRARY_ROOT)))


def load_music_catalog(input_root: str | Path) -> MusicCatalog:
    input_path = Path(input_root).resolve()
    configured_root = resolve_music_library_root(input_path)
    catalog_path = configured_root / CATALOG_FILENAME
    try:
        music_root = configured_root.resolve(strict=True)
    except FileNotFoundError as exc:
        raise MusicCatalogError(
            f"Biblioteca de músicas não encontrada em {configured_root}. "
            "Reconstrua a imagem ou configure MUSIC_LIBRARY_DIR."
        ) from exc
    try:
        resolved_catalog = catalog_path.resolve(strict=True)
    except FileNotFoundError as exc:
        raise MusicCatalogError(f"Catálogo de músicas não encontrado em {catalog_path}.") from exc
    try:
        resolved_catalog.relative_to(music_root)
    except ValueError as exc:
        raise MusicCatalogError("O catálogo de músicas escapa da raiz configurada.") from exc
    max_catalog_bytes = int(os.getenv("MUSIC_MAX_CATALOG_BYTES", str(DEFAULT_MAX_CATALOG_BYTES)))
    if not resolved_catalog.is_file() or resolved_catalog.stat().st_size > max_catalog_bytes:
        raise MusicCatalogError("O catálogo de músicas não é um arquivo regular de tamanho aceitável.")
    try:
        data = json.loads(resolved_catalog.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MusicCatalogError(f"Não foi possível ler o catálogo de músicas: {exc}") from exc
    root = _require_mapping(data, "catalog")
    if root.get("version") != CATALOG_VERSION:
        raise MusicCatalogError(
            f"Versão de catálogo incompatível: esperado {CATALOG_VERSION}, recebido {root.get('version')!r}."
        )
    raw_tracks = root.get("tracks")
    if not isinstance(raw_tracks, list) or not raw_tracks:
        raise MusicCatalogError("catalog.tracks deve ser uma lista não vazia.")

    try:
        tracks_root = (music_root / TRACKS_RELATIVE_ROOT.name).resolve(strict=True)
    except FileNotFoundError as exc:
        raise MusicCatalogError("A pasta faixas/ não foi encontrada na biblioteca de músicas.") from exc
    try:
        tracks_root.relative_to(music_root)
    except ValueError as exc:
        raise MusicCatalogError("A pasta faixas/ não pode apontar para fora da biblioteca.") from exc
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    tracks: list[CatalogTrack] = []
    for index, raw_track in enumerate(raw_tracks):
        context = f"catalog.tracks[{index}]"
        item = _require_mapping(raw_track, context)
        track_id = _require_string(item, "id", context)
        if not TRACK_ID_RE.fullmatch(track_id):
            raise MusicCatalogError(f"{context}.id deve corresponder a [a-z0-9_]+ e ter até 100 caracteres.")
        id_key = track_id.casefold()
        if id_key in seen_ids:
            raise MusicCatalogError(f"ID de faixa duplicado no catálogo: {track_id!r}.")
        seen_ids.add(id_key)

        raw_path = _require_string(item, "path", context)
        path, relative_path = _safe_track_path(raw_path, music_root, tracks_root, context)
        path_key = relative_path.casefold()
        if path_key in seen_paths:
            raise MusicCatalogError(f"Caminho de faixa duplicado no catálogo: {relative_path!r}.")
        seen_paths.add(path_key)

        duration = _finite_number(item, "duration_seconds", context)
        if not 0 < duration <= 6 * 60 * 60:
            raise MusicCatalogError(f"{context}.duration_seconds está fora do intervalo aceito.")
        measured_lufs = _finite_number(item, "measured_lufs", context)
        if not -100.0 < measured_lufs < 20.0:
            raise MusicCatalogError(f"{context}.measured_lufs está fora do intervalo aceito.")
        sha256 = _require_string(item, "sha256", context)
        if not SHA256_RE.fullmatch(sha256):
            raise MusicCatalogError(f"{context}.sha256 deve conter 64 dígitos hexadecimais minúsculos.")

        tracks.append(
            CatalogTrack(
                id=track_id,
                path=path,
                relative_path=relative_path,
                title=_require_string(item, "title", context),
                artist_candidate=_optional_string(item, "artist_candidate", context),
                category=_require_string(item, "category", context),
                best_for_estimate=_optional_string(item, "best_for_estimate", context),
                duration_seconds=duration,
                measured_lufs=measured_lufs,
                recommended_volume_percent=_integer(
                    item, "recommended_volume_percent", context, 0, 12
                ),
                selection_status=_require_string(item, "selection_status", context),
                license_status=_require_string(item, "license_status", context),
                license_url=_optional_string(item, "license_url", context),
                source_url=_optional_string(item, "source_url", context),
                attribution_text=_optional_string(item, "attribution_text", context),
                sha256=sha256,
            )
        )
    return MusicCatalog(music_root, tuple(tracks))


def calculate_catalog_gain(
    requested_percent: int | float,
    voice_lufs: float,
    music_lufs: float,
) -> float:
    """Return a conservative linear gain capped by request, voice gap and -38 LUFS."""
    values = (float(requested_percent), float(voice_lufs), float(music_lufs))
    if not all(math.isfinite(value) for value in values):
        raise AudioLevelError("Não foi possível calcular o ganho: uma medição LUFS é inválida.")
    requested, voice_level, music_level = values
    if not 0.0 <= requested <= 12.0:
        raise AudioLevelError("O volume catalogado deve ficar entre 0% e 12%.")
    if not -100.0 < voice_level < 20.0:
        raise AudioLevelError("A narração está silenciosa ou fora da faixa LUFS aceita.")
    if not -100.0 < music_level < 20.0:
        raise AudioLevelError("A medição LUFS da música está fora da faixa aceita.")
    requested_gain = requested / 100.0
    voice_gap_gain = 10 ** ((voice_level - 20.0 - music_level) / 20.0)
    music_ceiling_gain = 10 ** ((-38.0 - music_level) / 20.0)
    return max(0.0, min(requested_gain, voice_gap_gain, music_ceiling_gain))


def measure_integrated_lufs(audio_path: str | Path) -> float:
    path = Path(audio_path)
    if not path.is_file():
        raise AudioLevelError(f"Áudio não encontrado para medição LUFS: {path}.")
    command = [
        "ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
        "-af", "loudnorm=I=-24:LRA=7:TP=-2:print_format=json", "-f", "null", "-",
    ]
    try:
        result = subprocess.run(command, text=True, capture_output=True)
    except FileNotFoundError as exc:
        raise AudioLevelError("FFmpeg não foi encontrado para medir a narração.") from exc
    if result.returncode:
        raise AudioLevelError("FFmpeg falhou ao medir a narração.\n" + result.stderr[-2000:])
    matches = re.findall(r'"input_i"\s*:\s*"?([^",}\s]+)', result.stderr)
    if not matches:
        raise AudioLevelError("O FFmpeg não retornou a intensidade integrada da narração.")
    try:
        measured = float(matches[-1])
    except ValueError as exc:
        raise AudioLevelError("A narração está silenciosa e não possui LUFS integrado válido.") from exc
    if not math.isfinite(measured) or measured <= -100.0:
        raise AudioLevelError("A narração está silenciosa e não possui LUFS integrado válido.")
    return measured
