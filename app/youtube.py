from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
from threading import RLock, Thread
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from app.schemas import VideoProject


YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
YOUTUBE_READONLY_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
YOUTUBE_CAPTIONS_SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl"
YOUTUBE_SCOPES = (YOUTUBE_UPLOAD_SCOPE, YOUTUBE_READONLY_SCOPE, YOUTUBE_CAPTIONS_SCOPE)
_ACCOUNT_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_ACCOUNT_STORE_VERSION = 1
_MAX_CAPTION_BYTES = 100 * 1024 * 1024
_PENDING_AUTHORIZATIONS: dict[str, "YouTubeAuthorization"] = {}
_AUTH_LOCK = RLock()
_CALLBACK_SERVER: ThreadingHTTPServer | None = None


class YouTubeError(RuntimeError):
    """Raised for an expected local YouTube integration failure."""


class YouTubeConfigurationError(YouTubeError):
    """Raised when local OAuth credentials are missing or unusable."""


class YouTubeAlreadyPublishedError(YouTubeError):
    """Raised to prevent a second upload of the same rendered file."""


@dataclass(frozen=True)
class YouTubeAccount:
    id: str
    label: str
    channel_id: str
    channel_title: str

    @property
    def display_name(self) -> str:
        return f"{self.label} — {self.channel_title}"


@dataclass
class YouTubeAuthorization:
    state: str
    authorization_url: str
    requested_label: str
    flow: InstalledAppFlow
    status: str = "pending"
    account: YouTubeAccount | None = None
    error: str | None = None


@dataclass(frozen=True)
class YouTubeCaptionPublication:
    caption_id: str
    language: str
    format: str
    caption_sha256: str
    uploaded_at: str


@dataclass(frozen=True)
class YouTubePublication:
    video_id: str
    video_url: str
    account_id: str
    channel_id: str
    published_at: str
    video_sha256: str
    caption: YouTubeCaptionPublication | None = None


def youtube_data_dir() -> Path:
    input_root = Path(os.getenv("INPUT_DIR", "/workspace/input"))
    return Path(os.getenv("YOUTUBE_DATA_DIR", str(input_root / "youtube")))


def oauth_client_secret_path() -> Path:
    return Path(
        os.getenv(
            "YOUTUBE_CLIENT_SECRET_PATH",
            str(youtube_data_dir() / "client_secret.json"),
        )
    )


def oauth_redirect_port() -> int:
    raw_value = os.getenv("YOUTUBE_OAUTH_PORT", "8765")
    try:
        port = int(raw_value)
    except ValueError as exc:
        raise YouTubeConfigurationError("YOUTUBE_OAUTH_PORT deve ser um número inteiro.") from exc
    if not 1024 <= port <= 65535:
        raise YouTubeConfigurationError("YOUTUBE_OAUTH_PORT deve estar entre 1024 e 65535.")
    return port


def is_oauth_configured() -> bool:
    return oauth_client_secret_path().is_file()


def _accounts_path() -> Path:
    return youtube_data_dir() / "accounts.json"


def _tokens_dir() -> Path:
    return youtube_data_dir() / "tokens"


def _safe_account_id(value: str) -> str:
    if not _ACCOUNT_ID_RE.fullmatch(value):
        raise YouTubeError("Identificador de conta do YouTube inválido.")
    return value


def _token_path(account_id: str) -> Path:
    return _tokens_dir() / f"{_safe_account_id(account_id)}.json"


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise YouTubeError(f"Não foi possível ler a configuração local do YouTube em {path.name}.") from exc


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _accounts_payload() -> dict[str, Any]:
    payload = _read_json(_accounts_path(), {"version": _ACCOUNT_STORE_VERSION, "accounts": []})
    if not isinstance(payload, dict) or payload.get("version") != _ACCOUNT_STORE_VERSION:
        raise YouTubeError("A lista local de contas do YouTube é inválida.")
    accounts = payload.get("accounts")
    if not isinstance(accounts, list):
        raise YouTubeError("A lista local de contas do YouTube é inválida.")
    return payload


