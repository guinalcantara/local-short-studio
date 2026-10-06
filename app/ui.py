from __future__ import annotations

import os
from pathlib import Path
import time

import streamlit as st
import torch

from app.captions import DEFAULT_CAPTION_FONT_SIZE, DEFAULT_CAPTION_HEIGHT_PERCENT
from app.image_archive import ImageZipError, ImageZipValidation, validate_image_zip
from app.music_catalog import MusicCatalog, MusicCatalogError, load_music_catalog
from app.pipeline import ShortPipeline, project_image_paths
from app.schemas import VideoProject, example_project
from app.voices import KOKORO_VOICES, TTS_ENGINES, normalize_voice, tts_engine_label, voice_label
from app.youtube import (
    YouTubeAlreadyPublishedError,
    YouTubeError,
    is_oauth_configured,
    list_youtube_accounts,
    load_youtube_publication,
    publish_to_youtube,
    remove_youtube_account,
    start_youtube_authorization,
    youtube_authorization_status,
)


VIDEO_PREVIEW_WIDTH = 360


def render_youtube_publication(video_path: Path, project: VideoProject) -> None:
    st.subheader("Publicar no YouTube")
    st.caption("A renderização permanece local. O upload só acontece após a confirmação abaixo.")
    if project.youtube is None:
        st.warning("Este projeto não possui o bloco youtube. Adicione os metadados antes de publicar.")
        return

    try:
        accounts = list_youtube_accounts()
    except YouTubeError as exc:
        st.error(f"Não foi possível carregar as contas do YouTube: {exc}")
        accounts = ()
    accounts_by_id = {account.id: account for account in accounts}
    account_options = [""] + [account.id for account in accounts]
    selected_key = "youtube_selected_account_id"
    if st.session_state.get(selected_key) not in account_options:
        st.session_state[selected_key] = ""
    selected_account_id = st.selectbox(
        "Conta para publicar",
        options=account_options,
        index=0,
        key=selected_key,
        format_func=lambda account_id: (
            "Selecione uma conta para publicar"
            if not account_id
            else accounts_by_id[account_id].display_name
        ),
        help="Nenhuma conta é selecionada automaticamente. Escolha o canal que receberá este MP4.",
    )
    selected_account = accounts_by_id.get(selected_account_id)

    with st.expander("Conectar ou remover contas do YouTube", expanded=not accounts):
        if not is_oauth_configured():
            st.info(
                "Para conectar uma conta, coloque o JSON do cliente OAuth em "
                "`input/youtube/client_secret.json` e reconstrua/inicie o app."
            )
        else:
            label = st.text_input(
                "Apelido local da conta (opcional)",
                placeholder="Ex.: Canal de ciência",
                key="youtube_new_account_label",
                help="Este apelido aparece apenas neste computador; o título do canal vem da conta autorizada.",
            )
            if st.button("Conectar nova conta", key="youtube_connect_account"):
                try:
                    authorization = start_youtube_authorization(label)
                    st.session_state["youtube_authorization_state"] = authorization.state
                    st.rerun()
                except YouTubeError as exc:
                    st.error(f"Não foi possível iniciar a conexão: {exc}")

        authorization_state = st.session_state.get("youtube_authorization_state")
        if authorization_state:
            authorization = youtube_authorization_status(authorization_state)
            if authorization is None:
                st.session_state.pop("youtube_authorization_state", None)
                st.warning("A solicitação de conexão expirou. Inicie uma nova conexão.")
            elif authorization.status == "pending":
                st.info("Conclua o login no navegador e depois atualize o estado desta página.")
                st.link_button("Abrir autorização do Google", authorization.authorization_url)
                if st.button("Atualizar após concluir o login", key="youtube_refresh_authorization"):
                    st.rerun()
            elif authorization.status == "complete" and authorization.account is not None:
                st.session_state.pop("youtube_authorization_state", None)
                st.success(f"Conta conectada: {authorization.account.display_name}")
                st.rerun()
            else:
                st.session_state.pop("youtube_authorization_state", None)
                st.error(authorization.error or "A conexão com o YouTube não foi concluída.")

        if selected_account is not None:
            if st.button("Remover conexão local desta conta", key="youtube_remove_account"):
                try:
                    remove_youtube_account(selected_account.id)
                    st.session_state[selected_key] = ""
                    st.success("A conexão local foi removida. Para revogar o acesso no Google, use a página de conexões da conta.")
                    st.rerun()
                except YouTubeError as exc:
                    st.error(f"Não foi possível remover a conexão: {exc}")

    try:
        previous_publication = load_youtube_publication(video_path)
    except YouTubeError as exc:
        st.error(f"Não foi possível ler o registro de publicação: {exc}")
        previous_publication = None
    if previous_publication is not None:
        st.success("Este MP4 já foi enviado ao YouTube.")
        st.link_button("Abrir vídeo publicado", previous_publication.video_url)
        return

    with st.expander("Revisar metadados que serão enviados", expanded=False):
        st.write(f"**Título:** {project.title}")
        st.write(f"**Privacidade:** {project.youtube.status.privacy_status}")
        st.write(f"**Categoria:** {project.youtube.category_id}")
        st.write(f"**Descrição:** {project.youtube.description or '(vazia)'}")
        st.write("**Tags:** " + (", ".join(project.youtube.tags) or "(nenhuma)"))
        st.write(
            "**Mídia sintética declarada:** "
            + ("sim" if project.youtube.status.contains_synthetic_media else "não")
        )
        if project.youtube.captions.enabled:
            st.info("O envio de legendas VTT/SRT pela API será adicionado em uma etapa posterior; este primeiro upload contém somente o MP4.")

    if selected_account is not None:
        st.info(f"Destino selecionado: **{selected_account.channel_title}**.")
    confirmation = st.checkbox(
        "Confirmo o canal, os metadados, os direitos de publicação e as declarações acima.",
        value=False,
        key=f"youtube_publish_confirmation_{video_path.parent.name}",
    )
    can_publish = selected_account is not None and confirmation
    if st.button(
        "Publicar MP4 no YouTube",
        type="primary",
        disabled=not can_publish,
        key=f"youtube_publish_{video_path.parent.name}",
        use_container_width=True,
    ):
        upload_progress = st.progress(0.0, text="Preparando publicação no YouTube…")

        def update_upload_progress(message: str, fraction: float | None = None) -> None:
            if fraction is None:
                upload_progress.progress(0.0, text=message)
            else:
                upload_progress.progress(min(1.0, max(0.0, fraction)), text=message)

        try:
            with st.spinner("Enviando o MP4 para o YouTube…"):
                publication = publish_to_youtube(
                    project,
                    video_path,
                    selected_account.id,
                    progress=update_upload_progress,
                )
            upload_progress.progress(1.0, text="Upload concluído")
            st.success("Upload concluído. O YouTube pode continuar processando o vídeo antes de disponibilizá-lo.")
            st.link_button("Abrir vídeo no YouTube", publication.video_url, type="primary")
        except YouTubeAlreadyPublishedError as exc:
            st.info(str(exc))
        except YouTubeError as exc:
            st.error(f"A publicação não foi concluída: {exc}")


