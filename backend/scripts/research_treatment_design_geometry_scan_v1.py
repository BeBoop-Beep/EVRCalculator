"""Price-blind Treatment design-geometry feasibility scan.

Research only. Uses canonical identity, exact simulation pull probabilities and
frozen Collector V7 control rows. It never reads historical card prices and
never calls PkmnPrices.

Purpose: determine whether broader DR/UR/SIR Set-relative cohorts provide
independent scarcity support before any new outcome collection is authorized.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.scripts.research_treatment_set_relative_expansion_panel_v2 import (
    _paged,
    _subject_keys,
)
from backend.scripts.research_treatment_set_relative_hierarchy_v2 import (
    DOUBLE,
    ULTRA,
    SIR,
    load_controls,
)

MARKET_DATE = "2026-09-29"
TREATMENTS = {DOUBLE.casefold(), ULTRA.casefold(), SIR.casefold()}


def _chunks(values: list[str], size: int = 100):
    for start in range(0, len(values), size):
        yield values[start:start + size]


def _col_normalized_condition(x: np.ndarray) -> float:
    z = x.copy()
    for j in range(z.shape[1]):
        norm = float(np.linalg.norm(z[:, j]))
        if norm > 0:
            z[:, j] /= norm
    return float(np.linalg.cond(z))


def _geometry(triads: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = defaultdict(int)
    for triad in triads:
        counts[str(triad["set_name"])] += 1
    set_order = sorted(counts)
    width = 2 * len(set_order)

    z_rows: list[list[float]] = []
    scarcity: list[float] = []
    artist: list[float] = []
    edge_rows: list[dict[str, Any]] = []

    for triad in triads:
        by = {str(c["rarity"]): c for c in triad["cards"]}
        for high, low in ((ULTRA, DOUBLE), (SIR, DOUBLE), (SIR, ULTRA)):
            vector = [0.0] * width
            base = 2 * set_order.index(str(triad["set_name"]))

            def idx(treatment: str) -> int | None:
                if treatment == ULTRA:
                    return base
                if treatment == SIR:
                    return base + 1
                return None

            hi = idx(high)
            lo = idx(low)
            if hi is not None:
                vector[hi] += 1.0
            if lo is not None:
                vector[lo] -= 1.0

            high_card = by[high]
            low_card = by[low]
            sc = math.log(
                float(low_card["modeled_probability"])
                / float(high_card["modeled_probability"])
            )
            ar = (
                float(high_card["artist"])
                - float(low_card["artist"])
            ) / 100.0
            z_rows.append(vector)
            scarcity.append(sc)
            artist.append(ar)
            edge_rows.append({
                "set_name": str(triad["set_name"]),
                "subject_key": str(triad["subject_key"]),
                "high": high,
                "low": low,
                "scarcity_log_ratio": sc,
                "artist_delta_scaled": ar,
            })

    if not z_rows:
        return {"sets": 0, "triads": 0, "edges": 0}

    z = np.asarray(z_rows, dtype=float)
    s = np.asarray(scarcity, dtype=float)
    a = np.asarray(artist, dtype=float)

    scarcity_fit = np.linalg.lstsq(z, s, rcond=None)[0]
    scarcity_resid = s - z @ scarcity_fit
    ss_total = float(np.sum((s - np.mean(s)) ** 2))
    ss_resid = float(np.sum(scarcity_resid ** 2))
    scarcity_r2 = 1.0 - ss_resid / ss_total if ss_total > 0 else 1.0

    x_sc = np.column_stack([z, s])
    x_full = np.column_stack([z, s, a])

    by_set_edge: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in edge_rows:
        key = f"{row['high']}__{row['low']}"
        by_set_edge[row["set_name"]][key].append(float(row["scarcity_log_ratio"]))

    set_support = []
    for set_name in set_order:
        edge_stats = {}
        for edge_key, values in sorted(by_set_edge[set_name].items()):
            edge_stats[edge_key] = {
                "n": len(values),
                "unique": len({round(v, 12) for v in values}),
                "sd": float(np.std(values)),
                "min": min(values),
                "max": max(values),
                "range": max(values) - min(values),
            }
        set_support.append({
            "set_name": set_name,
            "triads": counts[set_name],
            "edges": edge_stats,
        })

    singular = np.linalg.svd(x_sc, compute_uv=False)

    return {
        "sets": len(set_order),
        "triads": len(triads),
        "edges": len(edge_rows),
        "parameters_set_treatment": width,
        "rank_set_treatment": int(np.linalg.matrix_rank(z)),
        "condition_set_treatment": float(np.linalg.cond(z)),
        "rank_with_scarcity": int(np.linalg.matrix_rank(x_sc)),
        "condition_with_scarcity": float(np.linalg.cond(x_sc)),
        "condition_with_scarcity_column_normalized": _col_normalized_condition(x_sc),
        "rank_full_with_artist": int(np.linalg.matrix_rank(x_full)),
        "condition_full_with_artist": float(np.linalg.cond(x_full)),
        "condition_full_column_normalized": _col_normalized_condition(x_full),
        "scarcity_sd": float(np.std(s)),
        "scarcity_min": float(np.min(s)),
        "scarcity_max": float(np.max(s)),
        "scarcity_r2_from_set_treatment": scarcity_r2,
        "scarcity_residual_sd": float(np.std(scarcity_resid)),
        "scarcity_residual_max_abs": float(np.max(np.abs(scarcity_resid))),
        "scarcity_residual_fraction_sd": (
            float(np.std(scarcity_resid)) / float(np.std(s))
            if float(np.std(s)) > 0
            else 0.0
        ),
        "singular_value_max": float(singular[0]),
        "singular_value_min": float(singular[-1]),
        "set_support": set_support,
    }


def build_design(db: Any, market_date: str) -> dict[str, Any]:
    runs = _paged(
        lambda: db.table("calculation_runs")
        .select("id,target_id,created_at")
        .eq("market_date", market_date)
        .eq("target_type", "set")
        .order("created_at", desc=True)
    )
    run_by_set: dict[str, str] = {}
    for row in runs:
        run_by_set.setdefault(str(row["target_id"]), str(row["id"]))
    if not run_by_set:
        raise RuntimeError("no Set simulation authority for market date")

    set_rows = []
    for chunk in _chunks(sorted(run_by_set)):
        set_rows.extend(
            db.table("sets")
            .select("id,name")
            .in_("id", chunk)
            .execute().data
            or []
        )
    set_name = {str(r["id"]): str(r["name"]) for r in set_rows}

    cards = []
    for chunk in _chunks(sorted(run_by_set)):
        cards.extend(
            _paged(
                lambda chunk=chunk: db.table("pokemon_canonical_cards")
                .select(
                    "id,set_id,name,number,printed_number,rarity,"
                    "pokemon_tcg_api_card_id"
                )
                .in_("set_id", chunk)
            )
        )
    cards = [
        dict(row)
        for row in cards
        if str(row.get("rarity") or "").casefold() in TREATMENTS
        and row.get("pokemon_tcg_api_card_id")
    ]
    subjects = _subject_keys(db, [str(row["id"]) for row in cards])
    for row in cards:
        row["subject_key"] = subjects.get(str(row["id"]))
        row["set_name"] = set_name.get(str(row["set_id"]))

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in cards:
        if row.get("subject_key") and row.get("set_name"):
            grouped[(str(row["set_id"]), str(row["subject_key"]))].append(row)

    raw_triads = []
    for (set_id, subject_key), group in grouped.items():
        by = {str(row["rarity"]).casefold(): row for row in group}
        if set(by) != TREATMENTS:
            continue
        raw_triads.append({
            "set_id": set_id,
            "set_name": set_name[set_id],
            "subject_key": subject_key,
            "cards": [
                by[DOUBLE.casefold()],
                by[ULTRA.casefold()],
                by[SIR.casefold()],
            ],
        })

    api_ids = sorted({
        str(card["pokemon_tcg_api_card_id"])
        for triad in raw_triads
        for card in triad["cards"]
    })
    legacy = []
    for chunk in _chunks(api_ids):
        legacy.extend(
            db.table("cards")
            .select("id,pokemon_tcg_api_id")
            .in_("pokemon_tcg_api_id", chunk)
            .execute().data
            or []
        )
    legacy_by_api = {
        str(row["pokemon_tcg_api_id"]): str(row["id"])
        for row in legacy
    }

    resolved_triads = []
    resolution_failures = []
    for triad in raw_triads:
        run_id = run_by_set[str(triad["set_id"])]
        out_cards = []
        failed = None
        for card in triad["cards"]:
            legacy_id = legacy_by_api.get(str(card["pokemon_tcg_api_card_id"]))
            if not legacy_id:
                failed = "LEGACY_ID_MISSING"
                break
            sims = (
                db.table("simulation_input_cards")
                .select("card_variant_id,effective_pull_rate")
                .eq("calculation_run_id", run_id)
                .eq("card_id", legacy_id)
                .execute().data
                or []
            )
            if len(sims) != 1:
                failed = f"SIM_VARIANT_COUNT_{len(sims)}"
                break
            variant_id = str(sims[0]["card_variant_id"])
            pulls = (
                db.table("simulation_card_variant_pull_rates")
                .select("modeled_probability,status")
                .eq("calculation_run_id", run_id)
                .eq("card_variant_id", variant_id)
                .execute().data
                or []
            )
            if len(pulls) != 1 or not pulls[0].get("modeled_probability"):
                failed = f"PULL_AUTHORITY_COUNT_{len(pulls)}"
                break
            out_cards.append({
                "canonical_card_id": str(card["id"]),
                "rarity": str(card["rarity"]),
                "modeled_probability": float(pulls[0]["modeled_probability"]),
            })
        if failed:
            resolution_failures.append({
                "set_name": triad["set_name"],
                "subject_key": triad["subject_key"],
                "reason": failed,
            })
            continue
        resolved_triads.append({
            "set_name": triad["set_name"],
            "subject_key": triad["subject_key"],
            "cards": out_cards,
        })

    all_card_ids = sorted({
        card["canonical_card_id"]
        for triad in resolved_triads
        for card in triad["cards"]
    })
    controls = load_controls(db, all_card_ids)

    eligible = []
    control_exclusions = []
    for triad in resolved_triads:
        by = {card["rarity"]: dict(card) for card in triad["cards"]}
        ids = [by[t]["canonical_card_id"] for t in (DOUBLE, ULTRA, SIR)]
        subject = [controls[cid]["subject"] for cid in ids]
        playability = [controls[cid]["playability"] for cid in ids]
        reasons = []
        if max(subject) - min(subject) > 1e-9:
            reasons.append("SUBJECT_CONTROL_MISMATCH")
        if max(playability) - min(playability) > 1e-9:
            reasons.append("PLAYABILITY_CONTROL_MISMATCH")
        if reasons:
            control_exclusions.append({
                "set_name": triad["set_name"],
                "subject_key": triad["subject_key"],
                "reasons": reasons,
            })
            continue
        for treatment in (DOUBLE, ULTRA, SIR):
            cid = by[treatment]["canonical_card_id"]
            by[treatment]["artist"] = controls[cid]["artist"]
        eligible.append({
            "set_name": triad["set_name"],
            "subject_key": triad["subject_key"],
            "cards": [by[DOUBLE], by[ULTRA], by[SIR]],
        })

    by_set: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for triad in eligible:
        by_set[str(triad["set_name"])].append(triad)

    cohorts = {}
    for min_triads in (1, 2, 3, 4, 5, 6):
        selected = [
            triad
            for set_name_, rows in by_set.items()
            if len(rows) >= min_triads
            for triad in rows
        ]
        cohorts[f"sets_with_at_least_{min_triads}_triads"] = _geometry(selected)

    return {
        "study_id": "treatment_design_geometry_scan_v1",
        "market_date": market_date,
        "price_outcomes_read": 0,
        "provider_calls": 0,
        "production_writes": 0,
        "simulation_set_count": len(run_by_set),
        "raw_complete_triads": len(raw_triads),
        "simulation_resolved_triads": len(resolved_triads),
        "control_eligible_triads": len(eligible),
        "resolution_failures": resolution_failures,
        "control_exclusions": control_exclusions,
        "eligible_by_set": {
            set_name_: len(rows)
            for set_name_, rows in sorted(by_set.items())
        },
        "cohorts": cohorts,
    }


def render(result: dict[str, Any]) -> str:
    lines = [
        "# Treatment Design Geometry Scan V1",
        "",
        "Price outcomes read: **ZERO**.",
        "PkmnPrices calls: **ZERO**.",
        "Production writes: **ZERO**.",
        "",
        f"- Simulation Sets: **{result['simulation_set_count']}**",
        f"- Raw complete DR/UR/SIR triads: **{result['raw_complete_triads']}**",
        f"- Simulation-resolved triads: **{result['simulation_resolved_triads']}**",
        f"- Control-eligible triads: **{result['control_eligible_triads']}**",
        "",
        "## Design-only cohort geometry",
        "",
        "| Cohort | Sets | Triads | Scarcity R² from Set×Treatment | Residual scarcity SD | Cond + scarcity | Cond normalized | Cond full |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, row in result["cohorts"].items():
        if not row.get("triads"):
            continue
        lines.append(
            f"| {name} | {row['sets']} | {row['triads']} | "
            f"{row['scarcity_r2_from_set_treatment']:.6f} | "
            f"{row['scarcity_residual_sd']:.5f} | "
            f"{row['condition_with_scarcity']:.2f} | "
            f"{row['condition_with_scarcity_column_normalized']:.2f} | "
            f"{row['condition_full_with_artist']:.2f} |"
        )
    lines += [
        "",
        "These are predictor-geometry diagnostics only. No price outcome was used to choose a cohort.",
        "",
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--market-date", default=MARKET_DATE)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    args = p.parse_args(argv)

    load_dotenv(ROOT / "backend/.env", override=False)
    from backend.db.clients.supabase_client import supabase

    result = build_design(supabase, args.market_date)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(render(result), encoding="utf-8")
    print(json.dumps({
        "study_id": result["study_id"],
        "simulation_set_count": result["simulation_set_count"],
        "raw_complete_triads": result["raw_complete_triads"],
        "simulation_resolved_triads": result["simulation_resolved_triads"],
        "control_eligible_triads": result["control_eligible_triads"],
        "cohorts": {
            key: {
                k: value
                for k, value in row.items()
                if k != "set_support"
            }
            for key, row in result["cohorts"].items()
        },
        "price_outcomes_read": 0,
        "provider_calls": 0,
        "production_writes": 0,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
