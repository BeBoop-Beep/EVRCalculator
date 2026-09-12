"""Prepared, run-scoped Set diagnostics for the frozen Collector Appeal V7 path.

These values explain sources of roster strength; they are not additive Collector
Appeal formula terms.  Subject identities are collapsed before aggregation so
duplicate printings cannot increase a Set's diagnostic.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

from backend.scripts.build_pokemon_collector_appeal_v6_corrected_successor import pokemon_d, trainer_d

METHODOLOGY_VERSION = "collector_component_diagnostics_v1_exact_v7_ablation"


def _bounded(value: Any) -> Optional[float]:
    if value is None:
        return None
    return min(100.0, max(0.0, float(value)))


def _card_paths(row: Mapping[str, Any]) -> Optional[Tuple[float, float, float]]:
    baseline = _bounded(row.get("subject_baseline_score"))
    if baseline is None:
        return None
    play = _bounded(row.get("playability_score"))
    artist = _bounded(row.get("artist_recognition_score"))
    after_play = baseline if play is None else baseline + (100.0 - baseline) * .20 * play / 100.0
    full = after_play if artist is None else after_play + (100.0 - after_play) * .10 * artist / 100.0
    without_play = baseline if artist is None else baseline + (100.0 - baseline) * .10 * artist / 100.0
    return full, after_play, without_play


def _identities(row: Mapping[str, Any]) -> list[str]:
    raw = (row.get("component_inputs_json") or {}).get("subjectIdentity")
    return [part.strip() for part in str(raw or "").split(" + ") if part.strip()]


def _aggregate(rows: Iterable[Mapping[str, Any]], score_index: int) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    pokemon, trainers = defaultdict(list), defaultdict(list)
    for row in rows:
        path = _card_paths(row)
        if path is None:
            continue
        target = pokemon if row.get("subject_policy") == "pokemon" else trainers if row.get("subject_policy") == "trainer" else None
        if target is not None:
            for identity in _identities(row):
                target[identity].append(path[score_index])
    pokemon_value = pokemon_d([max(values) for values in pokemon.values()])[0] if pokemon else None
    trainer_value = trainer_d([max(values) for values in trainers.values()]) if trainers else None
    if pokemon_value is None:
        combined = None
    else:
        combined = pokemon_value + ((100.0 - pokemon_value) * .15 * trainer_value / 100.0 if trainer_value is not None else 0.0)
    return pokemon_value, trainer_value, combined


def build_raw_component_diagnostics(card_rows: Iterable[Mapping[str, Any]]) -> Dict[str, Dict[str, Optional[float]]]:
    by_set: Dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in card_rows:
        by_set[str(row["set_id"])].append(row)
    result = {}
    for set_id, rows in by_set.items():
        pure_pokemon, pure_trainer, _ = _aggregate(
            [{**row, "playability_score": None, "artist_recognition_score": None} for row in rows], 0
        )
        _, _, full = _aggregate(rows, 0)
        _, _, without_artist = _aggregate(rows, 1)
        _, _, without_play = _aggregate(rows, 2)
        artist_evidence = any(row.get("artist_recognition_score") is not None for row in rows)
        playability_evidence = any(row.get("playability_score") is not None for row in rows)
        result[set_id] = {
            "pokemonAppeal": pure_pokemon,
            "trainerAppeal": pure_trainer,
            "artistImpact": None if not artist_evidence or full is None or without_artist is None else max(0.0, full - without_artist),
            "playabilityImpact": None if not playability_evidence or full is None or without_play is None else max(0.0, full - without_play),
        }
    return result


def build_component_ranking_rows(card_rows: Iterable[Mapping[str, Any]], model_run_id: str) -> list[dict[str, Any]]:
    raw = build_raw_component_diagnostics(card_rows)
    keys = ("pokemonAppeal", "trainerAppeal", "artistImpact", "playabilityImpact")
    ranked: Dict[str, Dict[str, tuple[int, float, int]]] = {}
    for key in keys:
        values = [(sid, float(parts[key])) for sid, parts in raw.items() if parts.get(key) is not None]
        values.sort(key=lambda item: (-item[1], item[0]))
        lo, hi, cohort = (min((v for _, v in values), default=0.0), max((v for _, v in values), default=0.0), len(values))
        ranked[key] = {
            sid: (index, 100.0 if hi == lo else 100.0 * (value - lo) / (hi - lo), cohort)
            for index, (sid, value) in enumerate(values, 1)
        }
    rows = []
    for sid in sorted(raw):
        drivers = {}
        for key in keys:
            value = raw[sid].get(key)
            prepared = ranked[key].get(sid)
            drivers[key] = {
                "rawValue": value,
                "publicScore": None if prepared is None else round(prepared[1], 6),
                "relativeScore": None if prepared is None else round(prepared[1], 6),
                "rank": None if prepared is None else prepared[0],
                "cohortSize": None if prepared is None else prepared[2],
                "status": "scored" if prepared is not None else "unavailable",
                "statusReason": None if prepared is not None else "component_evidence_unavailable",
                "methodologyVersion": METHODOLOGY_VERSION,
            }
        rows.append({"model_run_id": model_run_id, "set_id": sid, "drivers_json": drivers, "methodology_version": METHODOLOGY_VERSION})
    return rows