st.set_page_config(page_title="Local Short Studio", page_icon="🎬", layout="wide")
st.title("Local Short Studio")
st.write("Transforme um roteiro e um ZIP de imagens em narração e um Short vertical local.")
st.caption("As imagens são preparadas previamente e enviadas com o roteiro; Kokoro usa CUDA para a voz e FFmpeg monta o MP4.")

with st.container(border=True):
    cuda_ok = torch.cuda.is_available()
    col1, col2 = st.columns(2)
    col1.metric("CUDA para Kokoro", "Disponível" if cuda_ok else "Não detectada")
    if cuda_ok:
        props = torch.cuda.get_device_properties(0)
        col2.metric("GPU detectada", f"{props.name} · {props.total_memory / (1024**3):.1f} GB")
    else:
        col2.metric("GPU detectada", "Verifique Docker Desktop + WSL 2")

sample_project = example_project()
sample_text = sample_project.to_json()
uploaded = st.file_uploader("1. Importe o projeto de cenas (.json)", type=["json"])
project_uploaded = uploaded is not None
if uploaded:
    try:
        project_text = uploaded.getvalue().decode("utf-8")
    except UnicodeDecodeError:
        st.error("O JSON precisa estar codificado em UTF-8.")
        project_text = ""
else:
    project_text = sample_text
    st.info("Envie o modelo JSON para habilitar a geração.")

