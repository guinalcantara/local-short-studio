"""Interface Streamlit independente do pipeline de geração."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

from app.performance_analysis import METRICS, choose_comparable, deterministic_suggestion, group_medians, subscribers_per_1000
from app.performance_models import EDITORIAL_FORMATS, HOOK_TYPES, Measurement, PerformanceFilters, PerformanceValidationError, PerformanceVideo, SAO_PAULO, new_id
from app.performance_snapshot import safe_result_prefill
from app.performance_sync import sync_youtube_performance
from app.performance_store import DuplicatePerformanceVideoError, PerformanceStore
from app.youtube import YouTubeError, list_youtube_accounts


def _number(label: str, key: str, *, integer: bool = False, help: str | None = None):
    text = st.text_input(label, key=key, help=help)
    if not text.strip(): return None
    return int(text) if integer else float(text)


def _video_form(store: PerformanceStore, prefix: str, existing: PerformanceVideo | None = None) -> None:
    with st.form(f"{prefix}_video"):
        title = st.text_input("Título *", value=existing.title if existing else "")
        channel = st.text_input("Apelido do canal * (não e-mail)", value=existing.channel if existing else "")
        left, right = st.columns(2)
        youtube_id = left.text_input("ID do vídeo no YouTube (opcional)", value=existing.youtube_video_id or "" if existing else "")
        youtube_url = right.text_input("URL do YouTube (opcional)", value=existing.youtube_url or "" if existing else "")
        published_at = st.text_input("Publicado em (ISO; fuso America/Sao_Paulo)", value=existing.published_at or "" if existing else "", help="Ex.: 2026-10-08T14:30:00-03:00. Deixe vazio se desconhecido.")
        topic, series = st.columns(2)
        topic = topic.text_input("Tema", value=existing.topic or "" if existing else "")
        series = series.text_input("Série", value=existing.series or "" if existing else "")
        hook = st.text_area("Texto do gancho", value=existing.hook_text or "" if existing else "")
        a, b = st.columns(2)
        hook_type = a.selectbox("Tipo de gancho", options=("—",) + HOOK_TYPES, index=0 if not existing or not existing.hook_type else HOOK_TYPES.index(existing.hook_type)+1)
        editorial = b.selectbox("Formato editorial", options=("—",) + EDITORIAL_FORMATS, index=0 if not existing or not existing.editorial_format else EDITORIAL_FORMATS.index(existing.editorial_format)+1)
        c, d, e = st.columns(3)
        duration = c.text_input("Duração real (s)", value="" if not existing or existing.duration_seconds is None else str(existing.duration_seconds))
        scenes = d.text_input("Nº de cenas", value="" if not existing or existing.scene_count is None else str(existing.scene_count))
        shots = e.text_input("Nº de planos", value="" if not existing or existing.shot_count is None else str(existing.shot_count))
        learned = st.text_area("O que aprendemos", value=existing.learned or "" if existing else "")
        next_test, main_variable = st.columns(2)
        next_test = next_test.text_input("Próximo teste", value=existing.next_test or "" if existing else "")
        main_variable = main_variable.text_input("Variável principal", value=existing.main_variable or "" if existing else "")
        comparison_method = st.text_input("Como comparar", value=existing.comparison_method or "" if existing else "")
        submitted = st.form_submit_button("Salvar acompanhamento" if not existing else "Salvar alterações")
    if submitted:
        try:
            record = PerformanceVideo(id=existing.id if existing else new_id("short"), title=title, channel=channel, youtube_video_id=youtube_id, youtube_url=youtube_url, published_at=published_at, topic=topic, series=series, hook_text=hook, hook_type=None if hook_type == "—" else hook_type, editorial_format=None if editorial == "—" else editorial, duration_seconds=duration or None, scene_count=scenes or None, shot_count=shots or None, production_snapshot=existing.production_snapshot if existing else None, learned=learned, next_test=next_test, main_variable=main_variable, comparison_method=comparison_method)
            store.save_video(record); st.success("Acompanhamento salvo. Nenhuma coleta ou upload foi acionado.")
        except (PerformanceValidationError, DuplicatePerformanceVideoError, ValueError) as exc: st.error(str(exc))


def _measurement_form(store: PerformanceStore, videos: list[PerformanceVideo]) -> None:
    if not videos: return
    st.markdown("#### Registrar ou corrigir medição")
    options = {f"{video.title} — {video.channel}": video for video in videos}
    with st.form("performance_measurement"):
        selected = st.selectbox("Short", list(options))
        measurement_id = st.text_input("ID da medição para corrigir (opcional)", help="Deixe vazio para criar. Copie o ID da tabela para editar o mesmo snapshot.")
        collected_at = st.text_input("Coletado em *", value=datetime.now(SAO_PAULO).replace(microsecond=0).isoformat())
        horizon = st.selectbox("Horizonte declarado", ("48h", "7d", "custom"))
        custom = st.text_input("Horas personalizadas", disabled=horizon != "custom")
        a, b, c = st.columns(3)
        views = a.text_input("Visualizações totais", help="Valor cumulativo do YouTube Studio.")
        engaged = b.text_input("Visualizações engajadas", help="Valor cumulativo do YouTube Studio.")
        subs = c.text_input("Inscritos ganhos")
        d, e, f = st.columns(3)
        stayed = d.text_input("% continuou assistindo")
        average_seconds = e.text_input("Média assistida (segundos)")
        average_percent = f.text_input("% médio assistido", help="Pode superar 100% em replays.")
        observation = st.text_area("Observação manual de retenção")
        submitted = st.form_submit_button("Salvar medição")
    if submitted:
        try:
            item = Measurement(id=measurement_id.strip() or new_id("measurement"), video_id=options[selected].id, collected_at=collected_at, horizon=horizon, custom_horizon_hours=custom or None, views=views or None, engaged_views=engaged or None, subscribers_gained=subs or None, stayed_to_watch_percent=stayed or None, average_watch_seconds=average_seconds or None, average_watch_percent=average_percent or None, retention_observation=observation)
            store.save_measurement(item); st.success("Snapshot cumulativo salvo. Valores não são somados.")
        except (PerformanceValidationError, ValueError) as exc: st.error(str(exc))


def render_channel_performance(input_root: Path, *, available_video: Path | None = None, project: Any = None, effective: dict[str, Any] | None = None) -> None:
    st.header("Resultados do canal")
    st.caption("Painel local e manual: não usa GPU, modelos de voz, OAuth, APIs externas nem publica vídeos.")
    try: store = PerformanceStore(input_root); store.migrate()
    except Exception as exc: st.error(f"Analytics indisponível sem afetar seus renders: {exc}"); return
    accounts = ()
    try: accounts = list_youtube_accounts()
    except YouTubeError as exc: st.warning(f"Não foi possível listar as contas locais: {exc}")
    st.markdown("#### Sincronizar com YouTube")
    st.caption("A sincronização é manual. Ela consulta somente a conta escolhida e nunca publica, renderiza ou altera o projeto JSON.")
    if accounts:
        account_map = {account.id: account for account in accounts}
        selected_account = st.selectbox("Conta para sincronizar", [""] + list(account_map), format_func=lambda value: "Selecione uma conta" if not value else account_map[value].display_name, key="performance_sync_account")
        max_results = st.number_input("Máximo de vídeos recentes", min_value=1, max_value=100, value=50, key="performance_sync_limit")
        if st.button("Sincronizar resultados do YouTube", type="primary", disabled=not selected_account):
            try:
                with st.spinner("Consultando vídeos e métricas do YouTube…"):
                    total, created = sync_youtube_performance(store, selected_account, int(max_results))
                st.success(f"Sincronização concluída: {total} vídeo(s), {created} novo(s) no acompanhamento local.")
            except YouTubeError as exc:
                st.error(f"Não foi possível sincronizar: {exc} Reconecte a conta para conceder leitura analítica, se necessário.")
            except Exception as exc:
                st.error(f"A sincronização falhou sem alterar renderizações ou publicações: {exc}")
    else:
        st.info("Conecte uma conta OAuth no fluxo de publicação e reconecte contas antigas para conceder leitura do YouTube Analytics.")
    if available_video and available_video.is_file() and project is not None:
        if st.button("Acompanhar este Short", help="Abre um cadastro explícito para este MP4; não registra nada automaticamente."):
            try: st.session_state["performance_prefill"] = safe_result_prefill(available_video, project, effective or {})
            except Exception as exc: st.error(f"Não foi possível preparar o acompanhamento: {exc}")
    prefill = st.session_state.get("performance_prefill")
    with st.expander("Cadastrar Short manualmente" if not prefill else "Confirmar Short a acompanhar", expanded=bool(prefill)):
        _video_form(store, "performance_prefill" if prefill else "performance_manual", prefill)
        if prefill: st.caption("O snapshot de produção é congelado ao salvar; dados editoriais podem ser ajustados depois.")
    videos = store.list_videos()
    if videos:
        st.markdown("#### Vídeos e histórico")
        filters_a, filters_b, filters_c = st.columns(3)
        channels = ["—"] + sorted({item.channel for item in videos})
        topics = ["—"] + sorted({item.topic for item in videos if item.topic})
        series_list = ["—"] + sorted({item.series for item in videos if item.series})
        channel = filters_a.selectbox("Filtrar canal", channels)
        topic = filters_b.selectbox("Filtrar tema", topics)
        series = filters_c.selectbox("Filtrar série", series_list)
        filters_d, filters_e, filters_f = st.columns(3)
        hook_filter = filters_d.selectbox("Filtrar tipo de gancho", ("—",) + HOOK_TYPES)
        format_filter = filters_e.selectbox("Filtrar formato", ("—",) + EDITORIAL_FORMATS)
        duration_range = filters_f.text_input("Faixa de duração (min-max s)", help="Ex.: 20-45. Deixe vazio para não filtrar.")
        minimum, maximum = None, None
        if duration_range.strip():
            try:
                parts = duration_range.split("-", 1); minimum = float(parts[0]); maximum = float(parts[1])
                if minimum < 0 or maximum < minimum: raise ValueError
            except ValueError:
                st.error("Use uma faixa de duração válida, por exemplo 20-45.")
        filtered = store.list_videos(PerformanceFilters(channel=None if channel == "—" else channel, topic=None if topic == "—" else topic, series=None if series == "—" else series, hook_type=None if hook_filter == "—" else hook_filter, editorial_format=None if format_filter == "—" else format_filter, min_duration_seconds=minimum, max_duration_seconds=maximum))
        rows = []
        for item in filtered:
            rows.append({"id": item.id, "título": item.title, "canal": item.channel, "tema": item.topic, "série": item.series, "gancho": item.hook_type, "formato": item.editorial_format, "duração (s)": item.duration_seconds, "publicado": item.published_at})
        st.dataframe(rows, use_container_width=True, hide_index=True)
        edit_id = st.selectbox("Editar vídeo", ["—"] + [item.id for item in filtered])
        if edit_id != "—": _video_form(store, f"edit_{edit_id}", next(item for item in videos if item.id == edit_id))
        _measurement_form(store, filtered)
        selected_id = st.selectbox("Histórico do Short", [item.id for item in filtered], format_func=lambda ident: next(item.title for item in filtered if item.id == ident))
        history = store.list_measurements(selected_id)
        st.dataframe([{"id": item.id, "coleta": item.collected_at, "origem": item.source or "manual", "horizonte": item.horizon, "vis": item.views, "engajadas": item.engaged_views, "inscritos": item.subscribers_gained, "inscritos/1000 engajadas": subscribers_per_1000(item), "observação": item.retention_observation} for item in history], use_container_width=True, hide_index=True)
        st.markdown("#### Comparar grupos")
        horizon, tolerance, group = st.columns(3)
        horizon = horizon.selectbox("Horizonte", ("48h", "7d", "custom"))
        tolerance = tolerance.number_input("Tolerância (horas)", min_value=0.0, value=6.0)
        group = group.selectbox("Agrupar por", ("hook_type", "editorial_format", "topic", "series", "channel"))
        custom = st.number_input("Alvo personalizado (horas)", min_value=0.1, value=72.0, disabled=horizon != "custom")
        selected, excluded = choose_comparable(filtered, store.list_measurements(), horizon, float(tolerance), float(custom) if horizon == "custom" else None)
        st.caption(f"{len(selected)} vídeo(s) comparáveis; {len(excluded)} medição(ões) ficaram apenas no histórico por idade desconhecida ou fora da tolerância.")
        st.dataframe([{"vídeo": item.video.title, "canal": item.video.channel, "horizonte": item.measurement.horizon, "idade real (h)": round(item.actual_age_hours, 2), "coleta": item.measurement.collected_at} for item in selected], hide_index=True, use_container_width=True)
        groups = group_medians(selected, group)
        st.dataframe([{"grupo": name, **row} for name, row in groups.items()], hide_index=True, use_container_width=True)
        metric = st.selectbox("Métrica para leitura descritiva", list(METRICS), format_func=lambda key: METRICS[key])
        chart_values = {name: row.get(f"{metric}_median") for name, row in groups.items() if row.get(f"{metric}_median") is not None}
        if chart_values:
            st.bar_chart(chart_values, x_label="Grupo", y_label=f"Mediana: {METRICS[metric]}")
        else:
            st.caption("Sem valores válidos desta métrica para desenhar o gráfico.")
        minimum = st.number_input("Mínimo por grupo", min_value=1, value=3, step=1)
        st.info(deterministic_suggestion(groups, metric, int(minimum)))
    else: st.info("Ainda não há dados. Cadastre um Short manualmente para começar; o banco ficará em input/analytics/.")
