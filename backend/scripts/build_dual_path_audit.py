"""Dual-Path Depth real-data audit + CA6/CA7 comparison (READ-ONLY).

Answers, on production data and not on synthetic fixtures:

  1. Do Ascended Heroes' Dragonite and Gengar receive Dual-Path credit, and via
     which exact cards?
  2. What does the Dual-Path ranking look like across every covered set, and
     does it match a real reading of those products?
  3. Do the structural safeguards hold on real data (no duplicate inflation, no
     same-card false dual path)?
  4. CA6 (discount) vs CA7 (bounded bonus, pre-registered lambda grid), compared
     on CONSTRUCT grounds.
  5. What is Collector Appeal's effective influence on RIP at its fixed 10%
     weight?

WRITES NOTHING TO THE DATABASE. Emits JSON + CSVs under docs/research/ only.

Market price is loaded for ONE purpose: to report descriptive diagnostics in the
output. It never enters the construction, normalization, weighting, or selection
of any candidate. No lambda and no weight anywhere here is chosen by looking at
a market outcome.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.calculations.utils.rarity_classification import normalize_rarity_key  # noqa: E402
from backend.db.clients.supabase_client import public_read_client  # noqa: E402
from backend.desirability.card_appeal import get_treatment_score  # noqa: E402
from backend.desirability.collector_appeal import (  # noqa: E402
    CA6_DUAL_PATH_FLOOR,
    CA6_DUAL_PATH_GAIN,
    CA7_LAMBDA_GRID,
    bounded_bonus_appeal,
    compute_dual_path_depth,
    dual_path_utility,
    subject_dual_path,
)
from backend.desirability.opening_appeal import (  # noqa: E402
    EASY_PROBABILITY,
    ELITE_PROBABILITY,
    access_transform,
    build_subjects,
    scarcity_transform,
)
from backend.desirability.product_support import classify_product_support  # noqa: E402
from backend.desirability.rarity_buckets import HIT_BUCKETS, classify_rarity  # noqa: E402
from backend.desirability.scoring_config import DEFAULT_RIP_WEIGHTS  # noqa: E402
from backend.desirability.universal_set_desirability import (  # noqa: E402
    COVERAGE_FULL,
    assess_desirability_coverage,
    compute_universal_set_desirability,
)
from backend.desirability.weighted_rip import compute_weighted_rip, spearman  # noqa: E402
from backend.scripts.build_opening_appeal_study import (  # noqa: E402
    load_appeal_by_card,
    load_cards,
    load_latest_v2_rows,
    load_pull_rate_model,
    load_simulation_rows,
)

logger = logging.getLogger(__name__)

DOCS = Path(__file__).resolve().parents[2] / "docs" / "research"
TABLES = DOCS / "collector_appeal_tables"
AUDIT_VERSION = "dual_path_audit_v1"

ANCHOR_SETS = ("ascendedHeroes",)
ANCHOR_SUBJECTS = ("Dragonite", "Gengar")


def _as_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _round(value: Any, digits: int = 6) -> Optional[float]:
    parsed = _as_float(value)
    return round(parsed, digits) if parsed is not None else None


# ---------------------------------------------------------------------------
# Card-level trace
# ---------------------------------------------------------------------------

def build_card_trace(
    *,
    set_cards: Sequence[Dict[str, Any]],
    rarity_model: Dict[str, Dict[str, Any]],
    appeal_by_card: Dict[str, Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Every card with its eligibility verdict, plus the eligible subset.

    The full trace (including REJECTED cards and why) is the point: an audit that
    only shows the cards that made it through cannot explain a subject's score.
    """
    trace: List[Dict[str, Any]] = []
    eligible: List[Dict[str, Any]] = []
    for card in set_cards:
        card_id = str(card.get("id") or "")
        classification = classify_rarity(card.get("rarity"))
        is_hit = classification.bucket in HIT_BUCKETS
        appeal_row = appeal_by_card.get(card_id)
        model = rarity_model.get(classification.normalized_key)

        reasons: List[str] = []
        if not is_hit:
            reasons.append(f"not_hit_eligible(bucket={classification.bucket})")
        if appeal_row is None:
            reasons.append("no_subject_link")
        if model is None:
            reasons.append(f"no_pull_model(rarity_key={classification.normalized_key})")

        probability = model["probability"] if model else None
        entry = {
            "card_name": card.get("name"),
            "number": card.get("number"),
            "rarity": card.get("rarity"),
            "rarity_bucket": classification.bucket,
            "rarity_key": classification.normalized_key,
            "treatment_prestige": _round(get_treatment_score(card.get("rarity")) / 100.0, 4),
            "hit_eligible": is_hit,
            "subject_name": (appeal_row or {}).get("primary_species"),
            "subject_demand": _round((appeal_row or {}).get("appeal"), 4),
            "pull_probability": _round(probability, 8),
            "pull_odds_label": (f"1-in-{round(1.0/probability):,}" if probability else None),
            "slot_group": (model or {}).get("slot_group"),
            "access_transform": _round(access_transform(probability), 6),
            "scarcity_transform": _round(scarcity_transform(probability), 6),
            "eligible_for_dual_path": not reasons,
            "excluded_because": ";".join(reasons) or None,
        }
        trace.append(entry)
        if not reasons:
            eligible.append(
                {
                    "subject_key": f"ref:{appeal_row['primary_reference_id']}",
                    "subject_name": appeal_row.get("primary_species"),
                    "subject_demand": appeal_row["appeal"],
                    "pull_probability": min(probability, 1.0),
                    "slot_group": model["slot_group"],
                    "card_name": card.get("name"),
                    "number": card.get("number"),
                    "rarity": card.get("rarity"),
                    "treatment_prestige": get_treatment_score(card.get("rarity")) / 100.0,
                }
            )
    return trace, eligible