st.download_button(
    "Baixar modelo de projeto",
    data=sample_text,
    file_name="modelo_projeto_short.json",
    mime="application/json",
)

with st.expander("Revisar roteiro e metadados", expanded=False):
    project_text = st.text_area(
        "JSON do projeto",
        value=project_text,
        height=430,
        help=(
            "Cada cena precisa de narration e image_path. O campo opcional shots aceita de 2 a 4 "
            "planos com imagens do ZIP; transition_to_next escolhe a passagem para a cena seguinte."
        ),
    )

parsed: VideoProject | None = None
try:
    if project_text.strip():
        parsed = VideoProject.from_json_text(project_text)
except Exception as exc:
    st.error(f"Projeto inválido: {exc}")

if parsed is not None:
    parsed_plan_count = len(project_image_paths(parsed))
    st.caption(f"Projeto válido: {len(parsed.scenes)} cenas e {parsed_plan_count} planos visuais.")
    transition_summaries = []
    transition_labels = {
        "cut": "corte seco",
        "crossfade": "dissolvência",
        "fade_black": "passagem pelo preto",
    }
    for scene in parsed.scenes[:-1]:
        transition = scene.transition_to_next
        if transition is None:
            transition_summaries.append(f"{scene.id}: dissolvência padrão")
            continue
        duration = (
            f" ({transition.duration_seconds:.2f}s)"
            if transition.duration_seconds is not None
            else " (duração padrão)" if transition.type != "cut" else ""
        )
        transition_summaries.append(
            f"{scene.id}: {transition_labels[transition.type]}{duration}"
        )
    if transition_summaries:
        st.caption("Transições entre cenas: " + " · ".join(transition_summaries))

input_root = Path(os.getenv("INPUT_DIR", "/workspace/input"))
music_catalog: MusicCatalog | None = None
music_catalog_error: str | None = None
try:
    music_catalog = load_music_catalog(input_root)
except MusicCatalogError as exc:
    music_catalog_error = str(exc)

images_upload = st.file_uploader(
    "2. Importe as imagens das cenas (.zip)",
    type=["zip"],
    help="O ZIP pode conter imagens na raiz ou em uma única subpasta. Use PNG, JPG, JPEG ou WebP.",
)

engine_codes = [code for _, code in TTS_ENGINES]
tts_engine = st.selectbox(
    "Mecanismo de narração",
    options=engine_codes,
    format_func=tts_engine_label,
    help="Escolha o mecanismo usado nesta geração. A escolha não altera o JSON do projeto.",
)