def _parse_account(data: Any) -> YouTubeAccount:
    if not isinstance(data, dict):
        raise YouTubeError("Uma conta local do YouTube é inválida.")
    account = YouTubeAccount(
        id=_safe_account_id(str(data.get("id", ""))),
        label=str(data.get("label", "")).strip(),
        channel_id=str(data.get("channel_id", "")).strip(),
        channel_title=str(data.get("channel_title", "")).strip(),
    )
    if not account.label or not account.channel_id or not account.channel_title:
        raise YouTubeError("Uma conta local do YouTube está incompleta.")
    return account


def list_youtube_accounts() -> tuple[YouTubeAccount, ...]:
    payload = _accounts_payload()
    accounts = tuple(_parse_account(item) for item in payload["accounts"])
    if len({account.id for account in accounts}) != len(accounts):
        raise YouTubeError("A lista local contém contas do YouTube duplicadas.")
    return tuple(sorted(accounts, key=lambda account: account.display_name.casefold()))


def get_youtube_account(account_id: str) -> YouTubeAccount:
    safe_account_id = _safe_account_id(account_id)
    for account in list_youtube_accounts():
        if account.id == safe_account_id:
            return account
    raise YouTubeError("A conta do YouTube selecionada não está mais conectada.")


def remove_youtube_account(account_id: str) -> None:
    safe_account_id = _safe_account_id(account_id)
    with _AUTH_LOCK:
        payload = _accounts_payload()
        accounts = [_parse_account(item) for item in payload["accounts"]]
        if not any(account.id == safe_account_id for account in accounts):
            raise YouTubeError("A conta do YouTube selecionada não está mais conectada.")
        payload["accounts"] = [asdict(account) for account in accounts if account.id != safe_account_id]
        _write_json(_accounts_path(), payload)
        _token_path(safe_account_id).unlink(missing_ok=True)


def _save_account(account: YouTubeAccount, credentials: Credentials) -> None:
    with _AUTH_LOCK:
        payload = _accounts_payload()
        accounts = [_parse_account(item) for item in payload["accounts"]]
        replaced_ids = [existing.id for existing in accounts if existing.channel_id == account.channel_id]
        accounts = [existing for existing in accounts if existing.channel_id != account.channel_id]
        accounts.append(account)
        _write_json(
            _accounts_path(),
            {"version": _ACCOUNT_STORE_VERSION, "accounts": [asdict(item) for item in accounts]},
        )
        for replaced_id in replaced_ids:
            if replaced_id != account.id:
                _token_path(replaced_id).unlink(missing_ok=True)
        _token_path(account.id).parent.mkdir(parents=True, exist_ok=True)
        _token_path(account.id).write_text(credentials.to_json() + "\n", encoding="utf-8")


def _credentials_for_account(account: YouTubeAccount) -> Credentials:
    token_path = _token_path(account.id)
    if not token_path.is_file():
        raise YouTubeError(f"O token local da conta '{account.label}' não foi encontrado.")
    try:
        credentials = Credentials.from_authorized_user_file(str(token_path), YOUTUBE_SCOPES)
    except (OSError, ValueError) as exc:
        raise YouTubeError(f"O token local da conta '{account.label}' não pôde ser lido.") from exc
    if not credentials.has_scopes(YOUTUBE_SCOPES):
        raise YouTubeError(
            f"A conta '{account.label}' precisa ser conectada novamente para conceder também a permissão de legendas."
        )
    try:
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            token_path.write_text(credentials.to_json() + "\n", encoding="utf-8")
    except Exception as exc:
        raise YouTubeError(f"Não foi possível renovar a conexão da conta '{account.label}'.") from exc
    if not credentials.valid:
        raise YouTubeError(f"A conexão da conta '{account.label}' expirou. Conecte-a novamente.")
    return credentials


def _youtube_service(credentials: Credentials):
    return build("youtube", "v3", credentials=credentials, cache_discovery=False)