def audit_subject(subject: Dict[str, Any], share: Optional[float]) -> Dict[str, Any]:
    """One subject's full Dual-Path derivation, card by card.

    Selection is resolved BY POSITION, not by card name. In Ascended Heroes all
    four Dragonite printings are named "Mega Dragonite ex", so name-matching
    marks every printing as selected and the audit becomes unreadable. This also
    surfaces a real reporting weakness in ``subject_dual_path``, which returns
    only ``card_name`` for its picks and so cannot identify WHICH printing won
    when a subject has same-named variants - noted in the results doc.

    The selection rule below mirrors ``subject_dual_path`` exactly (first strict
    max access = easiest, first strict min access = rarest); the returned
    ``dual_path`` is cross-checked against the production function so this audit
    cannot silently diverge from the metric it is auditing.
    """
    dual = subject_dual_path(subject)
    raw_cards = list(subject.get("cards") or [])
    cards = [
        {
            "card_name": card.get("card_name"),
            "number": card.get("number"),
            "rarity": card.get("rarity"),
            "treatment_prestige": _round(card.get("treatment_prestige"), 4),
            "pull_probability": _round(card.get("pull_probability"), 8),
            "pull_odds_label": (
                f"1-in-{round(1.0 / card['pull_probability']):,}" if card.get("pull_probability") else None
            ),
            "access_transform": _round(access_transform(card.get("pull_probability")), 6),
            "scarcity_transform": _round(scarcity_transform(card.get("pull_probability")), 6),
        }
        for card in raw_cards
    ]

    easiest_index = rarest_index = None
    best = worst = None
    for index, card in enumerate(raw_cards):
        access = access_transform(card.get("pull_probability"))
        if access is None:
            continue
        if best is None or access > best:
            best, easiest_index = access, index
        if worst is None or access < worst:
            worst, rarest_index = access, index

    for index, card in enumerate(cards):
        card["is_selected_easiest"] = index == easiest_index
        card["is_selected_rarest"] = index == rarest_index

    same_card = easiest_index is not None and easiest_index == rarest_index

    # Ties at the elite anchor: several printings clamp to access 0.0 and are
    # then indistinguishable, so "which card is rarest" is decided by iteration
    # order rather than by scarcity. Flagged rather than hidden.
    elite_tie_count = sum(
        1 for card in cards
        if card["access_transform"] is not None and worst is not None
        and abs(card["access_transform"] - worst) < 1e-12
    )

    if dual is not None:
        recomputed = (best or 0.0) * (1.0 - (worst if worst is not None else 0.0))
        assert abs(recomputed - dual["dual_path"]) < 1e-9, (
            f"audit selection diverged from subject_dual_path for {subject.get('subject_name')}"
        )
    return {
        "subject_name": subject.get("subject_name"),
        "subject_key": subject.get("subject_key"),
        "subject_demand": _round(subject.get("subject_demand"), 4),
        "appeal_excess": _round(subject.get("appeal_excess"), 6),
        "demand_share_q_s": _round(share, 6),
        "printing_count": len(cards),
        "cards": sorted(cards, key=lambda row: -(row["access_transform"] or 0.0)),
        "selected_easiest_card": (
            f"{cards[easiest_index]['card_name']} #{cards[easiest_index]['number']} "
            f"({cards[easiest_index]['rarity']})" if easiest_index is not None else None
        ),
        "selected_rarest_card": (
            f"{cards[rarest_index]['card_name']} #{cards[rarest_index]['number']} "
            f"({cards[rarest_index]['rarity']})" if rarest_index is not None else None
        ),
        "reachable_access": (dual or {}).get("reachable_access"),
        "elite_scarcity": (dual or {}).get("elite_scarcity"),
        "dual_path": _round((dual or {}).get("dual_path"), 6),
        "contribution": _round((share or 0.0) * ((dual or {}).get("dual_path") or 0.0), 6),
        "same_card_both_paths": same_card,
        "same_card_ceiling_note": (
            "Easiest and rarest are the SAME card: dual_path = a*(1-a) <= 0.25 by algebra, "
            "so one card cannot imitate a true dual path."
            if same_card
            else None
        ),
        "elite_tie_count": elite_tie_count,
        "elite_tie_note": (
            f"{elite_tie_count} printings tie at the elite anchor (access clamped to "
            f"{round(worst, 4) if worst is not None else None}); which one is reported as "
            "'rarest' is decided by iteration order, not by scarcity. The dual_path VALUE is "
            "unaffected (the tied cards share an access), only the label is ambiguous."
            if elite_tie_count > 1
            else None
        ),
    }