left, right = st.columns(2)
captions_enabled = left.checkbox(
    "Adicionar legendas modernas",
    value=True,
    help=(
        "Usa Montserrat ExtraBold em maiúsculas, blocos de até três palavras, entrada em pop e destaque progressivo. "
        "Desmarcado: não queima texto no vídeo."
    ),
)
image_effects_enabled = st.checkbox(
    "Aplicar movimentos suaves nas imagens",
    value=True,
    help="Desmarque para testar a narração e as transições sem aplicar zoom ou panorâmica. As transições entre cenas continuam ativas.",
)
caption_size_col, caption_height_col = st.columns(2)
caption_font_size = caption_size_col.slider(
    "Tamanho da fonte da legenda",
    min_value=36,
    max_value=120,
    value=DEFAULT_CAPTION_FONT_SIZE,
    step=2,
    disabled=not captions_enabled,
    help="Tamanho da fonte no vídeo vertical de 1080 × 1920 pixels.",
)
caption_height_percent = caption_height_col.slider(
    "Altura da legenda na tela",
    min_value=15,
    max_value=75,
    value=DEFAULT_CAPTION_HEIGHT_PERCENT,
    step=1,
    format="%d%%",
    disabled=not captions_enabled,
    help="0% corresponde à base, 50% ao centro e valores maiores sobem a legenda.",
)
voice_reference_upload = None
if tts_engine == "kokoro":
    voice_codes = [code for _, code in KOKORO_VOICES]
    selected_voice = normalize_voice(parsed.voice if parsed else None)
    voice = right.selectbox(
        "Voz da narração",
        options=voice_codes,
        index=voice_codes.index(selected_voice),
        format_func=voice_label,
        help="Todas as falas usam a voz escolhida em português brasileiro.",
    )
    speech_speed = st.slider(
        "Velocidade da narração",
        min_value=0.75,
        max_value=1.25,
        value=float(parsed.speech_speed) if parsed else 1.0,
        step=0.05,
    )
    chatterbox_settings = None
else:
    voice = normalize_voice(parsed.voice if parsed else None)
    speech_speed = float(parsed.speech_speed) if parsed else 1.0
    st.info("Chatterbox usa o checkpoint dedicado pt-BR. Sem referência, usa a voz interna; com um áudio, tenta reproduzir a sua voz.")
    voice_reference_upload = st.file_uploader(
        "Áudio de referência da sua voz (opcional)",
        type=["wav", "mp3", "flac", "ogg"],
        help="Use 5–10 segundos de voz limpa, em português brasileiro, sem música, eco ou outras pessoas.",
    )
    cb_left, cb_middle, cb_right = st.columns(3)
    chatterbox_exaggeration = cb_left.slider("Expressividade", 0.25, 1.0, 0.5, 0.05)
    chatterbox_cfg = cb_middle.slider("Controle de ritmo", 0.2, 0.8, 0.5, 0.05)
    chatterbox_temperature = cb_right.slider("Variação", 0.3, 1.2, 0.8, 0.05)
    chatterbox_settings = {
        "exaggeration": chatterbox_exaggeration,
        "cfg_weight": chatterbox_cfg,
        "temperature": chatterbox_temperature,
    }

st.subheader("Trilha sonora")
project_soundtrack_valid = True
json_track = None
if parsed is not None and parsed.soundtrack is not None:
    if music_catalog is None:
        st.error(music_catalog_error or "O catálogo local não pôde ser carregado.")
        project_soundtrack_valid = False
    else:
        try:
            json_track = music_catalog.get(parsed.soundtrack.track_id, verify_sha256=True)
            if parsed.soundtrack.volume_percent not in {0, json_track.recommended_volume_percent}:
                raise MusicCatalogError(
                    f"O JSON pede {parsed.soundtrack.volume_percent}%, mas deve usar 0% para silêncio "
                    f"explícito ou os {json_track.recommended_volume_percent}% recomendados para {json_track.id}."
                )
        except MusicCatalogError as exc:
            st.error(f"Trilha do projeto inválida: {exc}")
            project_soundtrack_valid = False

music_source_options = ["none", "upload"]
if music_catalog is not None and music_catalog.editorial_tracks():
    music_source_options.insert(1, "catalog")
if parsed is not None and parsed.music_path:
    music_source_options.insert(0, "legacy")
if parsed is not None and parsed.soundtrack is not None:
    music_source_options.insert(0, "json")

music_source_labels = {
    "json": "Aceitar a faixa definida no JSON",
    "catalog": "Escolher outra faixa do catálogo local",
    "legacy": "Usar music_path legado do JSON",
    "upload": "Enviar um arquivo manualmente",
    "none": "Sem música nesta geração",
}
music_source = st.selectbox(
    "Música efetiva nesta geração",
    options=music_source_options,
    format_func=lambda value: music_source_labels[value],
    help=(
        "Precedência aplicada: upload selecionado, faixa escolhida aqui, faixa do JSON, "
        "music_path legado e, por fim, sem música. O project.json original não é reescrito."
    ),
)

