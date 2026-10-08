from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import re
import shutil
from typing import Any, Mapping
from uuid import uuid4
import zipfile

from app.image_archive import ArchiveImage, ImageZipValidation, validate_image_upload, validate_image_zip
from app.schemas import VideoProject


WORKSPACE_VERSION = 1
_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9_.-]+$")


class WorkspaceError(RuntimeError):
    """Raised when a persisted editing workspace is invalid or unsafe."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _sha256_bytes(data: bytes) -> str:
    return sha256(data).hexdigest()


def file_sha256(path: str | Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fingerprint(value: Any) -> str:
    return _sha256_bytes(canonical_json(value).encode("utf-8"))


def _atomic_bytes(target: Path, data: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.partial")
    try:
        temporary.write_bytes(data)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_json(target: Path, value: Any) -> None:
    _atomic_bytes(target, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def _relative_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise WorkspaceError("Um artefato tentou sair do workspace local.") from exc


def _safe_component(value: str, label: str) -> str:
    if not isinstance(value, str) or not _SAFE_COMPONENT.fullmatch(value):
        raise WorkspaceError(f"{label} inválido para o workspace.")
    return value


def _project_image_names(project: VideoProject) -> list[str]:
    return [shot.image_path for scene in project.scenes for shot in scene.visual_shots()]


@dataclass(frozen=True)
class WorkspaceSummary:
    workspace_id: str
    title: str
    updated_at: str
    root: Path


class ProjectWorkspace:
    """Persistent, hash-verified local state for selective Short reprocessing."""

    def __init__(self, root: str | Path, manifest: dict[str, Any]):
        self.root = Path(root).resolve()
        self.manifest = manifest

    @property
    def workspace_id(self) -> str:
        return str(self.manifest["id"])

    @classmethod
    def projects_root(cls, output_root: str | Path | None = None) -> Path:
        base = Path(output_root or os.getenv("OUTPUT_DIR", "/workspace/output"))
        return base / "projects"

    @classmethod
    def create(cls, title: str, *, output_root: str | Path | None = None) -> "ProjectWorkspace":
        root = cls.projects_root(output_root) / uuid4().hex
        root.mkdir(parents=True, exist_ok=False)
        manifest = {
            "version": WORKSPACE_VERSION,
            "id": root.name,
            "title": str(title).strip() or "Projeto sem título",
            "created_at": _now(),
            "updated_at": _now(),
            "project": None,
            "execution_settings": {},
            "images": {},
            "artifacts": {},
            "active_realizations": {},
            "voice_reference": None,
        }
        workspace = cls(root, manifest)
        workspace._save_manifest()
        return workspace

    @classmethod
    def open(cls, root: str | Path) -> "ProjectWorkspace":
        target = Path(root).resolve()
        manifest_path = target / "manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise WorkspaceError("Não foi possível abrir o manifesto do projeto salvo.") from exc
        if not isinstance(manifest, dict) or manifest.get("version") != WORKSPACE_VERSION:
            raise WorkspaceError("O projeto salvo usa um manifesto incompatível.")
        if manifest.get("id") != target.name or not _SAFE_COMPONENT.fullmatch(target.name):
            raise WorkspaceError("O identificador do projeto salvo é inválido.")
        return cls(target, manifest)

    @classmethod
    def list(cls, *, output_root: str | Path | None = None) -> tuple[WorkspaceSummary, ...]:
        root = cls.projects_root(output_root)
        if not root.is_dir():
            return ()
        results: list[WorkspaceSummary] = []
        for candidate in root.iterdir():
            if not candidate.is_dir():
                continue
            try:
                workspace = cls.open(candidate)
            except WorkspaceError:
                continue
            results.append(
                WorkspaceSummary(
                    workspace.workspace_id,
                    str(workspace.manifest.get("title", "Projeto sem título")),
                    str(workspace.manifest.get("updated_at", "")),
                    workspace.root,
                )
            )
        return tuple(sorted(results, key=lambda item: item.updated_at, reverse=True))

    def _save_manifest(self) -> None:
        self.manifest["updated_at"] = _now()
        _atomic_json(self.root / "manifest.json", self.manifest)

    def _resolve_relative(self, relative: str) -> Path:
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
            raise WorkspaceError("Caminho de artefato inválido no manifesto.")
        target = (self.root / relative).resolve()
        _relative_path(self.root, target)
        return target

    @staticmethod
    def _record(path: Path, root: Path) -> dict[str, Any]:
        return {
            "path": _relative_path(root, path),
            "sha256": file_sha256(path),
            "bytes": path.stat().st_size,
        }

    def _valid_record(self, record: Any) -> Path | None:
        if not isinstance(record, dict):
            return None
        try:
            target = self._resolve_relative(str(record["path"]))
            expected_hash = str(record["sha256"])
            expected_size = int(record["bytes"])
        except (KeyError, TypeError, ValueError, WorkspaceError):
            return None
        if not target.is_file() or target.stat().st_size != expected_size:
            return None
        return target if file_sha256(target) == expected_hash else None

    def save_project(self, project: VideoProject) -> None:
        target = self.root / "effective_project.json"
        _atomic_bytes(target, (project.to_json() + "\n").encode("utf-8"))
        self.manifest["title"] = project.title
        self.manifest["project"] = self._record(target, self.root)
        self._save_manifest()

    def load_project(self) -> VideoProject:
        target = self._valid_record(self.manifest.get("project"))
        if target is None:
            raise WorkspaceError("O roteiro efetivo salvo está ausente ou corrompido.")
        try:
            return VideoProject.from_json_file(target)
        except Exception as exc:
            raise WorkspaceError("O roteiro efetivo salvo não é válido no contrato atual.") from exc

    def save_execution_settings(self, settings: Mapping[str, Any]) -> None:
        # This manifest intentionally contains only serializable operational
        # values; voice-reference files are addressed separately by hash.
        try:
            normalized = json.loads(canonical_json(dict(settings)))
        except (TypeError, ValueError) as exc:
            raise WorkspaceError("As configurações efetivas não são serializáveis.") from exc
        self.manifest["execution_settings"] = normalized
        self._save_manifest()

    def execution_settings(self) -> dict[str, Any]:
        value = self.manifest.get("execution_settings", {})
        return dict(value) if isinstance(value, dict) else {}

    def import_image_zip(self, source: bytes | bytearray | memoryview | str | Path, project: VideoProject) -> ImageZipValidation:
        validation = validate_image_zip(source, _project_image_names(project))
        images = self.manifest.setdefault("images", {})
        for key, image in validation.images.items():
            self._store_image(image, preferred_name=image.basename)
            # Preserve a lookup by case-folded basename without trusting ZIP paths.
            images[key] = images[image.basename.casefold()]
        self._save_manifest()
        return validation

    def _store_image(self, image: ArchiveImage, *, preferred_name: str) -> str:
        suffix = Path(preferred_name).suffix.lower()
        digest = _sha256_bytes(image.data)
        target = self.root / "assets" / f"{digest}{suffix}"
        if not target.is_file() or file_sha256(target) != digest:
            _atomic_bytes(target, image.data)
        record = self._record(target, self.root)
        record.update({"name": preferred_name, "width": image.width, "height": image.height, "format": image.format})
        self.manifest.setdefault("images", {})[preferred_name.casefold()] = record
        return preferred_name

    def store_uploaded_image(self, filename: str, data: bytes | bytearray | memoryview) -> str:
        image = validate_image_upload(filename, data)
        preferred = image.basename
        existing = self.manifest.setdefault("images", {}).get(preferred.casefold())
        if isinstance(existing, dict) and existing.get("sha256") != _sha256_bytes(image.data):
            preferred = f"{Path(preferred).stem}_{_sha256_bytes(image.data)[:10]}{Path(preferred).suffix.lower()}"
            image = ArchiveImage(preferred, preferred, image.data, image.width, image.height, image.format)
        self._store_image(image, preferred_name=preferred)
        self._save_manifest()
        return preferred

    def image_names(self) -> tuple[str, ...]:
        names = [str(record.get("name", "")) for record in self.manifest.get("images", {}).values() if isinstance(record, dict)]
        return tuple(sorted({name for name in names if name}))

    def image_bytes(self, image_name: str) -> bytes:
        record = self.manifest.get("images", {}).get(image_name.casefold())
        target = self._valid_record(record)
        if target is None:
            raise WorkspaceError(f"A imagem salva {image_name!r} está ausente ou corrompida.")
        return target.read_bytes()

    def image_path(self, image_name: str) -> Path:
        record = self.manifest.get("images", {}).get(image_name.casefold())
        target = self._valid_record(record)
        if target is None:
            raise WorkspaceError(f"A imagem salva {image_name!r} está ausente ou corrompida.")
        return target

    def build_image_zip(self, project: VideoProject) -> bytes:
        data = BytesIO()
        names = _project_image_names(project)
        unique: dict[str, str] = {}
        for name in names:
            unique.setdefault(name.casefold(), name)
        with zipfile.ZipFile(data, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name in unique.values():
                archive.writestr(name, self.image_bytes(name))
        return data.getvalue()

    def get_artifact(self, kind: str, key: str) -> Path | None:
        _safe_component(kind, "Tipo de artefato")
        _safe_component(key, "Chave de artefato")
        record = self.manifest.get("artifacts", {}).get(kind, {}).get(key)
        target = self._valid_record(record)
        if target is not None:
            return target
        if record is not None:
            self.manifest["artifacts"][kind].pop(key, None)
            self._save_manifest()
        return None

    def put_artifact(self, kind: str, key: str, source: bytes | bytearray | memoryview | str | Path, *, suffix: str) -> Path:
        _safe_component(kind, "Tipo de artefato")
        _safe_component(key, "Chave de artefato")
        if not suffix.startswith(".") or not _SAFE_COMPONENT.fullmatch(suffix[1:]):
            raise WorkspaceError("Extensão de artefato inválida.")
        target = self.root / "cache" / kind / f"{key}{suffix}"
        if isinstance(source, (str, Path)):
            source_path = Path(source)
            if not source_path.is_file():
                raise WorkspaceError("O arquivo de artefato não está disponível.")
            temporary = target.with_name(f".{target.name}.{uuid4().hex}.partial")
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copyfile(source_path, temporary)
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
        else:
            _atomic_bytes(target, bytes(source))
        self.manifest.setdefault("artifacts", {}).setdefault(kind, {})[key] = self._record(target, self.root)
        self._save_manifest()
        return target

    def register_artifact(self, kind: str, key: str, path: str | Path) -> Path:
        """Register a completed file already written inside this workspace."""
        _safe_component(kind, "Tipo de artefato")
        _safe_component(key, "Chave de artefato")
        target = Path(path).resolve()
        _relative_path(self.root, target)
        if not target.is_file() or target.stat().st_size <= 0:
            raise WorkspaceError("O artefato concluído não está disponível para registro.")
        self.manifest.setdefault("artifacts", {}).setdefault(kind, {})[key] = self._record(target, self.root)
        self._save_manifest()
        return target

    def new_realization(self, scene_id: str) -> str:
        _safe_component(scene_id, "Cena")
        token = uuid4().hex
        self.manifest.setdefault("active_realizations", {})[scene_id] = token
        self._save_manifest()
        return token

    def active_realization(self, scene_id: str) -> str:
        _safe_component(scene_id, "Cena")
        value = self.manifest.setdefault("active_realizations", {}).get(scene_id)
        if not isinstance(value, str) or not _SAFE_COMPONENT.fullmatch(value):
            value = "default"
            self.manifest["active_realizations"][scene_id] = value
            self._save_manifest()
        return value

    def store_voice_reference(self, filename: str, data: bytes | bytearray | memoryview) -> tuple[Path, str]:
        raw = bytes(data)
        digest = _sha256_bytes(raw)
        suffix = Path(filename).suffix.lower() or ".wav"
        if suffix not in {".wav", ".mp3", ".flac", ".ogg"}:
            raise WorkspaceError("Formato de áudio de referência inválido.")
        target = self.root / "private" / f"voice_reference_{digest}{suffix}"
        if not target.is_file() or file_sha256(target) != digest:
            _atomic_bytes(target, raw)
        # Store only a hash and user-visible basename; never a host path.
        self.manifest["voice_reference"] = {"sha256": digest, "name": Path(filename).name, "suffix": suffix}
        self._save_manifest()
        return target, digest