# ---------------------------------------------------------------------------
# Per-set audit
# ---------------------------------------------------------------------------

def audit_set(
    *,
    set_id: str,
    v2_row: Dict[str, Any],
    set_cards: Sequence[Dict[str, Any]],
    rarity_model: Dict[str, Dict[str, Any]],
    appeal_by_card: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    diagnostics = v2_row.get("diagnostics_json") or {}
    coverage_audit = diagnostics.get("coverage_audit") or {}
    link_counts = diagnostics.get("hit_link_category_counts") or {}
    rollups = v2_row.get("subject_rollups_json") or []

    v3 = compute_universal_set_desirability(rollups)
    coverage = assess_desirability_coverage(
        canonical_card_count=coverage_audit.get("canonical_card_count") or diagnostics.get("canonical_cards_seen"),
        hit_eligible_card_count=v2_row.get("hit_eligible_card_count"),
        scored_hit_eligible_card_count=v2_row.get("scored_hit_eligible_card_count"),
        unique_subject_count=v2_row.get("unique_subject_count"),
        unmatched_pokemon_hit_count=link_counts.get("unmatched_pokemon_hit_count"),
        true_missing_link_count=link_counts.get("true_missing_link_count"),
    )
    support = classify_product_support(
        set_canonical_key=v2_row.get("set_canonical_key"), set_name=v2_row.get("set_name")
    )

    trace, eligible_cards = build_card_trace(
        set_cards=set_cards, rarity_model=rarity_model, appeal_by_card=appeal_by_card
    )
    subjects = build_subjects(eligible_cards) if eligible_cards else []
    depth = compute_dual_path_depth(subjects) if subjects else None

    # Recover q_s for the audited subjects from the same helper the metric uses.
    from backend.desirability.factorized_opening_appeal import demand_shares, desirable_subjects

    desirable = desirable_subjects(subjects)
    shares = demand_shares(desirable) if desirable else {}
    subject_audits = [
        audit_subject(subject, shares.get(str(subject.get("subject_key"))))
        for subject in desirable
    ]
    subject_audits.sort(key=lambda row: -(row["contribution"] or 0.0))

    d_raw = v3["score"] if coverage["status"] == COVERAGE_FULL else None
    d_unit = (d_raw / 100.0) if d_raw is not None else None
    p_value = (depth or {}).get("value")

    # Max achievable access for ANY hit rarity in this set: the structural
    # ceiling on every subject's dual_path, and therefore on P itself.
    hit_accesses = [
        row["access_transform"] for row in trace
        if row["hit_eligible"] and row["access_transform"] is not None
    ]
    access_ceiling = max(hit_accesses) if hit_accesses else None

    candidates: Dict[str, Optional[float]] = {}
    if d_unit is not None and p_value is not None:
        utility = dual_path_utility(p_value)
        candidates["CA6_dual_path_utility"] = _round(d_unit * utility, 6) if utility else None
        for lam in CA7_LAMBDA_GRID:
            candidates[f"CA7_bounded_bonus_{int(lam*100)}"] = _round(
                bounded_bonus_appeal(d_unit, p_value, lam), 6
            )
    candidates["CA0_desirability_only"] = _round(d_unit, 6)

    return {
        "set_id": set_id,
        "set_name": v2_row.get("set_name"),
        "set_canonical_key": v2_row.get("set_canonical_key"),
        "product_support_type": support["product_support_type"],
        "supported": support["supported"],
        "desirability_coverage": coverage["status"],
        "roster_desirability_D": d_raw,
        "dual_path_depth_P": _round(p_value, 6),
        "dual_path_available": p_value is not None,
        "covered_demand_share": (depth or {}).get("covered_demand_share"),
        "desirable_subject_count": len(desirable),
        "multi_printing_subject_count": (depth or {}).get("multi_printing_subject_count"),
        "single_printing_subject_count": sum(
            1 for row in subject_audits if row["printing_count"] == 1
        ),
        "hit_access_ceiling": _round(access_ceiling, 6),
        "canonical_card_count": len(set_cards),
        "eligible_card_count": len(eligible_cards),
        "candidates": candidates,
        "subjects": subject_audits,
        "card_trace": trace,
    }


# ---------------------------------------------------------------------------
# Effective RIP influence
# ---------------------------------------------------------------------------

def effective_influence(rows: Sequence[Dict[str, Any]], candidate_key: str) -> Dict[str, Any]:
    """RIP with the candidate as the fourth pillar vs the shipped baseline.

    Reports what a 10% NOMINAL weight actually buys in rank movement, which is
    not the same thing: influence depends on the pillar's dispersion relative to
    the others, not on its weight alone.
    """
    usable = [
        row for row in rows
        if row.get("profit_score") is not None
        and row.get(candidate_key) is not None
        and row.get("baseline_desirability") is not None
    ]
    if len(usable) < 3:
        return {"candidate": candidate_key, "n": len(usable), "insufficient_data": True}

    def _rip(row, desirability):
        return compute_weighted_rip(
            {
                "profit": row.get("profit_score"),
                "safety": row.get("safety_score"),
                "stability": row.get("stability_score"),
                "desirability": desirability,
            }
        ).get("score")

    old_scores = [_rip(row, row["baseline_desirability"]) for row in usable]
    new_scores = [_rip(row, row[candidate_key]) for row in usable]

    def _ranks(scores):
        order = sorted(range(len(scores)), key=lambda i: -(scores[i] or 0.0))
        ranks = [0] * len(scores)
        for rank, index in enumerate(order, start=1):
            ranks[index] = rank
        return ranks

    old_ranks, new_ranks = _ranks(old_scores), _ranks(new_scores)
    deltas = [abs(old_ranks[i] - new_ranks[i]) for i in range(len(usable))]
    score_deltas = [(new_scores[i] or 0) - (old_scores[i] or 0) for i in range(len(usable))]

    movers = sorted(
        (
            {
                "set_name": usable[i]["set_name"],
                "old_rank": old_ranks[i],
                "new_rank": new_ranks[i],
                "rank_delta": old_ranks[i] - new_ranks[i],
                "score_delta": round(score_deltas[i], 4),
            }
            for i in range(len(usable))
        ),
        key=lambda row: -abs(row["rank_delta"]),
    )

    # One-SD marginal influence: how many RIP points a 1-SD move in the pillar
    # buys, at its 10% weight. This is the honest "is 10% meaningful" number.
    pillar_values = [row[candidate_key] for row in usable]
    pillar_sd = statistics.pstdev(pillar_values) if len(pillar_values) > 1 else 0.0
    rip_sd = statistics.pstdev([s for s in new_scores if s is not None])

    weighted_contributions = {
        pillar: statistics.pstdev(
            [(_as_float(row.get(source)) or 0.0) * DEFAULT_RIP_WEIGHTS[pillar] for row in usable]
        )
        for pillar, source in (
            ("profit", "profit_score"),
            ("safety", "safety_score"),
            ("stability", "stability_score"),
        )
    }
    weighted_contributions["desirability"] = pillar_sd * DEFAULT_RIP_WEIGHTS["desirability"]

    return {
        "candidate": candidate_key,
        "n": len(usable),
        "nominal_weight": DEFAULT_RIP_WEIGHTS["desirability"],
        "pillar_sd": round(pillar_sd, 4),
        "rip_sd": round(rip_sd, 4),
        "one_sd_marginal_rip_points": round(pillar_sd * DEFAULT_RIP_WEIGHTS["desirability"], 4),
        "weighted_contribution_sd_by_pillar": {k: round(v, 4) for k, v in weighted_contributions.items()},
        "share_of_weighted_dispersion": round(
            weighted_contributions["desirability"] / sum(weighted_contributions.values()), 4
        ) if sum(weighted_contributions.values()) > 0 else None,
        "max_rank_movement": max(deltas),
        "mean_rank_movement": round(statistics.mean(deltas), 3),
        "median_rank_movement": round(statistics.median(deltas), 3),
        "pct_moving_1_plus": round(100.0 * sum(1 for d in deltas if d >= 1) / len(deltas), 2),
        "pct_moving_3_plus": round(100.0 * sum(1 for d in deltas if d >= 3) / len(deltas), 2),
        "pct_moving_5_plus": round(100.0 * sum(1 for d in deltas if d >= 5) / len(deltas), 2),
        "mean_abs_score_delta": round(statistics.mean([abs(d) for d in score_deltas]), 4),
        "top5_changed": old_ranks[:0] != new_ranks[:0] or sorted(
            [usable[i]["set_name"] for i in range(len(usable)) if old_ranks[i] <= 5]
        ) != sorted([usable[i]["set_name"] for i in range(len(usable)) if new_ranks[i] <= 5]),
        "most_helped": [m for m in movers if m["rank_delta"] > 0][:5],
        "most_harmed": [m for m in movers if m["rank_delta"] < 0][:5],
        "largest_movers": movers[:10],
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit-sets", type=int, default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    load_dotenv()
    client = public_read_client

    logger.info("[dual-path-audit] loading production data (read-only)...")
    v2_rows = load_latest_v2_rows(client)
    pull_model = load_pull_rate_model(client)
    simulation_rows = load_simulation_rows(client)
    logger.info(
        "[dual-path-audit] v2_rows=%s sets_with_pull_model=%s simulated_sets=%s",
        len(v2_rows), len(pull_model), len(simulation_rows),
    )

    # Only sets with a modeled pack can have Dual-Path Depth at all.
    target_ids = [sid for sid in v2_rows if sid in pull_model]
    if args.limit_sets:
        target_ids = target_ids[: args.limit_sets]
    logger.info("[dual-path-audit] auditing %s sets with a pull model", len(target_ids))

    cards = load_cards(client, target_ids)
    cards_by_set: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for card in cards:
        cards_by_set[str(card.get("set_id"))].append(card)
    appeal_by_card = load_appeal_by_card(client, [str(c.get("id")) for c in cards])
    logger.info("[dual-path-audit] cards=%s linked_cards=%s", len(cards), len(appeal_by_card))

    audits: List[Dict[str, Any]] = []
    for set_id in target_ids:
        audits.append(
            audit_set(
                set_id=set_id,
                v2_row=v2_rows[set_id],
                set_cards=cards_by_set.get(set_id, []),
                rarity_model=pull_model.get(set_id) or {},
                appeal_by_card=appeal_by_card,
            )
        )

    covered = [a for a in audits if a["dual_path_available"]]
    covered.sort(key=lambda row: -(row["dual_path_depth_P"] or 0.0))
    for rank, row in enumerate(covered, start=1):
        row["dual_path_rank"] = rank

    # --- effective RIP influence -----------------------------------------
    influence_rows: List[Dict[str, Any]] = []
    for audit in covered:
        sim = simulation_rows.get(audit["set_id"])
        if not sim:
            continue
        entry = {
            "set_name": audit["set_name"],
            "set_id": audit["set_id"],
            "profit_score": _as_float(sim.get("profit_score")),
            "safety_score": _as_float(sim.get("safety_score")),
            "stability_score": _as_float(sim.get("stability_score")),
            "baseline_desirability": audit["roster_desirability_D"],
        }
        for key, value in audit["candidates"].items():
            entry[key] = (value * 100.0) if value is not None else None
        influence_rows.append(entry)

    candidate_keys = ["CA6_dual_path_utility"] + [
        f"CA7_bounded_bonus_{int(lam*100)}" for lam in CA7_LAMBDA_GRID
    ]
    influence = {key: effective_influence(influence_rows, key) for key in candidate_keys}

    # --- anchors ----------------------------------------------------------
    anchors = {}
    for audit in audits:
        if audit["set_canonical_key"] in ANCHOR_SETS:
            anchors[audit["set_canonical_key"]] = {
                "set_name": audit["set_name"],
                "dual_path_depth_P": audit["dual_path_depth_P"],
                "roster_desirability_D": audit["roster_desirability_D"],
                "hit_access_ceiling": audit["hit_access_ceiling"],
                "subjects": [
                    s for s in audit["subjects"]
                    if any(a.lower() in str(s["subject_name"] or "").lower() for a in ANCHOR_SUBJECTS)
                ],
                "anchor_card_trace": [
                    c for c in audit["card_trace"]
                    if any(a.lower() in str(c["subject_name"] or "").lower() for a in ANCHOR_SUBJECTS)
                    or any(a.lower() in str(c["card_name"] or "").lower() for a in ANCHOR_SUBJECTS)
                ],
            }

    # --- distribution -----------------------------------------------------
    p_values = [a["dual_path_depth_P"] for a in covered if a["dual_path_depth_P"] is not None]
    ceilings = [a["hit_access_ceiling"] for a in covered if a["hit_access_ceiling"] is not None]
    distribution = {
        "n": len(p_values),
        "min": round(min(p_values), 6) if p_values else None,
        "max": round(max(p_values), 6) if p_values else None,
        "mean": round(statistics.mean(p_values), 6) if p_values else None,
        "median": round(statistics.median(p_values), 6) if p_values else None,
        "sd": round(statistics.pstdev(p_values), 6) if len(p_values) > 1 else None,
        "hit_access_ceiling_mean": round(statistics.mean(ceilings), 6) if ceilings else None,
        "hit_access_ceiling_max": round(max(ceilings), 6) if ceilings else None,
        "note": (
            "P is bounded above by the set's hit_access_ceiling = max access over hit-eligible "
            "rarities. No hit card approaches the 1-in-10 EASY anchor, so P is structurally "
            "compressed well below 1.0. See the results doc."
        ),
    }

    # --- correlations (descriptive only) ----------------------------------
    sizes = [(a["eligible_card_count"], a["dual_path_depth_P"]) for a in covered if a["dual_path_depth_P"] is not None]
    subj_counts = [(a["desirable_subject_count"], a["dual_path_depth_P"]) for a in covered if a["dual_path_depth_P"] is not None]
    d_vs_p = [(a["roster_desirability_D"], a["dual_path_depth_P"]) for a in covered
              if a["roster_desirability_D"] is not None and a["dual_path_depth_P"] is not None]
    diagnostics = {
        "spearman_P_vs_eligible_card_count": _round(spearman([x for x, _ in sizes], [y for _, y in sizes]), 4),
        "spearman_P_vs_desirable_subject_count": _round(spearman([x for x, _ in subj_counts], [y for _, y in subj_counts]), 4),
        "spearman_P_vs_D": _round(spearman([x for x, _ in d_vs_p], [y for _, y in d_vs_p]), 4),
        "note": "Descriptive only. Nothing here selects a formula or a lambda.",
    }

    report = {
        "version": AUDIT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "anchors": {"easy_probability": EASY_PROBABILITY, "elite_probability": ELITE_PROBABILITY},
        "ca6": {"floor": CA6_DUAL_PATH_FLOOR, "gain": CA6_DUAL_PATH_GAIN},
        "ca7_lambda_grid": list(CA7_LAMBDA_GRID),
        "sets_audited": len(audits),
        "sets_with_dual_path": len(covered),
        "distribution": distribution,
        "diagnostics": diagnostics,
        "ascended_heroes_anchor": anchors,
        "effective_rip_influence": influence,
        "set_rankings": [
            {k: v for k, v in a.items() if k not in {"subjects", "card_trace"}} for a in covered
        ],
    }

    DOCS.mkdir(parents=True, exist_ok=True)
    TABLES.mkdir(parents=True, exist_ok=True)
    (DOCS / "dual_path_audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    _write_csv(
        TABLES / "dual_path_set_rankings.csv",
        [
            {
                "rank": a["dual_path_rank"],
                "set_name": a["set_name"],
                "set_canonical_key": a["set_canonical_key"],
                "roster_desirability_D": a["roster_desirability_D"],
                "dual_path_depth_P": a["dual_path_depth_P"],
                "hit_access_ceiling": a["hit_access_ceiling"],
                "desirable_subject_count": a["desirable_subject_count"],
                "multi_printing_subject_count": a["multi_printing_subject_count"],
                "single_printing_subject_count": a["single_printing_subject_count"],
                "eligible_card_count": a["eligible_card_count"],
                "covered_demand_share": a["covered_demand_share"],
                **{k: v for k, v in a["candidates"].items()},
            }
            for a in covered
        ],
    )

    _write_csv(
        TABLES / "dual_path_subject_contributions.csv",
        [
            {
                "set_name": a["set_name"],
                "subject_name": s["subject_name"],
                "subject_demand": s["subject_demand"],
                "demand_share_q_s": s["demand_share_q_s"],
                "printing_count": s["printing_count"],
                "selected_easiest_card": s["selected_easiest_card"],
                "selected_rarest_card": s["selected_rarest_card"],
                "reachable_access": s["reachable_access"],
                "elite_scarcity": s["elite_scarcity"],
                "dual_path": s["dual_path"],
                "contribution": s["contribution"],
                "same_card_both_paths": s["same_card_both_paths"],
                "elite_tie_count": s["elite_tie_count"],
            }
            for a in covered
            for s in a["subjects"]
        ],
    )

    ah = next((a for a in audits if a["set_canonical_key"] == "ascendedHeroes"), None)
    if ah:
        _write_csv(
            TABLES / "ascended_heroes_anchor_card_trace.csv",
            [
                c for c in ah["card_trace"]
                if any(x.lower() in str(c["card_name"] or "").lower() for x in ANCHOR_SUBJECTS)
            ],
        )

    _write_csv(
        TABLES / "collector_appeal_ca6_ca7_comparison.csv",
        [
            {
                "set_name": a["set_name"],
                "D": a["roster_desirability_D"],
                "P": a["dual_path_depth_P"],
                **{k: (v * 100 if v is not None else None) for k, v in a["candidates"].items()},
            }
            for a in covered
        ],
    )

    _write_csv(
        TABLES / "pillar_effective_influence.csv",
        [
            {
                "candidate": key,
                **{k: v for k, v in value.items()
                   if k not in {"largest_movers", "most_helped", "most_harmed", "weighted_contribution_sd_by_pillar"}},
                **{f"wcsd_{k}": v for k, v in (value.get("weighted_contribution_sd_by_pillar") or {}).items()},
            }
            for key, value in influence.items()
        ],
    )

    logger.info("[dual-path-audit] wrote docs/research/dual_path_audit.json and 5 CSVs")
    logger.info("[dual-path-audit] P distribution: %s", json.dumps(distribution, indent=2))
    if anchors:
        logger.info("[dual-path-audit] Ascended Heroes anchors:\n%s", json.dumps(anchors, indent=2)[:4000])
    return 0


def _write_csv(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    if not rows:
        logger.warning("[dual-path-audit] no rows for %s", path.name)
        return
    keys: List[str] = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


if __name__ == "__main__":
    raise SystemExit(main())