selected_catalog_track = json_track if music_source == "json" else None
selected_catalog_track_id: str | None = None
if music_source == "catalog" and music_catalog is not None:
    editorial_tracks = music_catalog.editorial_tracks()
    track_ids = [track.id for track in editorial_tracks]
    preferred_id = json_track.id if json_track and json_track.id in track_ids else track_ids[0]
    selected_catalog_track_id = st.selectbox(
        "Faixa do catálogo",
        options=track_ids,
        index=track_ids.index(preferred_id),
        format_func=lambda track_id: next(
            f"{track.title} · {track.category} · {track.recommended_volume_percent}%"
            for track in editorial_tracks if track.id == track_id
        ),
    )
    selected_catalog_track = music_catalog.get(selected_catalog_track_id)

if selected_catalog_track is not None:
    artist = selected_catalog_track.artist_candidate or "autor não identificado"
    st.info(
        f"**{selected_catalog_track.title}** — {artist}  \n"
        f"Categoria: `{selected_catalog_track.category}` · "
        f"Uso estimado: {selected_catalog_track.best_for_estimate or 'não informado'} · "
        f"Duração: {selected_catalog_track.duration_seconds:.1f}s · "
        f"Volume recomendado: {selected_catalog_track.recommended_volume_percent}% · "
        f"Licença: `{selected_catalog_track.license_status}`"
    )
    if selected_catalog_track.license_status == "unverified":
        st.warning(
            "Licença, origem e atribuição não foram comprovadas. A renderização local serve para revisão; "
            "confirme os direitos antes de publicar."
        )
    else:
        st.caption(f"Estado de licença informado no catálogo: {selected_catalog_track.license_status}")

music_upload = None
if music_source == "upload":
    music_upload = st.file_uploader(
        "Música de fundo manual (com direitos de uso)",
        type=["mp3", "wav", "m4a", "aac"],
    )

catalog_volume = selected_catalog_track is not None
recommended_volume = (
    selected_catalog_track.recommended_volume_percent if selected_catalog_track else 12
)
initial_music_volume = (
    parsed.soundtrack.volume_percent
    if music_source == "json" and parsed is not None and parsed.soundtrack is not None
    else recommended_volume
)
music_volume_percent = st.slider(
    "Volume da música",
    min_value=0,
    max_value=max(1, recommended_volume) if catalog_volume else 100,
    value=initial_music_volume,
    step=1,
    format="%d%%",
    disabled=(music_source == "none" or (music_source == "upload" and music_upload is None) or recommended_volume == 0),
    key=f"music_volume_{music_source}_{selected_catalog_track.id if selected_catalog_track else 'manual'}",
    help=(
        "Para uma faixa catalogada, o controle permite apenas manter ou reduzir o teto recomendado; "
        "o app ainda pode baixar o ganho depois de medir a voz. Upload e music_path mantêm o controle legado."
    ),
)

zip_validation: ImageZipValidation | None = None
if images_upload is None:
    st.info("Envie o ZIP de imagens para validar o mapeamento das cenas.")
elif parsed is not None:
    try:
        required_images = project_image_paths(parsed)
        zip_validation = validate_image_zip(images_upload.getvalue(), required_images)
        st.success(
            f"ZIP válido: {zip_validation.image_count} imagens encontradas para "
            f"{len(parsed.scenes)} cenas e {len(required_images)} planos."
        )
        st.caption("Arquivos encontrados: " + ", ".join(zip_validation.found_names))
        if any(scene.shots is not None for scene in parsed.scenes):
            st.info(
                "Este projeto usa múltiplos planos. O Whisper será executado para alinhar as trocas de imagem, "
                "mesmo se as legendas visuais estiverem desativadas."
            )
        for warning in zip_validation.warnings:
            st.warning(warning)
    except ImageZipError as exc:
        st.error(f"ZIP de imagens inválido: {exc}")

