"""Build Collector Appeal V8 ANCHOR25 as an append-only successor to V7.

V8 changes exactly one construct:
- Trainer subject baseline is calibrated 25% toward the Pokemon subject-score
  distribution at the same tie-aware within-domain percentile.

Pokemon, Playability, Artist, Treatment diagnostics, Pull Scarcity diagnostics,
set aggregation, generalized frequency, and signed frequency modifier mechanics
remain unchanged. The validated candidate does not re-estimate downstream lifts
after changing the Trainer baseline: it preserves each card's exact realized V7
combined headroom-lift fraction and applies that fraction to the calibrated
subject. This is the preregistered/replayed ANCHOR25 formula.

Default execution is offline and read-only. Persistence is available only with
--write-stage; promotion is deliberately out of scope for this builder.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date
import json
import math
import os
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

import numpy as np
from dotenv import load_dotenv
from supabase import ClientOptions, create_client

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.desirability.card_collector_rankings import build_card_collector_ranking_rows
from backend.desirability.collector_appeal import collector_appeal_v4_frequency_index
from backend.desirability.collector_component_rankings import build_component_ranking_rows
from backend.desirability.opening_appeal import union_probability_from_cards
from backend.scripts.build_pokemon_collector_appeal_v6_corrected_successor import (
    canonical_hash,
    pokemon_d,
    trainer_d,
)
from backend.scripts.build_pokemon_collector_appeal_v7_expanded import build as build_v7

MODEL_VERSION = "pokemon_collector_appeal_v8_anchor25_cross_domain_v1"
ALPHA = 0.25
ANCHOR_METHOD = "trainer_tie_midrank_percentile_to_pokemon_empirical_quantile_v1"
V7_VERSION = "pokemon_collector_appeal_v7_expanded_price_blind_v1"
V7_ARTIFACT = ROOT / "backend/artifacts/collector_appeal_v7_expanded_candidate_v1.json"
OUTPUT = ROOT / "backend/artifacts/collector_appeal_v8_anchor25_candidate_v1.json"


def tie_percentiles(values: Mapping[str, float]) -> dict[str, float]:
    ordered = sorted(values.items(), key=lambda item: (item[1], item[0]))
    n = len(ordered)
    out: dict[str, float] = {}
    i = 0
    while i < n:
        j = i + 1
        while j < n and ordered[j][1] == ordered[i][1]:
            j += 1
        percentile = ((i + 1 + j) / 2.0 - 0.5) / n
        for key, _ in ordered[i:j]:
            out[key] = percentile
        i = j
    return out


def empirical_quantile(values: Sequence[float], percentile: float) -> float:
    return float(np.quantile(np.asarray(sorted(values), dtype=float), percentile, method="linear"))


def identity_authorities(cards: Sequence[Mapping[str, Any]]) -> tuple[dict[str, float], dict[str, float]]:
    grouped: dict[str, dict[str, list[float]]] = {
        "pokemon": defaultdict(list),
        "trainer": defaultdict(list),
    }
    for card in cards:
        domain = str(card.get("subject_type") or "")
        identity = str(card.get("subject_identity") or "")
        if domain in grouped and identity:
            grouped[domain][identity].append(float(card["subject_appeal_corrected"]))
    result = []
    for domain in ("pokemon", "trainer"):
        authority: dict[str, float] = {}
        for identity, values in grouped[domain].items():
            if max(values) - min(values) > 1e-9:
                raise RuntimeError(f"V8_NON_UNIQUE_SUBJECT_AUTHORITY:{domain}:{identity}")
            authority[identity] = values[0]
        result.append(authority)
    return result[0], result[1]


def trainer_pokemon_anchors(trainers: Mapping[str, float], pokemon: Mapping[str, float]) -> dict[str, float]:
    percentiles = tie_percentiles(trainers)
    pokemon_values = list(pokemon.values())
    return {
        identity: empirical_quantile(pokemon_values, percentile)
        for identity, percentile in percentiles.items()
    }


def calibrated_subject(*, original: float, anchor: float, domain: str) -> float:
    if domain != "trainer":
        return original
    return (1.0 - ALPHA) * original + ALPHA * anchor


def _rank(values: Mapping[str, float]) -> dict[str, int]:
    return {
        key: index
        for index, (key, _) in enumerate(
            sorted(values.items(), key=lambda item: (-item[1], item[0])),
            1,
        )
    }


def _spearman_from_scores(a: Mapping[str, float], b: Mapping[str, float]) -> float | None:
    keys = sorted(set(a) & set(b))
    if len(keys) < 3:
        return None
    ra, rb = _rank({key: a[key] for key in keys}), _rank({key: b[key] for key in keys})
    xa = np.asarray([ra[key] for key in keys], dtype=float)
    xb = np.asarray([rb[key] for key in keys], dtype=float)
    if xa.std() <= 1e-12 or xb.std() <= 1e-12:
        return None
    return float(np.corrcoef(xa, xb)[0, 1])


def realized_combined_headroom_fraction(*, subject_v7: float, card_score_v7: float) -> float:
    """Recover the exact realized V7 downstream lift as a headroom fraction."""
    subject_v7 = float(subject_v7)
    card_score_v7 = float(card_score_v7)
    if subject_v7 >= 100.0:
        if abs(card_score_v7 - subject_v7) > 1e-12:
            raise RuntimeError("V8_INVALID_V7_COMBINED_LIFT_AT_CEILING")
        return 0.0
    fraction = (card_score_v7 - subject_v7) / (100.0 - subject_v7)
    if fraction < -1e-12 or fraction > 1.0 + 1e-12:
        raise RuntimeError(f"V8_INVALID_V7_COMBINED_LIFT_FRACTION:{fraction}")
    return min(1.0, max(0.0, fraction))


def apply_combined_headroom_lift(subject: float, fraction: float) -> float:
    return float(subject) + (100.0 - float(subject)) * float(fraction)


def build_v8_cards(v7_cards: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    pokemon, trainers = identity_authorities(v7_cards)
    anchors = trainer_pokemon_anchors(trainers, pokemon)
    cards: list[dict[str, Any]] = []
    trainer_original: dict[str, float] = {}
    trainer_calibrated: dict[str, float] = {}
    control_replay_errors: list[float] = []
    pokemon_score_deltas: list[float] = []

    for source in v7_cards:
        domain = str(source.get("subject_type") or "")
        identity = str(source.get("subject_identity") or "")
        original = float(source["subject_appeal_corrected"])
        v7_final = float(source["card_collector_appeal_v7"])
        fraction = realized_combined_headroom_fraction(
            subject_v7=original,
            card_score_v7=v7_final,
        )
        control_replay = apply_combined_headroom_lift(original, fraction)
        control_replay_errors.append(abs(control_replay - v7_final))

        anchor = anchors.get(identity, original)
        subject = calibrated_subject(original=original, anchor=anchor, domain=domain)
        final = apply_combined_headroom_lift(subject, fraction)

        if domain == "trainer" and identity:
            trainer_original[identity] = original
            trainer_calibrated[identity] = subject
        if domain == "pokemon":
            pokemon_score_deltas.append(abs(final - v7_final))

        cards.append({
            **source,
            "subject_appeal_v7_original": original,
            "trainer_pokemon_anchor_score": anchor if domain == "trainer" else None,
            "subject_appeal_v8": subject,
            "v7_realized_combined_lift_fraction": fraction,
            "combined_lift_points_v8": final - subject,
            "card_collector_appeal_v8": final,
        })

    max_control_error = max(control_replay_errors, default=0.0)
    max_pokemon_delta = max(pokemon_score_deltas, default=0.0)
    analysis = {
        "pokemonIdentityCount": len(pokemon),
        "trainerIdentityCount": len(trainers),
        "pokemonUnchanged": max_pokemon_delta <= 1e-12,
        "maxPokemonCardScoreDelta": max_pokemon_delta,
        "maxV7ControlReplayError": max_control_error,
        "controlReplayExact": max_control_error <= 1e-12,
        "trainerWithinDomainSpearman": _spearman_from_scores(trainer_original, trainer_calibrated),
        "trainerAnchorCount": len(anchors),
        "downstreamLiftMode": "preserve_exact_v7_realized_combined_headroom_fraction",
    }
    return cards, analysis

def build_v8_sets(v7_sets: Sequence[Mapping[str, Any]], cards: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    frozen = {str(row["set_id"]): row for row in v7_sets}
    by_set: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in cards:
        set_id = str(row["set_id"])
        if set_id in frozen:
            by_set[set_id].append(row)

    sets: list[dict[str, Any]] = []
    for set_id in sorted(frozen):
        rows = by_set.get(set_id, [])
        if not rows:
            raise RuntimeError(f"V8_FROZEN_SET_CARD_MEMBERSHIP_MISSING:{set_id}")
        base = frozen[set_id]
        pg: dict[str, list[float]] = defaultdict(list)
        tg: dict[str, list[float]] = defaultdict(list)
        for row in rows:
            target = pg if row["subject_type"] == "pokemon" else tg if row["subject_type"] == "trainer" else None
            if target is None:
                continue
            for name in str(row.get("subject_identity") or "").split(" + "):
                name = name.strip()
                if name:
                    target[name].append(float(row["card_collector_appeal_v8"]))

        dp, strength, breadth = pokemon_d([max(values) for values in pg.values()])
        dt = trainer_d([max(values) for values in tg.values()])
        trainer_lift = (100.0 - dp) * 0.15 * dt / 100.0
        d_final = dp + trainer_lift

        desirable = [
            row for row in rows
            if row.get("hit_eligibility") and float(row["card_collector_appeal_v8"]) > 50.0
        ]
        modeled = []
        covered_ids = set()
        for row in desirable:
            scarcity = row.get("pull_scarcity_diagnostic")
            if scarcity and scarcity.get("probability") is not None and scarcity.get("slotGroup"):
                modeled.append({
                    "canonical_card_id": str(row["canonical_card_id"]),
                    "pull_probability": float(scarcity["probability"]),
                    "slot_group": str(scarcity["slotGroup"]),
                })
                covered_ids.add(str(row["canonical_card_id"]))

        excess = sum(float(row["card_collector_appeal_v8"]) - 50.0 for row in desirable)
        covered = sum(
            float(row["card_collector_appeal_v8"]) - 50.0
            for row in desirable
            if str(row["canonical_card_id"]) in covered_ids
        )
        coverage = covered / excess if excess else None
        unique_modeled = list({row["canonical_card_id"]: row for row in modeled}.values())
        frequency = (
            union_probability_from_cards(unique_modeled)
            if unique_modeled and coverage is not None and coverage >= 0.25
            else None
        )
        index = collector_appeal_v4_frequency_index(frequency) if frequency is not None else None
        z = 2.0 * index - 1.0 if index is not None else None
        modifier = (2.0 * z if z >= 0 else z) if z is not None else None
        final = min(100.0, max(0.0, d_final + modifier)) if modifier is not None else None

        base_desirable = {
            str(row["canonical_card_id"])
            for row in rows
            if row.get("hit_eligibility") and float(row["card_collector_appeal_v7"]) > 50.0
        }
        new_desirable = {str(row["canonical_card_id"]) for row in desirable}
        sets.append({
            "set_id": set_id,
            "set_name": base.get("set_name"),
            "D_pokemon": dp,
            "S": strength,
            "B": breadth,
            "D_trainer": dt,
            "trainer_lift_points": trainer_lift,
            "D_final": d_final,
            "F": frequency,
            "frequency_index": index,
            "frequency_modifier": modifier,
            "collector_appeal": final,
            "v7_D_final": base.get("D_final"),
            "D_delta": None if base.get("D_final") is None else d_final - float(base["D_final"]),
            "v7_F": base.get("F"),
            "F_delta": None if frequency is None or base.get("F") is None else frequency - float(base["F"]),
            "v7_collector_appeal": base.get("collector_appeal"),
            "collector_delta": None if final is None or base.get("collector_appeal") is None else final - float(base["collector_appeal"]),
            "desirable_card_count": len(desirable),
            "entering_cards": sorted(new_desirable - base_desirable),
            "leaving_cards": sorted(base_desirable - new_desirable),
            "unavailable_reason": None if final is not None else "collector_appeal_unavailable_no_generalized_frequency",
        })

    ranked = sorted(
        (row for row in sets if row["collector_appeal"] is not None),
        key=lambda row: (-float(row["collector_appeal"]), str(row["set_id"])),
    )
    for index, row in enumerate(ranked, 1):
        row["rank"] = index
    return sets


def build_from_v7(v7: Mapping[str, Any], *, build_mode: str) -> dict[str, Any]:
    manifest_v7 = v7.get("manifest") or {}
    if manifest_v7.get("modelVersion") != V7_VERSION:
        raise RuntimeError("V8_BASE_ARTIFACT_IS_NOT_FROZEN_V7")
    source_authority = dict(manifest_v7.get("sourceAuthority") or {})
    if not source_authority:
        source_ids = list(manifest_v7.get("sourceRunIds") or [])
        if len(source_ids) != 6:
            raise RuntimeError("V8_BASE_V7_SOURCE_AUTHORITY_INCOMPLETE")
        source_authority = dict(zip(
            ("pokemonTrends", "trainer12m", "trainer5y", "playability", "artist12m", "artist5y"),
            map(str, source_ids),
        ))
    if set(source_authority) != {
        "pokemonTrends", "trainer12m", "trainer5y", "playability", "artist12m", "artist5y"
    }:
        raise RuntimeError("V8_BASE_V7_SOURCE_AUTHORITY_INCOMPLETE")

    cards, calibration = build_v8_cards(v7["cards"])
    sets = build_v8_sets(v7["sets"], cards)

    formula_contract = {
        "modelVersion": MODEL_VERSION,
        "baseModelVersion": V7_VERSION,
        "pokemonWeights": [0.75, 0.25],
        "trainerWeights": [0.4, 0.6],
        "trainerCrossDomainCalibration": {
            "alpha": ALPHA,
            "anchorMethod": ANCHOR_METHOD,
            "mapping": "(1-alpha)*trainer_subject + alpha*pokemon_quantile_at_trainer_midrank_percentile",
        },
        "artistWeights": [0.4, 0.6],
        "artistLambdaV7Source": 0.10,
        "playabilityLambdaV7Source": 0.20,
        "downstreamHeadroomLift": {
            "mode": "preserve_exact_v7_realized_combined_headroom_fraction",
            "definition": "(v7_card_score-v7_subject)/(100-v7_subject)",
            "application": "v8_subject+(100-v8_subject)*v7_realized_combined_fraction",
            "rawPlayabilityArtistInputs": "diagnostic_only_after_calibration",
        },
        "trainerSetLambda": 0.15,
        "frequency": "unchanged_generalized_F_card_gt_50",
        "c5": "unchanged_collector_c5_frozen_signed_frequency_v1",
        "price": "excluded",
        "treatment": "diagnostic_only",
        "scarcity": "diagnostic_only",
    }
    formula_fingerprint = canonical_hash(formula_contract)
    card_fingerprint = canonical_hash([
        {
            "canonical_card_id": row["canonical_card_id"],
            "subject_appeal_v8": row["subject_appeal_v8"],
            "v7_realized_combined_lift_fraction": row["v7_realized_combined_lift_fraction"],
            "card_collector_appeal_v8": row["card_collector_appeal_v8"],
        }
        for row in sorted(cards, key=lambda x: str(x["canonical_card_id"]))
    ])
    set_fingerprint = canonical_hash([
        {
            key: row.get(key)
            for key in ("set_id", "D_pokemon", "D_trainer", "D_final", "F", "frequency_modifier", "collector_appeal")
        }
        for row in sorted(sets, key=lambda x: str(x["set_id"]))
    ])
    expected = {
        "cardRows": len(cards),
        "c4Rows": len(sets),
        "c5Rows": len(sets),
        "scoredRows": sum(row.get("collector_appeal") is not None for row in sets),
        "unavailableRows": sum(row.get("collector_appeal") is None for row in sets),
    }
    manifest = {
        "modelVersion": MODEL_VERSION,
        "baseModelVersion": V7_VERSION,
        "buildMode": build_mode,
        "formulaFingerprint": formula_fingerprint,
        "formulaContract": formula_contract,
        "cardFingerprint": card_fingerprint,
        "setFingerprint": set_fingerprint,
        "sourceRunIds": list(manifest_v7["sourceRunIds"]),
        "sourceAuthority": source_authority,
        "expectedCounts": expected,
        "calibrationAnalysis": calibration,
        "pricePolicy": "excluded",
        "treatmentPolicy": "diagnostic_only",
        "scarcityPolicy": "diagnostic_only",
    }
    manifest["modelFingerprint"] = canonical_hash({
        "version": MODEL_VERSION,
        "buildMode": build_mode,
        "formulaFingerprint": formula_fingerprint,
        "sourceAuthority": source_authority,
        "cardFingerprint": card_fingerprint,
        "setFingerprint": set_fingerprint,
        "expectedCounts": expected,
    })
    return {"manifest": manifest, "cards": cards, "sets": sets}


def build(client: Any, *, pokemon_trends_source_run_id: str, trainer_12m_source_run_id: str,
          trainer_5y_source_run_id: str, playability_source_run_id: str,
          artist_12m_source_run_id: str, artist_5y_source_run_id: str) -> dict[str, Any]:
    v7 = build_v7(
        client,
        pokemon_trends_source_run_id=pokemon_trends_source_run_id,
        trainer_12m_source_run_id=trainer_12m_source_run_id,
        trainer_5y_source_run_id=trainer_5y_source_run_id,
        playability_source_run_id=playability_source_run_id,
        artist_12m_source_run_id=artist_12m_source_run_id,
        artist_5y_source_run_id=artist_5y_source_run_id,
    )
    return build_from_v7(v7, build_mode="live_v7_rebuild")


def build_frozen_cutover() -> dict[str, Any]:
    v7 = json.loads(V7_ARTIFACT.read_text(encoding="utf-8"))
    if v7.get("manifest", {}).get("modelFingerprint") != "3b781f4ec01ef8c74c77b34d2b91e9a90231d2feccf2ee41411de64606378c9d":
        raise RuntimeError("V8_FROZEN_CUTOVER_V7_FINGERPRINT_MISMATCH")
    if len(v7.get("cards") or []) != 18293 or len(v7.get("sets") or []) != 128:
        raise RuntimeError("V8_FROZEN_CUTOVER_V7_COHORT_MISMATCH")
    return build_from_v7(v7, build_mode="frozen_v7_exact_cutover")


def persistence_rows(built: Mapping[str, Any], run_id: str):
    authority = built["manifest"]["sourceAuthority"]
    cards = []
    for row in built["cards"]:
        baseline = float(row["subject_appeal_v8"])
        combined_fraction = float(row["v7_realized_combined_lift_fraction"])
        combined_points = float(row["combined_lift_points_v8"])
        raw_play = row.get("playability_raw_score")
        confidence = row.get("confidence")
        playability_score = (
            None if raw_play is None or confidence is None
            else float(raw_play) * float(confidence)
        )
        cards.append({
            "model_run_id": run_id,
            "pokemon_canonical_card_id": row["canonical_card_id"],
            "set_id": row["set_id"],
            "subject_policy": {"pokemon": "pokemon", "trainer": "trainer", "neutral_functional": "neutral"}[row["subject_type"]],
            "subject_baseline_score": baseline,
            "artist_recognition_score": row.get("artist_appeal_score"),
            "playability_score": playability_score,
            # The validated ANCHOR25 candidate preserves the exact realized V7
            # combined headroom fraction. A post-calibration split into separate
            # Playability and Artist fractions was never preregistered, so do not
            # invent one in persisted lineage.
            "artist_lift": None,
            "playability_lift": None,
            "combined_lift": combined_fraction,
            "collector_card_appeal_score": row["card_collector_appeal_v8"],
            "score_status": "scored",
            "confidence": "high" if row.get("artist_appeal_score") is not None else "insufficient",
            "price_input_excluded": True,
            "treatment_input_excluded": True,
            "hit_eligibility_independent": True,
            "component_inputs_json": {
                "subjectType": row["subject_type"],
                "subjectIdentity": row.get("subject_identity"),
                "subjectBaselineV7": row["subject_appeal_v7_original"],
                "trainerPokemonAnchorScore": row.get("trainer_pokemon_anchor_score"),
                "trainerCrossDomainCalibrationAlpha": ALPHA if row["subject_type"] == "trainer" else 0.0,
                "trainerCrossDomainAnchorMethod": ANCHOR_METHOD if row["subject_type"] == "trainer" else None,
                "v7RealizedCombinedHeadroomLiftFraction": combined_fraction,
                "v8CombinedLiftPoints": combined_points,
                "downstreamLiftMode": "preserve_exact_v7_realized_combined_headroom_fraction",
                "playabilityArtistDecomposition": "not_recomputed_unvalidated",
                "playabilityDiagnosticScore": playability_score,
                "artistRecognitionDiagnosticScore": row.get("artist_appeal_score"),
                "artistIdentified": row.get("artist_identified"),
                "artistNames": row.get("artist_names") or [],
                "artistEvidenceStatus": row.get("artist_evidence_status"),
                "treatmentDiagnostic": row.get("treatment_diagnostic"),
                "pullScarcityDiagnostic": row.get("pull_scarcity_diagnostic"),
            },
            "lineage_json": {
                "formulaFingerprint": built["manifest"]["formulaFingerprint"],
                "baseModelVersion": V7_VERSION,
                "sourceAuthority": authority,
                "validatedCandidateFormula": "anchor25_preserve_v7_realized_combined_headroom_fraction",
                "excludedInputs": ["price", "Treatment", "Pull Scarcity as direct score"],
            },
        })

    d_rank = _rank({str(row["set_id"]): float(row["D_final"]) for row in built["sets"]})
    drows, arows = [], []
    for row in built["sets"]:
        subset = [card for card in built["cards"] if card["set_id"] == row["set_id"]]
        drows.append({
            "model_run_id": run_id,
            "set_id": row["set_id"],
            "aggregation_version": "v8_anchor25_cross_domain_D_v1",
            "collector_desirability_score": row["D_final"],
            "collector_desirability_rank": d_rank[str(row["set_id"])],
            "eligible_card_count": sum(bool(card.get("hit_eligibility")) for card in subset),
            "scored_card_count": sum(card["subject_type"] != "neutral_functional" and bool(card.get("hit_eligibility")) for card in subset),
            "neutral_card_count": sum(card["subject_type"] == "neutral_functional" and bool(card.get("hit_eligibility")) for card in subset),
            "unsupported_card_count": 0,
            "score_coverage_ratio": 1,
            "max_card_appeal_score": max(float(card["card_collector_appeal_v8"]) for card in subset),
            "top_3_card_appeal_score": None,
            "top_5_card_appeal_score": None,
            "effective_desirable_card_count": row["desirable_card_count"],
            "subject_rollups_json": [],
            "top_cards_json": [],
            "component_inputs_json": {
                "D_pokemon": row["D_pokemon"],
                "D_trainer": row["D_trainer"],
                "trainerLiftPoints": row["trainer_lift_points"],
                "trainerLambda": 0.15,
                "trainerCrossDomainCalibrationAlpha": ALPHA,
                "trainerCrossDomainAnchorMethod": ANCHOR_METHOD,
                "downstreamLiftMode": "preserve_exact_v7_realized_combined_headroom_fraction",
            },
            "diagnostics_json": {
                "S": row["S"],
                "B": row["B"],
                "v7D": row["v7_D_final"],
                "DDelta": row["D_delta"],
            },
        })
        arows.append({
            "model_run_id": run_id,
            "set_id": row["set_id"],
            "collector_roster_desirability_score": row["D_final"],
            "generalized_desirable_outcome_frequency": row["F"],
            "generalized_frequency_status": "available" if row["F"] is not None else "unavailable",
            "generalized_frequency_status_reason": None if row["F"] is not None else row["unavailable_reason"],
            "frequency_index": row["frequency_index"],
            "frequency_modifier_points": row["frequency_modifier"],
            "collector_appeal_score": row["collector_appeal"],
            "score_status": "scored" if row["collector_appeal"] is not None else "unavailable",
            "score_status_reason": row["unavailable_reason"],
            "collector_appeal_rank": row.get("rank"),
            "component_inputs_json": {
                "formula": "signed_up2_down1",
                "frequencyThreshold": ">50",
                "trainerCrossDomainCalibrationAlpha": ALPHA,
                "trainerCrossDomainAnchorMethod": ANCHOR_METHOD,
                "excludedInputs": ["price", "Treatment", "Pull Scarcity as direct score"],
            },
            "diagnostics_json": {
                "v7F": row["v7_F"],
                "FDelta": row["F_delta"],
                "v7CollectorAppeal": row["v7_collector_appeal"],
                "collectorDelta": row["collector_delta"],
                "enteringCards": row["entering_cards"],
                "leavingCards": row["leaving_cards"],
            },
            "lineage_json": {
                "formulaFingerprint": built["manifest"]["formulaFingerprint"],
                "cardFingerprint": built["manifest"]["cardFingerprint"],
                "setFingerprint": built["manifest"]["setFingerprint"],
                "baseModelVersion": V7_VERSION,
            },
        })
    return cards, drows, arows


def persist_built_model(client: Any, built: Mapping[str, Any], *, as_of_date: date | str):
    manifest = built["manifest"]
    existing = (
        client.table("pokemon_collector_appeal_model_runs")
        .select("id,status,validation_json")
        .eq("model_version", MODEL_VERSION)
        .eq("input_fingerprint", manifest["modelFingerprint"])
        .execute().data or []
    )
    if existing:
        row = existing[0]
        if row.get("status") not in ("validated", "published") or not (row.get("validation_json") or {}).get("passed"):
            raise RuntimeError(f"matching Collector V8 run {row['id']} is not reusable")
        return str(row["id"]), row.get("validation_json"), False

    run = client.table("pokemon_collector_appeal_model_runs").insert({
        "model_version": MODEL_VERSION,
        "as_of_date": str(as_of_date),
        "source_run_ids": manifest["sourceRunIds"],
        "input_fingerprint": manifest["modelFingerprint"],
        "scoring_config_json": manifest,
        "price_policy": "excluded",
        "treatment_policy": "disabled_v1",
        "energy_policy": "neutral_v1",
        "hit_eligibility_policy": "independent",
        "diagnostics_json": {
            "publicationBoundary": "staged_not_current",
            "baseModelVersion": V7_VERSION,
            "explicitSourceAuthority": manifest["sourceAuthority"],
        },
    }).execute().data[0]
    run_id = str(run["id"])

    client.table("pokemon_collector_appeal_model_run_sources").insert([
        {"model_run_id": run_id, "source_run_id": source_id, "source_position": position}
        for position, source_id in enumerate(manifest["sourceRunIds"], 1)
    ]).execute()

    cards, drows, arows = persistence_rows(built, run_id)
    for table, rows in zip(
        ("pokemon_card_collector_appeal_scores", "pokemon_set_collector_desirability_scores", "pokemon_set_collector_appeal_scores"),
        (cards, drows, arows),
    ):
        for index in range(0, len(rows), 100):
            client.table(table).insert(rows[index:index + 100]).execute()

    eligible_set_ids = [
        row["set_id"] for row in arows
        if row.get("score_status") == "scored" and row.get("collector_appeal_score") is not None
    ]
    component_rows = build_component_ranking_rows(cards, run_id, eligible_set_ids=eligible_set_ids)
    client.rpc("replace_pokemon_set_collector_component_rankings", {
        "p_model_run_id": run_id,
        "p_rows": component_rows,
    }).execute()

    card_rank_rows = build_card_collector_ranking_rows(cards, run_id)
    for index in range(0, len(card_rank_rows), 100):
        client.table("pokemon_card_collector_appeal_rankings").insert(card_rank_rows[index:index + 100]).execute()
    client.rpc("hydrate_pokemon_card_collector_appeal_rankings", {"p_model_run_id": run_id}).execute()

    validation = client.rpc("validate_pokemon_collector_appeal_model_run", {
        "p_model_run_id": run_id,
        "p_diagnostics": {
            "builder": "build_pokemon_collector_appeal_v8_anchor25.py",
            "baseModelVersion": V7_VERSION,
            "trainerCrossDomainCalibrationAlpha": ALPHA,
            "formulaFingerprint": manifest["formulaFingerprint"],
        },
    }).execute().data
    if not validation or validation.get("passed") is not True:
        raise RuntimeError("Collector V8 model validation failed")
    return run_id, validation, True


def load_v7_source_authority(client: Any) -> dict[str, str]:
    current = (
        client.table("pokemon_collector_appeal_current")
        .select("model_run_id,model_version")
        .eq("scope", "pokemon").single().execute().data
    )
    if not current or current.get("model_version") != V7_VERSION:
        raise RuntimeError("V8_BASELINE_REQUIRES_CURRENT_V7")
    run = (
        client.table("pokemon_collector_appeal_model_runs")
        .select("source_run_ids,scoring_config_json")
        .eq("id", current["model_run_id"]).single().execute().data
    )
    manifest = run.get("scoring_config_json") or {}
    authority = manifest.get("sourceAuthority")
    if authority:
        return {str(k): str(v) for k, v in authority.items()}
    ids = list(run.get("source_run_ids") or [])
    if len(ids) != 6:
        raise RuntimeError("current V7 run lacks six-source authority")
    return dict(zip(
        ("pokemonTrends", "trainer12m", "trainer5y", "playability", "artist12m", "artist5y"),
        map(str, ids),
    ))


def summary(built: Mapping[str, Any]) -> dict[str, Any]:
    sets = built["sets"]
    deltas = [float(row["collector_delta"]) for row in sets if row.get("collector_delta") is not None]
    f_changes = [
        row for row in sets
        if (row.get("entering_cards") or row.get("leaving_cards"))
        or (row.get("F_delta") is not None and abs(float(row["F_delta"])) > 1e-12)
    ]
    return {
        "modelVersion": MODEL_VERSION,
        "manifest": built["manifest"],
        "counts": {
            "cards": len(built["cards"]),
            "sets": len(sets),
            "scoredSets": sum(row.get("collector_appeal") is not None for row in sets),
            "unavailableSets": sum(row.get("collector_appeal") is None for row in sets),
        },
        "setDelta": {
            "mean": float(np.mean(deltas)) if deltas else None,
            "median": float(np.median(deltas)) if deltas else None,
            "maxGain": max(deltas) if deltas else None,
            "maxLoss": min(deltas) if deltas else None,
            "frequencyOrThresholdMembershipChanges": len(f_changes),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-stage", action="store_true")
    parser.add_argument("--live-rebuild", action="store_true",
                        help="Use current catalog membership through the V7 builder. Default is the exact frozen V7 cutover cohort.")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--as-of-date", default=date.today().isoformat())
    args = parser.parse_args()

    client = None
    authority = None
    # Exact frozen-cutover dry-run is deliberately offline. Live access is
    # required only for a live rebuild or an explicit staged write.
    if args.live_rebuild or args.write_stage:
        load_dotenv(ROOT / "backend/.env", override=False)
        client = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SERVICE_ROLE_KEY"],
            options=ClientOptions(postgrest_client_timeout=90),
        )
        authority = load_v7_source_authority(client)

    if args.live_rebuild:
        if client is None or authority is None:
            raise RuntimeError("V8_LIVE_REBUILD_REQUIRES_CURRENT_V7_AUTHORITY")
        built = build(
            client,
            pokemon_trends_source_run_id=authority["pokemonTrends"],
            trainer_12m_source_run_id=authority["trainer12m"],
            trainer_5y_source_run_id=authority["trainer5y"],
            playability_source_run_id=authority["playability"],
            artist_12m_source_run_id=authority["artist12m"],
            artist_5y_source_run_id=authority["artist5y"],
        )
    else:
        built = build_frozen_cutover()
        if authority is not None and built["manifest"]["sourceAuthority"] != authority:
            raise RuntimeError("V8_FROZEN_CUTOVER_SOURCE_AUTHORITY_NO_LONGER_MATCHES_CURRENT_V7")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(built, indent=2, ensure_ascii=False), encoding="utf-8")

    run_id = validation = None
    created = False
    if args.write_stage:
        if client is None:
            raise RuntimeError("V8_WRITE_STAGE_REQUIRES_DATABASE_CLIENT")
        run_id, validation, created = persist_built_model(client, built, as_of_date=args.as_of_date)

    print(json.dumps({
        "mode": "write-stage" if args.write_stage else "dry-run",
        "modelRunId": run_id,
        "modelCreated": created,
        "validation": validation,
        **summary(built),
    }, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
