"""Build the price-independent candidate pair manifest for Treatment Direct Preference V1.

Research only. Uses canonical card identity, frozen 2026-09-29 simulation authority,
and frozen Collector V7 Subject/Playability controls. It does not read card prices,
PkmnPrices history, V2 effect magnitudes, or market rankings.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

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
EDGES = ((SIR, DOUBLE), (SIR, ULTRA), (ULTRA, DOUBLE))


def stable_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _chunks(values: list[str], size: int = 100):
    for start in range(0, len(values), size):
        yield values[start:start + size]


def build_manifest(db: Any, market_date: str) -> dict[str, Any]:
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
        raise RuntimeError("no Set simulation authority")

    set_rows: list[dict[str, Any]] = []
    for chunk in _chunks(sorted(run_by_set)):
        set_rows += list(
            db.table("sets").select("id,name,era_id").in_("id", chunk).execute().data
            or []
        )
    set_meta = {str(row["id"]): dict(row) for row in set_rows}
    era_ids = sorted({str(row["era_id"]) for row in set_rows if row.get("era_id")})
    eras: dict[str, str] = {}
    for chunk in _chunks(era_ids):
        rows = (
            db.table("eras").select("id,name").in_("id", chunk).execute().data
            or []
        )
        eras.update({str(row["id"]): str(row["name"]) for row in rows})

    cards: list[dict[str, Any]] = []
    for chunk in _chunks(sorted(run_by_set)):
        cards += _paged(
            lambda chunk=chunk: db.table("pokemon_canonical_cards")
            .select(
                "id,set_id,pokemon_tcg_api_card_id,name,number,rarity,"
                "image_small_url,image_large_url"
            )
            .in_("set_id", chunk)
        )
    cards = [
        dict(row)
        for row in cards
        if str(row.get("rarity") or "").casefold() in TREATMENTS
        and row.get("pokemon_tcg_api_card_id")
    ]

    subjects = _subject_keys(db, [str(row["id"]) for row in cards])
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in cards:
        cid = str(row["id"])
        subject = subjects.get(cid)
        if subject:
            grouped[(str(row["set_id"]), subject)].append(row)

    raw_triads: list[dict[str, Any]] = []
    for (set_id, subject_key), group in grouped.items():
        by_rarity = {str(row["rarity"]).casefold(): row for row in group}
        if set(by_rarity) != TREATMENTS:
            continue
        sm = set_meta[set_id]
        raw_triads.append({
            "set_id": set_id,
            "set_name": str(sm["name"]),
            "era_name": eras.get(str(sm.get("era_id")), "Unknown"),
            "subject_key": subject_key,
            "cards": [
                by_rarity[DOUBLE.casefold()],
                by_rarity[ULTRA.casefold()],
                by_rarity[SIR.casefold()],
            ],
        })

    api_ids = sorted({
        str(card["pokemon_tcg_api_card_id"])
        for triad in raw_triads for card in triad["cards"]
    })
    legacy: list[dict[str, Any]] = []
    for chunk in _chunks(api_ids):
        legacy += list(
            db.table("cards").select("id,pokemon_tcg_api_id")
            .in_("pokemon_tcg_api_id", chunk).execute().data or []
        )
    legacy_by_api = {
        str(row["pokemon_tcg_api_id"]): str(row["id"]) for row in legacy
    }

    resolved: list[dict[str, Any]] = []
    resolution_exclusions: list[dict[str, Any]] = []
    for triad in raw_triads:
        run_id = run_by_set[triad["set_id"]]
        out_cards: list[dict[str, Any]] = []
        reason: str | None = None
        for card in triad["cards"]:
            legacy_id = legacy_by_api.get(str(card["pokemon_tcg_api_card_id"]))
            if not legacy_id:
                reason = "LEGACY_ID_MISSING"
                break
            sims = (
                db.table("simulation_input_cards")
                .select("card_variant_id")
                .eq("calculation_run_id", run_id)
                .eq("card_id", legacy_id)
                .execute().data or []
            )
            if len(sims) != 1:
                reason = f"SIM_VARIANT_COUNT_{len(sims)}"
                break
            pulls = (
                db.table("simulation_card_variant_pull_rates")
                .select("modeled_probability")
                .eq("calculation_run_id", run_id)
                .eq("card_variant_id", str(sims[0]["card_variant_id"]))
                .execute().data or []
            )
            if len(pulls) != 1 or not pulls[0].get("modeled_probability"):
                reason = f"PULL_AUTHORITY_COUNT_{len(pulls)}"
                break
            if not card.get("image_large_url"):
                reason = "IMAGE_LARGE_MISSING"
                break
            out_cards.append({
                "canonical_card_id": str(card["id"]),
                "card_name": str(card["name"]),
                "number": str(card["number"]),
                "rarity": str(card["rarity"]),
                "image_small_url": card.get("image_small_url"),
                "image_large_url": card.get("image_large_url"),
                "modeled_probability": float(pulls[0]["modeled_probability"]),
            })
        if reason:
            resolution_exclusions.append({
                "set_name": triad["set_name"],
                "subject_key": triad["subject_key"],
                "reason": reason,
            })
            continue
        resolved.append({**{k:v for k,v in triad.items() if k != "cards"}, "cards": out_cards})

    card_ids = sorted({
        card["canonical_card_id"] for triad in resolved for card in triad["cards"]
    })
    controls = load_controls(db, card_ids)

    eligible: list[dict[str, Any]] = []
    control_exclusions: list[dict[str, Any]] = []
    for triad in resolved:
        by = {card["rarity"]: card for card in triad["cards"]}
        ids = [by[t]["canonical_card_id"] for t in (DOUBLE, ULTRA, SIR)]
        subject_vals = [controls[cid]["subject"] for cid in ids]
        play_vals = [controls[cid]["playability"] for cid in ids]
        reasons: list[str] = []
        if max(subject_vals) - min(subject_vals) > 1e-9:
            reasons.append("SUBJECT_CONTROL_MISMATCH")
        if max(play_vals) - min(play_vals) > 1e-9:
            reasons.append("PLAYABILITY_CONTROL_MISMATCH")
        if reasons:
            control_exclusions.append({
                "set_name": triad["set_name"],
                "subject_key": triad["subject_key"],
                "reasons": reasons,
            })
            continue
        eligible.append(triad)

    pairs: list[dict[str, Any]] = []
    for triad in eligible:
        by = {card["rarity"]: card for card in triad["cards"]}
        for treatment_a, treatment_b in EDGES:
            a = by[treatment_a]
            b = by[treatment_b]
            payload = {
                "study_version": "treatment_direct_preference_v1",
                "set_id": triad["set_id"],
                "set_name": triad["set_name"],
                "era_name": triad["era_name"],
                "subject_key": triad["subject_key"],
                "treatment_a": treatment_a,
                "treatment_b": treatment_b,
                "card_a_id": a["canonical_card_id"],
                "card_a_name": a["card_name"],
                "card_a_number": a["number"],
                "card_a_image_large_url": a["image_large_url"],
                "card_b_id": b["canonical_card_id"],
                "card_b_name": b["card_name"],
                "card_b_number": b["number"],
                "card_b_image_large_url": b["image_large_url"],
            }
            payload["underlying_pair_id"] = stable_hash(payload)[:24]
            pairs.append(payload)

    pairs.sort(key=lambda x: (
        x["era_name"], x["set_name"], x["subject_key"],
        x["treatment_a"], x["treatment_b"]
    ))

    edge_counts = Counter(f"{p['treatment_a']}__{p['treatment_b']}" for p in pairs)
    era_counts = Counter(p["era_name"] for p in pairs)
    subject_counts = Counter(p["subject_key"] for p in pairs)
    set_counts = Counter(p["set_name"] for p in pairs)
    n_pairs = len(pairs)
    max_subject = max(subject_counts.values()) if subject_counts else 0
    max_subject_share = max_subject / n_pairs if n_pairs else 0.0

    per_edge_subject_share: dict[str, float] = {}
    for edge in sorted(edge_counts):
        edge_pairs = [
            p for p in pairs
            if f"{p['treatment_a']}__{p['treatment_b']}" == edge
        ]
        counts = Counter(p["subject_key"] for p in edge_pairs)
        per_edge_subject_share[edge] = (
            max(counts.values()) / len(edge_pairs) if edge_pairs else 0.0
        )

    manifest_core = {
        "study_version": "treatment_direct_preference_v1",
        "market_date_authority": market_date,
        "pair_selection_price_inputs": 0,
        "provider_calls": 0,
        "production_writes": 0,
        "eligible_triads": len(eligible),
        "pair_count": n_pairs,
        "edge_counts": dict(edge_counts),
        "era_counts": dict(era_counts),
        "set_counts": dict(set_counts),
        "unique_subjects": len(subject_counts),
        "maximum_subject_pair_share": max_subject_share,
        "maximum_subject_pair_share_by_edge": per_edge_subject_share,
        "subject_concentration_gate_le_10pct": (
            max_subject_share <= 0.10
            and all(v <= 0.10 for v in per_edge_subject_share.values())
        ),
        "resolution_exclusions": resolution_exclusions,
        "control_exclusions": control_exclusions,
        "pairs": pairs,
    }
    manifest_core["manifest_fingerprint"] = stable_hash(manifest_core["pairs"])
    return manifest_core


def render(result: dict[str, Any]) -> str:
    lines = [
        "# Treatment Direct Preference V1 — Candidate Pair Manifest",
        "",
        "Selection used market-price outcomes: **NO**.",
        "PkmnPrices calls: **ZERO**.",
        "Production writes: **ZERO**.",
        "",
        f"- Eligible complete triads: **{result['eligible_triads']}**",
        f"- Pairwise comparisons: **{result['pair_count']}**",
        f"- Unique Subjects: **{result['unique_subjects']}**",
        f"- Maximum Subject share: **{100*result['maximum_subject_pair_share']:.2f}%**",
        f"- Subject concentration gate <=10%: **{'PASS' if result['subject_concentration_gate_le_10pct'] else 'FAIL'}**",
        f"- Manifest fingerprint: `{result['manifest_fingerprint']}`",
        "",
        "## Pair edges",
        "",
    ]
    for edge, count in sorted(result["edge_counts"].items()):
        lines.append(f"- {edge}: **{count} pairs**")
    lines += ["", "## Era coverage", ""]
    for era, count in sorted(result["era_counts"].items()):
        lines.append(f"- {era}: **{count} comparisons**")
    lines += [
        "",
        "No pair was selected using V2 price direction, price magnitude, rarity market rank, or PkmnPrices evidence.",
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

    result = build_manifest(supabase, args.market_date)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(render(result), encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k != "pairs"}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
