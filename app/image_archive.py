from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import BinaryIO, Iterable
import zipfile

from PIL import Image, ImageOps, UnidentifiedImageError


ALLOWED_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp"})
IGNORED_BASENAMES = frozenset({".ds_store"})
IGNORED_PREFIXES = ("__macosx",)


class ImageZipError(ValueError):
    """Raised when the uploaded archive cannot be used safely."""


@dataclass(frozen=True)
class ZipLimits:
    max_files: int = 100
    max_compressed_bytes: int = 250 * 1024 * 1024
    max_uncompressed_bytes: int = 1024 * 1024 * 1024
    max_image_bytes: int = 50 * 1024 * 1024
    max_image_pixels: int = 40_000_000

    @classmethod
    def from_environment(cls) -> "ZipLimits":
        def integer(name: str, default: int) -> int:
            try:
                return max(1, int(os.getenv(name, str(default))))
            except ValueError:
                return default

        return cls(
            max_files=integer("ZIP_MAX_FILES", cls.max_files),
            max_compressed_bytes=integer("ZIP_MAX_COMPRESSED_BYTES", cls.max_compressed_bytes),
            max_uncompressed_bytes=integer("ZIP_MAX_UNCOMPRESSED_BYTES", cls.max_uncompressed_bytes),
            max_image_bytes=integer("ZIP_MAX_IMAGE_BYTES", cls.max_image_bytes),
            max_image_pixels=integer("ZIP_MAX_IMAGE_PIXELS", cls.max_image_pixels),
        )


@dataclass(frozen=True)
class ArchiveImage:
    basename: str
    member_name: str
    data: bytes
    width: int
    height: int
    format: str


@dataclass(frozen=True)
class ImageZipValidation:
    images: dict[str, ArchiveImage]
    found_names: tuple[str, ...]
    used_names: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def image_count(self) -> int:
        return len(self.found_names)

    def image_for(self, image_path: str) -> ArchiveImage:
        try:
            return self.images[normalize_basename(image_path)]
        except KeyError as exc:
            raise ImageZipError(f"Imagem ausente no ZIP: {image_path}") from exc


@dataclass(frozen=True)
class _Candidate:
    info: zipfile.ZipInfo
    basename: str
    key: str