manual_music_ready = music_source != "upload" or music_upload is not None
can_generate = (
    project_uploaded
    and parsed is not None
    and images_upload is not None
    and zip_validation is not None
    and project_soundtrack_valid
    and manual_music_ready
)
if st.button("Gerar Short", type="primary", disabled=not can_generate, use_container_width=True):
    project = VideoProject.from_json_text(project_text)
    project.captions.enabled = captions_enabled
    if tts_engine == "kokoro":
        project.voice = voice
        project.speech_speed = speech_speed
    manual_music_path = None
    if music_source == "upload" and music_upload is not None:
        music_dir = input_root / "music"
        music_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(music_upload.name).suffix.lower() or ".mp3"
        manual_music_path = music_dir / f"background{suffix}"
        manual_music_path.write_bytes(music_upload.getvalue())

    progress_bar = st.progress(0.0, text="Preparando validação…")
    status_text = st.empty()
    progress_started = time.perf_counter()

    def update_progress(message: str, fraction: float | None = None):
        elapsed = time.perf_counter() - progress_started
        status_text.info(f"{message}  ·  decorrido: {elapsed:.0f}s")
        if fraction is not None:
            progress_bar.progress(min(1.0, max(0.0, fraction)), text=message)

    try:
        with st.spinner("Gerando o Short…"):
            output_video = ShortPipeline(
                progress=update_progress,
                tts_engine=tts_engine,
                chatterbox_settings=chatterbox_settings,
                image_effects_enabled=image_effects_enabled,
                music_volume=music_volume_percent / 100.0,
                disable_music=music_source == "none",
                manual_music_path=manual_music_path,
                catalog_track_id=selected_catalog_track_id if music_source == "catalog" else None,
                catalog_volume_percent=music_volume_percent if music_source in {"catalog", "json"} else None,
                caption_font_size=caption_font_size,
                caption_height_percent=caption_height_percent,
            ).run(
                project,
                images_upload.getvalue(),
                voice_reference=voice_reference_upload.getvalue() if voice_reference_upload else None,
                voice_reference_name=voice_reference_upload.name if voice_reference_upload else None,
            )
        status_text.success("Short finalizado.")
        progress_bar.progress(1.0, text="Pronto")
        st.session_state["youtube_output_video_path"] = str(output_video)
        st.session_state["youtube_output_project_json"] = project.to_json()
        st.video(str(output_video), width=VIDEO_PREVIEW_WIDTH)
        st.download_button(
            "Baixar MP4",
            data=output_video.read_bytes(),
            file_name=output_video.name,
            mime="video/mp4",
            type="primary",
        )
        project_dir = output_video.parent
        st.write(f"Arquivos salvos em: `{project_dir}`")
        if captions_enabled:
            srt_path = output_video.with_suffix(".srt")
            if srt_path.exists():
                st.download_button("Baixar legendas SRT", data=srt_path.read_bytes(), file_name=srt_path.name, mime="application/x-subrip")
    except Exception as exc:
        status_text.error("A geração parou. Veja a etapa indicada na mensagem abaixo.")
        st.exception(exc)

stored_video_path = st.session_state.get("youtube_output_video_path")
stored_project_json = st.session_state.get("youtube_output_project_json")
if stored_video_path and stored_project_json:
    stored_video = Path(stored_video_path)
    try:
        stored_project = VideoProject.from_json_text(stored_project_json)
    except Exception:
        st.session_state.pop("youtube_output_video_path", None)
        st.session_state.pop("youtube_output_project_json", None)
    else:
        if stored_video.is_file():
            st.divider()
            render_youtube_publication(stored_video, stored_project)
        else:
            st.warning("O MP4 gerado nesta sessão não está mais disponível para publicação.")
            st.session_state.pop("youtube_output_video_path", None)
            st.session_state.pop("youtube_output_project_json", None)

st.divider()
st.markdown("**Fluxo local:** modelo JSON + ZIP → validação → voz pt-BR local → alinhamento quando necessário → FFmpeg → MP4 9:16")