def _channel_from_credentials(credentials: Credentials) -> tuple[str, str]:
    try:
        response = _youtube_service(credentials).channels().list(part="id,snippet", mine=True).execute()
    except HttpError as exc:
        raise YouTubeError("Não foi possível identificar o canal da conta autorizada.") from exc
    items = response.get("items", [])
    if not items:
        raise YouTubeError("A conta autorizada não possui um canal do YouTube disponível.")
    channel = items[0]
    channel_id = str(channel.get("id", "")).strip()
    channel_title = str(channel.get("snippet", {}).get("title", "")).strip()
    if not channel_id or not channel_title:
        raise YouTubeError("A API não retornou a identificação do canal autorizado.")
    return channel_id, channel_title


def _callback_url() -> str:
    return f"http://localhost:{oauth_redirect_port()}/"


def _oauth_flow() -> InstalledAppFlow:
    client_secret = oauth_client_secret_path()
    if not client_secret.is_file():
        raise YouTubeConfigurationError(
            "Arquivo OAuth não encontrado. Coloque o JSON do cliente em "
            f"{client_secret} e tente novamente."
        )
    try:
        flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), scopes=YOUTUBE_SCOPES)
    except (OSError, ValueError) as exc:
        raise YouTubeConfigurationError("O arquivo de cliente OAuth do YouTube é inválido.") from exc
    flow.redirect_uri = _callback_url()
    return flow


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    server_version = "LocalShortStudioOAuth/1.0"

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        state = query.get("state", [""])[0]
        code = query.get("code", [""])[0]
        oauth_error = query.get("error", [""])[0]
        with _AUTH_LOCK:
            authorization = _PENDING_AUTHORIZATIONS.get(state)
        if authorization is None:
            self._respond(400, "A autorização não corresponde a uma solicitação ativa do Local Short Studio.")
            return
        if oauth_error:
            authorization.status = "error"
            authorization.error = f"O Google cancelou ou recusou a autorização: {oauth_error}."
            self._respond(400, "A autorização foi cancelada. Volte ao Local Short Studio.")
            self._shutdown_server()
            return
        if not code:
            authorization.status = "error"
            authorization.error = "O Google não devolveu o código de autorização."
            self._respond(400, "Não recebemos o código de autorização. Volte ao Local Short Studio.")
            self._shutdown_server()
            return
        try:
            authorization.flow.fetch_token(code=code)
            credentials = authorization.flow.credentials
            channel_id, channel_title = _channel_from_credentials(credentials)
            label = authorization.requested_label.strip() or channel_title
            account = YouTubeAccount(
                id=uuid4().hex,
                label=label,
                channel_id=channel_id,
                channel_title=channel_title,
            )
            _save_account(account, credentials)
            authorization.account = account
            authorization.status = "complete"
            self._respond(200, "Conta conectada com sucesso. Você já pode voltar ao Local Short Studio.")
        except Exception as exc:  # callback must return a friendly page instead of an HTTP traceback
            authorization.status = "error"
            authorization.error = str(exc) if isinstance(exc, YouTubeError) else "Não foi possível concluir a conexão com o YouTube."
            self._respond(500, "Não foi possível concluir a conexão. Volte ao Local Short Studio para ver o erro.")
        finally:
            self._shutdown_server()

    def log_message(self, format: str, *args: object) -> None:
        return

    def _respond(self, status: int, message: str) -> None:
        body = (
            "<!doctype html><html lang='pt-BR'><meta charset='utf-8'>"
            "<title>Local Short Studio</title><body><p>"
            f"{message}</p></body></html>"
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    @staticmethod
    def _shutdown_server() -> None:
        global _CALLBACK_SERVER
        with _AUTH_LOCK:
            server = _CALLBACK_SERVER
            _CALLBACK_SERVER = None
        if server is not None:
            def close_server() -> None:
                server.shutdown()
                server.server_close()

            Thread(target=close_server, daemon=True).start()


def start_youtube_authorization(label: str = "") -> YouTubeAuthorization:
    global _CALLBACK_SERVER
    with _AUTH_LOCK:
        if _CALLBACK_SERVER is not None:
            raise YouTubeError("Já existe uma autorização do YouTube aguardando conclusão.")
        flow = _oauth_flow()
        try:
            server = ThreadingHTTPServer(("0.0.0.0", oauth_redirect_port()), _OAuthCallbackHandler)
        except OSError as exc:
            raise YouTubeConfigurationError(
                "Não foi possível abrir a porta local de retorno do OAuth. "
                "Confira YOUTUBE_OAUTH_PORT e a porta exposta pelo Docker."
            ) from exc
        _CALLBACK_SERVER = server
        try:
            authorization_url, state = flow.authorization_url(
                access_type="offline",
                prompt="consent",
                include_granted_scopes="true",
            )
            authorization = YouTubeAuthorization(
                state=state,
                authorization_url=authorization_url,
                requested_label=label,
                flow=flow,
            )
            _PENDING_AUTHORIZATIONS[state] = authorization
            Thread(target=server.serve_forever, daemon=True).start()
            return authorization
        except Exception:
            _CALLBACK_SERVER = None
            server.server_close()
            raise


def youtube_authorization_status(state: str) -> YouTubeAuthorization | None:
    with _AUTH_LOCK:
        return _PENDING_AUTHORIZATIONS.get(state)


def pending_youtube_authorization() -> YouTubeAuthorization | None:
    """Return the active browser authorization, even after a Streamlit page refresh."""
    with _AUTH_LOCK:
        pending = [
            authorization
            for authorization in _PENDING_AUTHORIZATIONS.values()
            if authorization.status == "pending"
        ]
    return pending[-1] if pending else None


def cancel_youtube_authorization(state: str) -> None:
    """Cancel an unfinished local OAuth request and free its loopback callback port."""
    global _CALLBACK_SERVER
    with _AUTH_LOCK:
        authorization = _PENDING_AUTHORIZATIONS.get(state)
        if authorization is None or authorization.status != "pending":
            raise YouTubeError("Não há uma autorização do YouTube pendente para cancelar.")
        authorization.status = "cancelled"
        authorization.error = "A autorização foi cancelada neste computador."
        server = _CALLBACK_SERVER
        _CALLBACK_SERVER = None
    if server is not None:
        server.shutdown()
        server.server_close()


def youtube_video_resource(project: VideoProject) -> dict[str, Any]:
    if project.youtube is None:
        raise YouTubeError("O projeto não possui o bloco youtube necessário para publicação.")
    metadata = project.youtube
    return {
        "snippet": {
            "title": project.title,
            "description": metadata.description,
            "tags": metadata.tags,
            "categoryId": metadata.category_id,
            "defaultLanguage": metadata.default_language,
        },
        "status": {
            "privacyStatus": metadata.status.privacy_status,
            "license": metadata.status.license,
            "embeddable": metadata.status.embeddable,
            "publicStatsViewable": metadata.status.public_stats_viewable,
            "selfDeclaredMadeForKids": metadata.status.self_declared_made_for_kids,
            "containsSyntheticMedia": metadata.status.contains_synthetic_media,
        },
    }


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _video_sha256(video_path: Path) -> str:
    return _file_sha256(video_path)


def _srt_to_webvtt(source: Path, target: Path) -> None:
    try:
        content = source.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise YouTubeError("Não foi possível ler o arquivo SRT das legendas.") from exc
    normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        raise YouTubeError("O arquivo SRT das legendas está vazio.")

    converted_blocks: list[str] = []
    for block in re.split(r"\n{2,}", normalized):
        lines = block.split("\n")
        if lines and lines[0].strip().isdigit():
            lines = lines[1:]
        if not lines or "-->" not in lines[0]:
            raise YouTubeError("O arquivo SRT das legendas não possui timestamps válidos.")
        lines[0] = lines[0].replace(",", ".")
        converted_blocks.append("\n".join(lines))

    target.write_text("WEBVTT\n\n" + "\n\n".join(converted_blocks) + "\n", encoding="utf-8")


def _caption_file_for_publication(project: VideoProject, video_path: Path) -> tuple[Path, str] | None:
    if project.youtube is None or not project.youtube.captions.enabled:
        return None

    srt_path = video_path.with_suffix(".srt")
    if not srt_path.is_file():
        raise YouTubeError(
            "O projeto pede uma faixa de legendas, mas o SRT desta renderização não foi encontrado. "
            "Gere o Short novamente com as legendas ativadas."
        )
    try:
        source_size = srt_path.stat().st_size
    except OSError as exc:
        raise YouTubeError("Não foi possível acessar o arquivo SRT das legendas.") from exc
    if not 0 < source_size <= _MAX_CAPTION_BYTES:
        raise YouTubeError("O arquivo SRT das legendas está vazio ou excede o limite de 100 MB do YouTube.")

    caption_format = project.youtube.captions.format
    if caption_format == "srt":
        return srt_path, caption_format

    vtt_path = video_path.with_suffix(".vtt")
    _srt_to_webvtt(srt_path, vtt_path)
    try:
        vtt_size = vtt_path.stat().st_size
    except OSError as exc:
        raise YouTubeError("Não foi possível preparar o arquivo VTT das legendas.") from exc
    if not 0 < vtt_size <= _MAX_CAPTION_BYTES:
        raise YouTubeError("O arquivo VTT das legendas está vazio ou excede o limite de 100 MB do YouTube.")
    return vtt_path, caption_format


def publication_record_path(video_path: str | Path) -> Path:
    return Path(video_path).parent / "youtube_publication.json"


def load_youtube_publication(video_path: str | Path) -> YouTubePublication | None:
    record_path = publication_record_path(video_path)
    if not record_path.is_file():
        return None
    data = _read_json(record_path, None)
    if not isinstance(data, dict):
        raise YouTubeError("O registro local de publicação do YouTube é inválido.")
    try:
        caption_data = data.get("caption")
        if caption_data is None:
            caption = None
        elif not isinstance(caption_data, dict):
            raise ValueError("caption inválida")
        else:
            caption = YouTubeCaptionPublication(
                caption_id=str(caption_data["caption_id"]),
                language=str(caption_data["language"]),
                format=str(caption_data["format"]),
                caption_sha256=str(caption_data["caption_sha256"]),
                uploaded_at=str(caption_data["uploaded_at"]),
            )
        return YouTubePublication(
            video_id=str(data["video_id"]),
            video_url=str(data["video_url"]),
            account_id=_safe_account_id(str(data["account_id"])),
            channel_id=str(data["channel_id"]),
            published_at=str(data["published_at"]),
            video_sha256=str(data["video_sha256"]),
            caption=caption,
        )
    except (KeyError, ValueError) as exc:
        raise YouTubeError("O registro local de publicação do YouTube é inválido.") from exc


def _upload_caption(
    service: Any,
    project: VideoProject,
    video_id: str,
    caption_path: Path,
    caption_format: str,
    report_progress: Callable[[str, float | None], None],
) -> YouTubeCaptionPublication:
    if project.youtube is None:
        raise YouTubeError("O projeto não possui o bloco youtube necessário para publicação.")
    language = project.youtube.captions.language
    report_progress("Enviando faixa de legendas para o YouTube…", 0.96)
    request = service.captions().insert(
        part="snippet",
        body={
            "snippet": {
                "videoId": video_id,
                "language": language,
                "name": f"Legendas {caption_format.upper()} ({language})",
                "isDraft": False,
            }
        },
        media_body=MediaFileUpload(str(caption_path), mimetype="application/octet-stream"),
    )
    try:
        response = request.execute()
    except HttpError as exc:
        detail = getattr(exc, "reason", None) or "A API do YouTube recusou a faixa de legendas."
        raise YouTubeError(f"O MP4 foi enviado, mas a legenda não foi concluída: {detail}") from exc
    caption_id = str(response.get("id", "")).strip() if response else ""
    if not caption_id:
        raise YouTubeError("O MP4 foi enviado, mas o YouTube não retornou o ID da faixa de legendas.")
    return YouTubeCaptionPublication(
        caption_id=caption_id,
        language=language,
        format=caption_format,
        caption_sha256=_file_sha256(caption_path),
        uploaded_at=datetime.now(UTC).isoformat(),
    )


def publish_to_youtube(
    project: VideoProject,
    video_path: str | Path,
    account_id: str,
    progress: Callable[[str, float | None], None] | None = None,
) -> YouTubePublication:
    target = Path(video_path)
    if not target.is_file() or target.suffix.lower() != ".mp4":
        raise YouTubeError("O MP4 renderizado não está disponível para publicação.")
    report_progress = progress or (lambda message, fraction=None: None)
    caption_file = _caption_file_for_publication(project, target)
    video_digest = _video_sha256(target)
    existing = load_youtube_publication(target)
    account = get_youtube_account(account_id)
    report_progress("Renovando a autorização da conta do YouTube…", 0.02)
    credentials = _credentials_for_account(account)
    service = _youtube_service(credentials)
    if existing is not None and existing.video_sha256 == video_digest:
        if existing.account_id != account.id:
            raise YouTubeError("Este MP4 já está associado a outra conta do YouTube neste computador.")
        if caption_file is None:
            raise YouTubeAlreadyPublishedError(
                "Este MP4 já foi enviado ao YouTube. Consulte o link registrado ou gere um novo vídeo antes de publicar novamente."
            )
        caption_path, caption_format = caption_file
        caption_digest = _file_sha256(caption_path)
        if existing.caption is not None and existing.caption.caption_sha256 == caption_digest:
            raise YouTubeAlreadyPublishedError(
                "Este MP4 e esta faixa de legendas já foram enviados ao YouTube."
            )
        caption = _upload_caption(
            service,
            project,
            existing.video_id,
            caption_path,
            caption_format,
            report_progress,
        )
        publication = YouTubePublication(
            video_id=existing.video_id,
            video_url=existing.video_url,
            account_id=existing.account_id,
            channel_id=existing.channel_id,
            published_at=existing.published_at,
            video_sha256=existing.video_sha256,
            caption=caption,
        )
        _write_json(publication_record_path(target), asdict(publication))
        report_progress("Legenda enviada; o YouTube pode continuar processando o vídeo.", 1.0)
        return publication

    request = service.videos().insert(
        part="snippet,status",
        notifySubscribers=project.youtube.notify_subscribers if project.youtube else True,
        body=youtube_video_resource(project),
        media_body=MediaFileUpload(
            str(target),
            mimetype="video/mp4",
            resumable=True,
            chunksize=8 * 1024 * 1024,
        ),
    )
    response: dict[str, Any] | None = None
    try:
        while response is None:
            status, response = request.next_chunk()
            if status is not None:
                report_progress("Enviando MP4 para o YouTube…", 0.05 + 0.9 * float(status.progress()))
    except HttpError as exc:
        detail = getattr(exc, "reason", None) or "A API do YouTube recusou o upload."
        raise YouTubeError(f"Falha no upload para o YouTube: {detail}") from exc
    video_id = str(response.get("id", "")).strip() if response else ""
    if not video_id:
        raise YouTubeError("O YouTube não retornou o identificador do vídeo enviado.")
    publication = YouTubePublication(
        video_id=video_id,
        video_url=f"https://www.youtube.com/watch?v={video_id}",
        account_id=account.id,
        channel_id=account.channel_id,
        published_at=datetime.now(UTC).isoformat(),
        video_sha256=video_digest,
    )
    _write_json(publication_record_path(target), asdict(publication))
    if caption_file is not None:
        caption_path, caption_format = caption_file
        caption = _upload_caption(
            service,
            project,
            video_id,
            caption_path,
            caption_format,
            report_progress,
        )
        publication = YouTubePublication(
            video_id=publication.video_id,
            video_url=publication.video_url,
            account_id=publication.account_id,
            channel_id=publication.channel_id,
            published_at=publication.published_at,
            video_sha256=publication.video_sha256,
            caption=caption,
        )
        _write_json(publication_record_path(target), asdict(publication))
        report_progress("MP4 e legenda enviados; o YouTube pode continuar processando o vídeo.", 1.0)
    else:
        report_progress("Upload concluído; o YouTube pode continuar processando o vídeo.", 1.0)
    return publication
