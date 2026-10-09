"""Cálculos transparentes e deliberadamente descritivos para resultados."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import median
from typing import Iterable

from app.performance_models import Measurement, PerformanceVideo, as_datetime


def age_hours(video: PerformanceVideo, measurement: Measurement) -> float | None:
    published, collected = as_datetime(video.published_at), as_datetime(measurement.collected_at)
    if not published or not collected or collected < published: return None
    return (collected - published).total_seconds() / 3600


def subscribers_per_1000(measurement: Measurement) -> float | None:
    if measurement.subscribers_gained is None or not measurement.engaged_views: return None
    return measurement.subscribers_gained / measurement.engaged_views * 1000

@dataclass(frozen=True)
class SelectedMeasurement:
    video: PerformanceVideo
    measurement: Measurement
    actual_age_hours: float


def choose_comparable(videos: Iterable[PerformanceVideo], measurements: Iterable[Measurement], horizon: str, tolerance_hours: float, custom_hours: float | None = None) -> tuple[list[SelectedMeasurement], list[Measurement]]:
    target = 48.0 if horizon == "48h" else 168.0 if horizon == "7d" else float(custom_hours or 0)
    by_video: dict[str, list[Measurement]] = defaultdict(list)
    for item in measurements:
        if item.horizon == horizon and (horizon != "custom" or item.custom_horizon_hours == custom_hours): by_video[item.video_id].append(item)
    chosen, excluded = [], []
    for video in videos:
        candidates = []
        for item in by_video.get(video.id, []):
            age = age_hours(video, item)
            if age is None or abs(age - target) > tolerance_hours: excluded.append(item)
            else: candidates.append((abs(age-target), -as_datetime(item.collected_at).timestamp(), item, age))
        if candidates:
            _, _, item, age = min(candidates); chosen.append(SelectedMeasurement(video, item, age))
    return chosen, excluded


METRICS = {"views": "Visualizações", "engaged_views": "Visualizações engajadas", "stayed_to_watch_percent": "% continuou assistindo", "average_watch_seconds": "Média assistida (s)", "average_watch_percent": "% médio assistido", "subscribers_gained": "Inscritos ganhos", "subscribers_per_1000": "Inscritos / 1.000 engajadas"}

def group_medians(selected: Iterable[SelectedMeasurement], group_field: str) -> dict[str, dict[str, float | int | None]]:
    grouped: dict[str, list[SelectedMeasurement]] = defaultdict(list)
    for item in selected: grouped[str(getattr(item.video, group_field) or "Não informado")].append(item)
    result = {}
    for group, items in grouped.items():
        values = {metric: [] for metric in METRICS}
        for item in items:
            for metric in METRICS:
                value = subscribers_per_1000(item.measurement) if metric == "subscribers_per_1000" else getattr(item.measurement, metric)
                if value is not None: values[metric].append(value)
        result[group] = {"videos": len(items), **{f"{metric}_median": median(value) if value else None for metric, value in values.items()}, **{f"{metric}_n": len(value) for metric, value in values.items()}}
    return result


def deterministic_suggestion(groups: dict[str, dict[str, float | int | None]], metric: str, minimum_sample: int) -> str:
    eligible = [(name, row) for name, row in groups.items() if int(row.get(f"{metric}_n", 0) or 0) >= minimum_sample and row.get(f"{metric}_median") is not None]
    if len(eligible) < 2: return f"Dados insuficientes: são necessários ao menos {minimum_sample} vídeos com esta métrica em dois grupos."
    ordered = sorted(eligible, key=lambda pair: float(pair[1][f"{metric}_median"] or 0), reverse=True)
    best, other = ordered[0], ordered[1]
    return f"Descrição, não causalidade: {best[0]} teve mediana {best[1][f'{metric}_median']:.2f} (n={best[1][f'{metric}_n']}) versus {other[0]} {other[1][f'{metric}_median']:.2f} (n={other[1][f'{metric}_n']}). Teste a variável principal de forma controlada."