def normalize_basename(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ImageZipError("image_path precisa ser um nome de arquivo não vazio.")
    name = value.strip()
    if "\\" in name or "/" in name or "\x00" in name:
        raise ImageZipError(f"image_path deve conter somente o basename: {value!r}")
    if name in {".", ".."} or re.match(r"^[A-Za-z]:", name):
        raise ImageZipError(f"image_path inválido: {value!r}")
    if Path(name).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ImageZipError(f"Formato não aceito em {value!r}; use PNG, JPG, JPEG ou WebP.")
    return name.casefold()


def _metadata_member(raw_name: str) -> bool:
    parts = [part for part in raw_name.replace("\\", "/").split("/") if part]
    if not parts:
        return True
    return parts[-1].casefold() in IGNORED_BASENAMES or parts[0].casefold() in IGNORED_PREFIXES


def _normalized_member_parts(info: zipfile.ZipInfo) -> tuple[str, ...]:
    raw_name = info.filename.replace("\\", "/")
    if "\x00" in raw_name or raw_name.startswith("/") or re.match(r"^[A-Za-z]:", raw_name):
        raise ImageZipError(f"Caminho absoluto ou inválido no ZIP: {info.filename!r}")
    parts = tuple(part for part in PurePosixPath(raw_name).parts if part)
    if not parts or any(part in {".", ".."} for part in parts):
        raise ImageZipError(f"Caminho inseguro no ZIP: {info.filename!r}")
    return parts


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    return stat.S_ISLNK(mode)


def _validated_image_data(data: bytes, limits: ZipLimits, basename: str) -> ArchiveImage:
    if len(data) > limits.max_image_bytes:
        raise ImageZipError(f"A imagem {basename} excede o limite configurado.")
    try:
        with Image.open(BytesIO(data)) as image:
            image_format = (image.format or "").upper()
            image.verify()
        # Pillow requires verify() immediately after opening. Reopen before
        # reading EXIF orientation for the camera coordinate system.
        with Image.open(BytesIO(data)) as image:
            # The camera contract measures focus after EXIF orientation.
            width, height = ImageOps.exif_transpose(image).size
            if width <= 0 or height <= 0 or width * height > limits.max_image_pixels:
                raise ImageZipError(f"Resolução incompatível em {basename}: {width}x{height}.")
    except ImageZipError:
        raise
    except (UnidentifiedImageError, OSError, RuntimeError, ValueError) as exc:
        raise ImageZipError(f"Arquivo de imagem inválido: {basename} ({exc})") from exc
    return ArchiveImage(basename, basename, data, width, height, image_format)


def validate_image_upload(
    filename: str,
    data: bytes | bytearray | memoryview,
    *,
    limits: ZipLimits | None = None,
) -> ArchiveImage:
    """Validate a single replacement image with the same limits as a ZIP member."""
    normalize_basename(filename)
    raw = bytes(data)
    active_limits = limits or ZipLimits.from_environment()
    return _validated_image_data(raw, active_limits, filename)


def _read_image(info: zipfile.ZipInfo, archive: zipfile.ZipFile, limits: ZipLimits, basename: str) -> ArchiveImage:
    if info.file_size > limits.max_image_bytes:
        raise ImageZipError(f"A imagem {basename} excede o limite configurado.")
    try:
        data = archive.read(info)
    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise ImageZipError(f"Não foi possível ler a imagem {basename}: {exc}") from exc
    validated = _validated_image_data(data, limits, basename)
    return ArchiveImage(
        basename,
        info.filename,
        validated.data,
        validated.width,
        validated.height,
        validated.format,
    )


def _open_source(source: bytes | bytearray | memoryview | str | Path | BinaryIO) -> tuple[zipfile.ZipFile, object | None]:
    if isinstance(source, (str, Path)):
        return zipfile.ZipFile(source), None
    if isinstance(source, (bytes, bytearray, memoryview)):
        handle = BytesIO(bytes(source))
        return zipfile.ZipFile(handle), handle
    if hasattr(source, "read"):
        handle = BytesIO(source.read())
        return zipfile.ZipFile(handle), handle
    raise TypeError("O ZIP precisa ser bytes, caminho ou arquivo binário.")


def validate_image_zip(
    source: bytes | bytearray | memoryview | str | Path | BinaryIO,
    required_names: Iterable[str],
    *,
    limits: ZipLimits | None = None,
) -> ImageZipValidation:
    """Validate image members and resolve scenes by basename without extraction."""
    active_limits = limits or ZipLimits.from_environment()
    requested: dict[str, str] = {}
    issues: list[str] = []
    for name in required_names:
        try:
            key = normalize_basename(name)
        except ImageZipError as exc:
            issues.append(str(exc))
            continue
        if key in requested and requested[key] != name:
            issues.append(f"O projeto referencia o mesmo basename mais de uma vez: {requested[key]} / {name}.")
        requested[key] = name

    try:
        archive, handle = _open_source(source)
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise ImageZipError(f"ZIP inválido ou protegido: {exc}") from exc

    try:
        infos = archive.infolist()
        file_infos = [info for info in infos if not info.is_dir() and not _metadata_member(info.filename)]
        if len(file_infos) > active_limits.max_files:
            issues.append(f"O ZIP contém {len(file_infos)} arquivos; o limite é {active_limits.max_files}.")
        if sum(max(0, info.compress_size) for info in file_infos) > active_limits.max_compressed_bytes:
            issues.append("O tamanho comprimido do ZIP excede o limite configurado.")
        if sum(max(0, info.file_size) for info in file_infos) > active_limits.max_uncompressed_bytes:
            issues.append("O tamanho descompactado do ZIP excede o limite configurado.")

        candidates: list[_Candidate] = []
        prefixes: set[str] = set()
        has_root_file = False
        for info in infos:
            if _metadata_member(info.filename):
                continue
            try:
                parts = _normalized_member_parts(info)
            except ImageZipError as exc:
                issues.append(str(exc))
                continue
            if info.is_dir():
                if len(parts) > 1:
                    prefixes.add(parts[0].casefold())
                continue
            if info.flag_bits & 0x1:
                issues.append(f"Arquivo criptografado não aceito no ZIP: {info.filename}")
                continue
            if _is_symlink(info):
                issues.append(f"Link simbólico não aceito no ZIP: {info.filename}")
                continue
            if len(parts) == 1:
                has_root_file = True
            elif len(parts) == 2:
                prefixes.add(parts[0].casefold())
            else:
                issues.append(f"O ZIP aceita somente a raiz ou uma subpasta: {info.filename}")
                continue
            basename = parts[-1]
            if Path(basename).suffix.lower() not in ALLOWED_EXTENSIONS:
                issues.append(f"Arquivo inesperado no ZIP: {info.filename}; use somente imagens PNG/JPG/JPEG/WebP.")
                continue
            candidates.append(_Candidate(info, basename, basename.casefold()))

        if has_root_file and prefixes:
            issues.append("O ZIP deve conter imagens na raiz ou em uma única subpasta, sem misturar os dois formatos.")
        if len(prefixes) > 1:
            issues.append("O ZIP contém mais de uma subpasta de imagens; use uma única subpasta.")

        by_key: dict[str, list[_Candidate]] = {}
        for candidate in candidates:
            by_key.setdefault(candidate.key, []).append(candidate)
        for key, matches in by_key.items():
            if len(matches) > 1:
                names = ", ".join(match.info.filename for match in matches)
                issues.append(f"Basename duplicado no ZIP ({requested.get(key, matches[0].basename)}): {names}")
        missing = [name for key, name in requested.items() if key not in by_key]
        if missing:
            issues.append("Imagens referenciadas ausentes no ZIP: " + ", ".join(missing))
        if issues:
            raise ImageZipError(" ".join(issues))

        validated: dict[str, ArchiveImage] = {}
        found_by_key: dict[str, str] = {}
        found_names: list[str] = []
        for key, matches in by_key.items():
            image = _read_image(matches[0].info, archive, active_limits, matches[0].basename)
            found_by_key[key] = image.basename
            if key in requested:
                validated[key] = image
            found_names.append(image.basename)
        extras = [name for key, name in found_by_key.items() if key not in requested]
        warnings = ("Imagens extras ignoradas: " + ", ".join(sorted(extras)),) if extras else ()
        return ImageZipValidation(
            validated,
            tuple(sorted(found_names)),
            tuple(requested[key] for key in requested),
            warnings,
        )
    except zipfile.BadZipFile as exc:
        raise ImageZipError(f"ZIP inválido: {exc}") from exc
    finally:
        archive.close()
        if handle is not None:
            handle.close()
