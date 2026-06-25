from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.desirability.composite import COMPOSITE_SCORING_VERSION  # noqa: E402
from backend.desirability.rarity_buckets import HIT_POLICY_VERSION  # noqa: E402
from backend.desirability.set_components import (  # noqa: E402
    SCORING_VERSION,
    build_canonical_card_price_index,
    build_card_appeal_correlation_dataset,
)


DEFAULT_FOCUS_SET_KEYS = [
    "shroudedFable",
    "evolvingSkies",
    "prismaticEvolutions",
    "ascendedHeroes",
    "scarletAndViolet151",
    "paldeanFates",
    "phantasmalFlames",
    "journeyTogether",
    "whiteFlare",
    "blackBolt",
    "cosmicEclipse",
    "crownZenithGalarianGallery",
    "celebrations",
    "legendaryCollection",
    "base",
    "skyridge",
]

COMPONENT_FIELDS = [
    "chase_subject_strength",
    "chase_subject_depth",
    "accessible_favorite_hits",
    "special_pack_chase_appeal",
]

FINANCIAL_METRIC_FIELDS = [
    "mean_value",
    "average_hit_value",
    "hit_ev_per_pack",
    "simulated_set_value",
    "profit_score",
    "safety_score",
    "stability_score",
    "effective_chase_count",
    "hhi_ev_concentration",
    "top1_ev_share",
    "top3_ev_share",
    "top5_ev_share",
    "prob_big_hit",
    "prob_profit",
    "expected_loss_when_losing",
    "expected_loss_per_pack",
    "mean_value_to_cost_ratio",
    "median_value_to_cost_ratio",
    "p95_value_to_cost_ratio",
    "p99_value_to_cost_ratio",
]

VARIANT_FIELDS = [
    "pure_desirability_score_baseline",
    "market_salient_subject_alignment_score",
    "pure_desirability_capped_adjustment_5",
    "pure_desirability_capped_adjustment_10",
    "pure_desirability_capped_adjustment_15",
    "monetary_chase_appeal_score",
    "rip_desirability_80_20",
    "rip_desirability_70_30",
    "rip_desirability_60_40",
]

SET_KEY_COMPAT_ALIASES = {
    "scarletandviolet": "scarletAndVioletBase",
}


class DesirabilityChaseAuditRepository:
    def __init__(self, client: Optional[Any] = None):
        if client is None:
            from backend.db.clients.supabase_client import supabase

            client = supabase
        self.client = client

    def list_v2_rows(
        self,
        *,
        scoring_version: str,
        hit_policy_version: str,
        composite_scoring_version: str,
    ) -> List[Dict[str, Any]]:
        return _paged_select(
            self.client.table("pokemon_set_desirability_component_scores")
            .select(
                "id,set_id,set_name,set_canonical_key,scoring_version,hit_policy_version,"
                "composite_scoring_version,set_desirability_score,chase_subject_strength,"
                "chase_subject_depth,accessible_favorite_hits,special_pack_chase_appeal,"
                "hit_eligible_card_count,scored_hit_eligible_card_count,unique_subject_count,"
                "premium_chase_subject_count,major_hit_subject_count,accessible_hit_count,"
                "top_subjects_json,subject_rollups_json,rarity_bucket_counts_json,"
                "component_inputs_json,diagnostics_json,warnings_json,built_at,updated_at"
            )
            .eq("scoring_version", scoring_version)
            .eq("hit_policy_version", hit_policy_version)
            .eq("composite_scoring_version", composite_scoring_version)
            .order("built_at", desc=True)
        )

    def list_latest_rip_rows(self) -> List[Dict[str, Any]]:
        return _paged_select(
            self.client.table("explore_rip_statistics_latest")
            .select(
                "calculation_run_id,set_id,set_name,canonical_key,run_at,mean_value,"
                "average_hit_value,hit_ev_per_pack,hit_pull_rate,hit_cards_pulled,"
                "hit_ev,non_hit_ev,simulated_set_value,current_market_pack_cost,pack_cost,"
                "profit_score,safety_score,stability_score,desirability_score,pack_score,"
                "chase_potential_score,experience_score,effective_chase_count,"
                "hhi_ev_concentration,top1_ev_share,top3_ev_share,top5_ev_share,"
                "prob_big_hit,prob_profit,expected_loss_when_losing,expected_loss_per_pack,"
                "mean_value_to_cost_ratio,median_value_to_cost_ratio,p95_value_to_cost_ratio,"
                "p99_value_to_cost_ratio,coefficient_of_variation,tail_value_p05"
            )
            .order("run_at", desc=True)
        )

    def list_simulation_cards_for_runs(self, run_ids: Sequence[str]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        if not run_ids:
            return rows
        # The near-mint helper view joins pricing data and can timeout when read
        # for many runs at once. The persisted simulation input row already
        # contains the price used at run time, pull rate, and EV contribution,
        # which are the exact values Chase Depth was computed from.
        for run_id in [str(value) for value in run_ids if value]:
            response = (
                self.client.table("simulation_input_cards")
                .select(
                    "calculation_run_id,card_id,card_variant_id,card_name,rarity_bucket,"
                    "price_used,effective_pull_rate,ev_contribution,captured_at"
                )
                .eq("calculation_run_id", run_id)
                .order("ev_contribution", desc=True)
                .limit(80)
                .execute()
            )
            rows.extend(response.data or [])
        return rows

    def list_canonical_cards(self, set_ids: Sequence[str]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        if not set_ids:
            return rows
        for chunk in _chunked([str(set_id) for set_id in set_ids if set_id], 200):
            rows.extend(
                _paged_select(
                    self.client.table("pokemon_canonical_cards")
                    .select(
                        "id,set_id,pokemon_tcg_api_card_id,name,supertype,subtypes,rarity,"
                        "number,printed_number,national_pokedex_numbers"
                    )
                    .in_("set_id", chunk)
                )
            )
        return rows

    def list_legacy_cards(self, set_ids: Sequence[str]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        if not set_ids:
            return rows
        for chunk in _chunked([str(set_id) for set_id in set_ids if set_id], 200):
            rows.extend(
                _paged_select(
                    self.client.table("cards")
                    .select("id,set_id,name,rarity,card_number,pokemon_tcg_api_id")
                    .in_("set_id", chunk)
                )
            )
        return rows

    def list_card_variants(self, legacy_card_ids: Sequence[str]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        if not legacy_card_ids:
            return rows
        for chunk in _chunked([str(card_id) for card_id in legacy_card_ids if card_id], 200):
            rows.extend(
                _paged_select(
                    self.client.table("card_variants")
                    .select("id,card_id,pokemon_tcg_api_id")
                    .in_("card_id", chunk)
                )
            )
        return rows

    def get_near_mint_condition_id(self) -> Optional[str]:
        response = (
            self.client.table("conditions")
            .select("id,name")
            .eq("name", "Near Mint")
            .limit(1)
            .execute()
        )
        row = (response.data or [None])[0]
        return str(row.get("id")) if isinstance(row, dict) and row.get("id") is not None else None

    def list_latest_price_rows(self, variant_ids: Sequence[str], condition_id: Optional[str]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        if not variant_ids or not condition_id:
            return rows
        for chunk in _chunked([str(variant_id) for variant_id in variant_ids if variant_id], 200):
            rows.extend(
                _paged_select(
                    self.client.table("card_market_usd_latest_by_condition")
                    .select("variant_id,condition_id,market_price,source,captured_at")
                    .in_("variant_id", chunk)
                    .eq("condition_id", condition_id)
                )
            )
        return rows

    def list_card_links(self, card_ids: Sequence[str]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        if not card_ids:
            return rows
        for chunk in _chunked([str(card_id) for card_id in card_ids if card_id], 200):
            rows.extend(
                _paged_select(
                    self.client.table("pokemon_card_desirability_links")
                    .select(
                        "pokemon_canonical_card_id,pokemon_reference_id,pokedex_number,"
                        "contribution_weight,match_method,match_confidence,is_hit_eligible,hit_policy_version"
                    )
                    .in_("pokemon_canonical_card_id", chunk)
                )
            )
        return rows

    def list_composite_scores(self, *, scoring_version: str) -> List[Dict[str, Any]]:
        return _paged_select(
            self.client.table("pokemon_desirability_composite_scores")
            .select(
                "pokemon_reference_id,pokedex_number,pokemon_name,desirability_score,"
                "fan_popularity_score,current_trend_score,desirability_rank,desirability_tier,scoring_version"
            )
            .eq("scoring_version", scoring_version)
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only Desirability V2 chase definition and variant audit."
    )
    parser.add_argument("--output-dir", default="logs")
    parser.add_argument("--focus-sets", nargs="+", default=DEFAULT_FOCUS_SET_KEYS)
    parser.add_argument("--scoring-version", default=SCORING_VERSION)
    parser.add_argument("--hit-policy-version", default=HIT_POLICY_VERSION)
    parser.add_argument("--composite-scoring-version", default=COMPOSITE_SCORING_VERSION)
    parser.add_argument("--market-card-limit", type=int, default=15)
    parser.add_argument(
        "--meaningful-share-threshold",
        type=float,
        default=0.01,
        help="Minimum EV contribution share for card-level meaningful chase pool.",
    )
    parser.add_argument(
        "--max-meaningful-cumulative-share",
        type=float,
        default=0.80,
        help="Always include cards until this cumulative EV share is reached.",
    )
    return parser


def load_backend_env() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    load_dotenv(env_path, override=False)


def main() -> int:
    args = build_parser().parse_args()
    load_backend_env()
    report = build_audit_report(
        repository=DesirabilityChaseAuditRepository(),
        focus_set_keys=args.focus_sets,
        scoring_version=args.scoring_version,
        hit_policy_version=args.hit_policy_version,
        composite_scoring_version=args.composite_scoring_version,
        market_card_limit=args.market_card_limit,
        meaningful_share_threshold=args.meaningful_share_threshold,
        max_meaningful_cumulative_share=args.max_meaningful_cumulative_share,
    )
    paths = write_outputs(report, output_dir=Path(args.output_dir))
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


def build_audit_report(
    *,
    repository: DesirabilityChaseAuditRepository,
    focus_set_keys: Sequence[str],
    scoring_version: str,
    hit_policy_version: str,
    composite_scoring_version: str,
    market_card_limit: int,
    meaningful_share_threshold: float,
    max_meaningful_cumulative_share: float,
) -> Dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    v2_rows = _latest_by_set_id(
        repository.list_v2_rows(
            scoring_version=scoring_version,
            hit_policy_version=hit_policy_version,
            composite_scoring_version=composite_scoring_version,
        )
    )
    rip_rows = _latest_by_set_id(repository.list_latest_rip_rows())
    set_ids = _focused_set_ids(
        sorted(set(v2_rows) | set(rip_rows)),
        v2_rows=v2_rows,
        rip_rows=rip_rows,
        focus_set_keys=focus_set_keys,
    )
    run_ids = [
        str((rip_rows.get(set_id) or {}).get("calculation_run_id"))
        for set_id in set_ids
        if (rip_rows.get(set_id) or {}).get("calculation_run_id")
    ]
    card_rows = repository.list_simulation_cards_for_runs(run_ids)
    canonical_cards = repository.list_canonical_cards(set_ids)
    links = repository.list_card_links([str(row.get("id")) for row in canonical_cards if row.get("id")])
    composite_scores = repository.list_composite_scores(scoring_version=composite_scoring_version)
    legacy_cards = repository.list_legacy_cards(set_ids)
    variant_rows = repository.list_card_variants([str(row.get("id")) for row in legacy_cards if row.get("id")])
    near_mint_condition_id = repository.get_near_mint_condition_id()
    latest_price_rows = repository.list_latest_price_rows(
        [str(row.get("id")) for row in variant_rows if row.get("id")],
        near_mint_condition_id,
    )
    prices_by_card = build_canonical_card_price_index(
        canonical_cards=canonical_cards,
        legacy_cards=legacy_cards,
        variant_rows=variant_rows,
        latest_price_rows=latest_price_rows,
    )

    canonical_indexes = _build_canonical_indexes(canonical_cards)
    canonical_by_set = _group_by(canonical_cards, "set_id")
    links_by_card = _group_by(links, "pokemon_canonical_card_id")
    scores_by_reference = {
        str(row.get("pokemon_reference_id")): row
        for row in composite_scores
        if row.get("pokemon_reference_id") is not None
    }
    cards_by_run = _group_by(card_rows, "calculation_run_id")

    set_reports: List[Dict[str, Any]] = []
    for set_id in set_ids:
        v2 = v2_rows.get(set_id)
        rip = rip_rows.get(set_id)
        run_id = str(rip.get("calculation_run_id")) if rip and rip.get("calculation_run_id") else ""
        market_cards = _build_market_cards(
            simulation_cards=cards_by_run.get(run_id, []),
            set_id=set_id,
            canonical_indexes=canonical_indexes,
            links_by_card=links_by_card,
            scores_by_reference=scores_by_reference,
            market_card_limit=market_card_limit,
            meaningful_share_threshold=meaningful_share_threshold,
            max_meaningful_cumulative_share=max_meaningful_cumulative_share,
            v2_row=v2 or {},
        )
        set_cards = canonical_by_set.get(set_id, [])
        set_card_ids = {str(card.get("id")) for card in set_cards if card.get("id") is not None}
        card_appeal_dataset = build_card_appeal_correlation_dataset(
            cards=set_cards,
            links=[link for card_id in set_card_ids for link in links_by_card.get(card_id, [])],
            scores_by_reference=scores_by_reference,
            prices_by_card={card_id: prices_by_card[card_id] for card_id in set_card_ids if card_id in prices_by_card},
        )
        set_reports.append(
            _build_set_report(
                set_id=set_id,
                v2=v2 or {},
                rip=rip or {},
                market_cards=market_cards,
                card_appeal_dataset=card_appeal_dataset,
            )
        )

    _add_variant_ranks(set_reports)
    correlations = _build_correlations(set_reports)
    focused = _build_focused_rows(set_reports, focus_set_keys)
    recommendation = _build_recommendation(set_reports, correlations, focused)

    return {
        "generated_at": generated_at,
        "read_only": True,
        "source_tables": [
            "pokemon_set_desirability_component_scores",
            "explore_rip_statistics_latest",
            "simulation_input_cards",
            "pokemon_canonical_cards",
            "pokemon_card_desirability_links",
            "pokemon_desirability_composite_scores",
            "cards",
            "card_variants",
            "conditions",
            "card_market_usd_latest_by_condition",
        ],
        "parameters": {
            "scoring_version": scoring_version,
            "hit_policy_version": hit_policy_version,
            "composite_scoring_version": composite_scoring_version,
            "market_card_limit": market_card_limit,
            "meaningful_share_threshold": meaningful_share_threshold,
            "max_meaningful_cumulative_share": max_meaningful_cumulative_share,
            "focus_set_keys": list(focus_set_keys),
        },
        "current_chase_depth_formula": current_chase_depth_formula(),
        "sets": set_reports,
        "correlations": correlations,
        "focused": focused,
        "recommendation_markdown": recommendation,
    }


def _focused_set_ids(
    set_ids: Sequence[str],
    *,
    v2_rows: Dict[str, Dict[str, Any]],
    rip_rows: Dict[str, Dict[str, Any]],
    focus_set_keys: Sequence[str],
) -> List[str]:
    focused_keys = {
        candidate.lower()
        for key in focus_set_keys
        for candidate in _focus_key_candidates(key)
        if candidate
    }
    if not focused_keys:
        return list(set_ids)
    focused_ids = [
        set_id
        for set_id in set_ids
        if str((v2_rows.get(set_id) or {}).get("set_canonical_key") or "").lower() in focused_keys
        or str((rip_rows.get(set_id) or {}).get("canonical_key") or "").lower() in focused_keys
    ]
    return focused_ids or list(set_ids)


def _build_set_report(
    *,
    set_id: str,
    v2: Dict[str, Any],
    rip: Dict[str, Any],
    market_cards: List[Dict[str, Any]],
    card_appeal_dataset: Dict[str, Any],
) -> Dict[str, Any]:
    baseline = _as_float(v2.get("set_desirability_score"))
    alignment = _market_salient_subject_alignment(market_cards)
    adjustment_input = max(0.0, (alignment or 0.0) - (baseline or 0.0))
    monetary = _monetary_chase_appeal_score(rip, market_cards)
    card_appeal_pairs = [
        (
            _as_float(row.get("subject_desirability_score")) or 0.0,
            _as_float(row.get("market_price")) or 0.0,
        )
        for row in card_appeal_dataset.get("rows") or []
        if _as_float(row.get("subject_desirability_score")) is not None
        and _as_float(row.get("market_price")) is not None
    ]
    card_appeal_pearson = _pearson(card_appeal_pairs)
    card_appeal_spearman = _spearman(card_appeal_pairs)
    card_appeal_max_abs = (
        max(abs(card_appeal_pearson or 0.0), abs(card_appeal_spearman or 0.0))
        if card_appeal_pairs
        else None
    )

    variants = {
        "pure_desirability_score_baseline": baseline,
        "market_salient_subject_alignment_score": alignment,
        "pure_desirability_capped_adjustment_5": _cap_score((baseline or 0.0) + min(5.0, adjustment_input)) if baseline is not None else None,
        "pure_desirability_capped_adjustment_10": _cap_score((baseline or 0.0) + min(10.0, adjustment_input)) if baseline is not None else None,
        "pure_desirability_capped_adjustment_15": _cap_score((baseline or 0.0) + min(15.0, adjustment_input)) if baseline is not None else None,
        "monetary_chase_appeal_score": monetary,
        "rip_desirability_80_20": _blend(baseline, monetary, 0.80, 0.20),
        "rip_desirability_70_30": _blend(baseline, monetary, 0.70, 0.30),
        "rip_desirability_60_40": _blend(baseline, monetary, 0.60, 0.40),
    }

    return {
        "set_id": set_id,
        "set_name": v2.get("set_name") or rip.get("set_name"),
        "set_canonical_key": v2.get("set_canonical_key") or rip.get("canonical_key"),
        "v2_built_at": v2.get("built_at"),
        "calculation_run_id": rip.get("calculation_run_id"),
        "run_at": rip.get("run_at"),
        "current_v2": {
            "set_desirability_score": baseline,
            **{field: _as_float(v2.get(field)) for field in COMPONENT_FIELDS},
            "top_subjects": _jsonish(v2.get("top_subjects_json")) or [],
            "subject_rollups": _jsonish(v2.get("subject_rollups_json")) or [],
            "rarity_bucket_counts": _jsonish(v2.get("rarity_bucket_counts_json")) or {},
            "component_inputs": _jsonish(v2.get("component_inputs_json")) or {},
            "diagnostics": _jsonish(v2.get("diagnostics_json")) or {},
            "warnings": _jsonish(v2.get("warnings_json")) or [],
        },
        "financial_metrics": {field: _as_float(rip.get(field)) for field in FINANCIAL_METRIC_FIELDS},
        "market_salient_cards": market_cards,
        "card_appeal_market_price_correlation": {
            **(card_appeal_dataset.get("diagnostics") or {}),
            "n": len(card_appeal_pairs),
            "pearson": card_appeal_pearson,
            "spearman": card_appeal_spearman,
            "interpretation": _correlation_interpretation(card_appeal_max_abs),
            "sample_source": "canonical_checklist_cards",
        },
        "card_appeal_correlation_sample_cards": (card_appeal_dataset.get("rows") or [])[:20],
        "variants": variants,
    }


def _build_market_cards(
    *,
    simulation_cards: Sequence[Dict[str, Any]],
    set_id: str,
    canonical_indexes: Dict[str, Dict[str, Dict[str, Any]]],
    links_by_card: Dict[str, List[Dict[str, Any]]],
    scores_by_reference: Dict[str, Dict[str, Any]],
    market_card_limit: int,
    meaningful_share_threshold: float,
    max_meaningful_cumulative_share: float,
    v2_row: Dict[str, Any],
) -> List[Dict[str, Any]]:
    rows = []
    total_ev = sum(max(0.0, _as_float(row.get("ev_contribution")) or 0.0) for row in simulation_cards)
    if total_ev <= 0:
        total_ev = 0.0
    sorted_cards = sorted(
        simulation_cards,
        key=lambda row: (
            max(0.0, _as_float(row.get("ev_contribution")) or 0.0),
            _as_float(row.get("current_near_mint_price")) or _as_float(row.get("price_used")) or 0.0,
        ),
        reverse=True,
    )
    cumulative = 0.0
    v2_card_ids = _v2_card_id_bucket_index(v2_row)

    for index, row in enumerate(sorted_cards, start=1):
        ev = max(0.0, _as_float(row.get("ev_contribution")) or 0.0)
        if ev <= 0:
            continue
        share = ev / total_ev if total_ev > 0 else None
        cumulative += share or 0.0
        included = (
            index <= 5
            or (share is not None and share >= meaningful_share_threshold)
            or cumulative <= max_meaningful_cumulative_share
        )
        if not included and len(rows) >= market_card_limit:
            break
        canonical = _match_canonical_card(row, set_id, canonical_indexes)
        linked_subjects = _linked_subjects(canonical, links_by_card, scores_by_reference)
        weighted_subject_score = _weighted_subject_score(linked_subjects)
        canonical_card_id = str(canonical.get("id") or "") if canonical else None
        v2_bucket = (
            v2_card_ids.get(canonical_card_id or "")
            or v2_card_ids.get(f"name:{_norm(_strip_parenthetical(row.get('card_name')))}")
            or v2_card_ids.get(f"name:{_norm(_strip_parenthetical(canonical.get('name') if canonical else None))}")
        )
        contribution_to_hhi = (share * share) if share is not None else None
        rows.append(
            {
                "rank_by_ev_contribution": index,
                "canonical_card_id": canonical_card_id,
                "pokemon_tcg_api_card_id": canonical.get("pokemon_tcg_api_card_id") if canonical else None,
                "simulation_card_id": row.get("card_id"),
                "simulation_card_variant_id": row.get("card_variant_id"),
                "set_id": set_id,
                "card_name": row.get("card_name"),
                "canonical_card_name": canonical.get("name") if canonical else None,
                "rarity": canonical.get("rarity") if canonical else row.get("rarity_bucket"),
                "rarity_bucket": row.get("rarity_bucket"),
                "market_price": _as_float(row.get("current_near_mint_price")) or _as_float(row.get("price_used")),
                "price_used_at_run": _as_float(row.get("price_used")),
                "pull_rate": _as_float(row.get("effective_pull_rate")),
                "ev_contribution": ev,
                "contribution_share": share,
                "cumulative_contribution_share": cumulative,
                "chase_depth_effective_count_contribution": contribution_to_hhi,
                "included_in_meaningful_chase_pool": included,
                "linked_subjects": linked_subjects,
                "subject_desirability_score": weighted_subject_score,
                "captured_by_current_rarity_bucket_logic": bool(v2_bucket),
                "current_v2_bucket": v2_bucket,
                "would_require_promotion_for_desirability_analysis": bool(
                    included and weighted_subject_score is not None and not v2_bucket
                ),
            }
        )
        if len(rows) >= market_card_limit:
            break
    return rows


def _match_canonical_card(
    row: Dict[str, Any],
    set_id: str,
    indexes: Dict[str, Dict[str, Dict[str, Any]]],
) -> Dict[str, Any]:
    set_indexes = indexes.get(str(set_id), {})
    card_id = str(row.get("card_id") or "").strip()
    if card_id and card_id in set_indexes.get("by_id", {}):
        return set_indexes["by_id"][card_id]
    if card_id and card_id in set_indexes.get("by_number", {}):
        return set_indexes["by_number"][card_id]
    name_key = _norm(row.get("card_name"))
    rarity_key = _norm(row.get("rarity_bucket"))
    if (name_key, rarity_key) in set_indexes.get("by_name_rarity", {}):
        return set_indexes["by_name_rarity"][(name_key, rarity_key)]
    base_name_key = _norm(_strip_parenthetical(row.get("card_name")))
    if (base_name_key, rarity_key) in set_indexes.get("by_name_rarity", {}):
        return set_indexes["by_name_rarity"][(base_name_key, rarity_key)]
    if base_name_key in set_indexes.get("by_name", {}):
        return set_indexes["by_name"][base_name_key]
    return set_indexes.get("by_name", {}).get(name_key, {})


def _build_canonical_indexes(cards: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Dict[str, Any]]]:
    indexes: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for card in cards:
        set_id = str(card.get("set_id") or "")
        if not set_id:
            continue
        bucket = indexes.setdefault(
            set_id,
            {"by_id": {}, "by_number": {}, "by_name_rarity": {}, "by_name": {}},
        )
        card_id = str(card.get("id") or "")
        if card_id:
            bucket["by_id"][card_id] = card
        for value in (card.get("number"), card.get("printed_number"), card.get("pokemon_tcg_api_card_id")):
            key = str(value or "").strip()
            if key and key not in bucket["by_number"]:
                bucket["by_number"][key] = card
        name_key = _norm(card.get("name"))
        rarity_key = _norm(card.get("rarity"))
        if name_key:
            bucket["by_name"].setdefault(name_key, card)
            bucket["by_name_rarity"].setdefault((name_key, rarity_key), card)
    return indexes


def _linked_subjects(
    canonical: Dict[str, Any],
    links_by_card: Dict[str, List[Dict[str, Any]]],
    scores_by_reference: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    card_id = str(canonical.get("id") or "")
    subjects: List[Dict[str, Any]] = []
    seen_reference_ids: set[str] = set()
    for link in links_by_card.get(card_id, []):
        reference_id = str(link.get("pokemon_reference_id") or "")
        if reference_id in seen_reference_ids:
            continue
        seen_reference_ids.add(reference_id)
        score = scores_by_reference.get(reference_id, {})
        desirability = _as_float(score.get("desirability_score"))
        subjects.append(
            {
                "pokemon_reference_id": reference_id or None,
                "pokedex_number": link.get("pokedex_number") or score.get("pokedex_number"),
                "pokemon_name": score.get("pokemon_name"),
                "desirability_score": desirability,
                "fan_popularity_score": _as_float(score.get("fan_popularity_score")),
                "current_trend_score": _as_float(score.get("current_trend_score")),
                "desirability_rank": score.get("desirability_rank"),
                "desirability_tier": score.get("desirability_tier"),
                "contribution_weight": _as_float(link.get("contribution_weight")) or 1.0,
                "match_method": link.get("match_method"),
                "match_confidence": link.get("match_confidence"),
            }
        )
    return subjects


def _weighted_subject_score(subjects: Sequence[Dict[str, Any]]) -> Optional[float]:
    weighted = [
        ((_as_float(subject.get("desirability_score"))), (_as_float(subject.get("contribution_weight")) or 1.0))
        for subject in subjects
        if _as_float(subject.get("desirability_score")) is not None
    ]
    total_weight = sum(weight for _, weight in weighted)
    if total_weight <= 0:
        return None
    return sum(float(score) * weight for score, weight in weighted if score is not None) / total_weight


def _v2_card_id_bucket_index(v2_row: Dict[str, Any]) -> Dict[str, str]:
    index: Dict[str, str] = {}
    for rollup in _jsonish(v2_row.get("subject_rollups_json")) or []:
        bucket = str(rollup.get("best_rarity_bucket") or "")
        representative_name = str(rollup.get("representative_card_name") or "")
        if representative_name:
            index[f"name:{_norm(_strip_parenthetical(representative_name))}"] = bucket
        for card in rollup.get("all_card_names") or []:
            card_id = str(card.get("pokemon_canonical_card_id") or "")
            if card_id:
                index[card_id] = bucket
            name = str(card.get("name") or "")
            if name:
                index[f"name:{_norm(_strip_parenthetical(name))}"] = bucket
    return index


def _market_salient_subject_alignment(cards: Sequence[Dict[str, Any]]) -> Optional[float]:
    meaningful = [
        card for card in cards
        if card.get("included_in_meaningful_chase_pool")
        and _as_float(card.get("subject_desirability_score")) is not None
        and _as_float(card.get("contribution_share")) is not None
    ]
    total_share = sum(_as_float(card.get("contribution_share")) or 0.0 for card in meaningful)
    if total_share <= 0:
        return None
    return _cap_score(
        sum(
            (_as_float(card.get("subject_desirability_score")) or 0.0)
            * ((_as_float(card.get("contribution_share")) or 0.0) / total_share)
            for card in meaningful
        )
    )


def _monetary_chase_appeal_score(rip: Dict[str, Any], cards: Sequence[Dict[str, Any]]) -> Optional[float]:
    meaningful = [card for card in cards if card.get("included_in_meaningful_chase_pool")]
    if not meaningful and not rip:
        return None

    top_values = sorted(
        [_as_float(card.get("market_price")) or 0.0 for card in meaningful],
        reverse=True,
    )
    top1_value = top_values[0] if top_values else None
    top3_value = sum(top_values[:3]) if top_values else None
    top5_value = sum(top_values[:5]) if top_values else None
    pack_cost = _as_float(rip.get("current_market_pack_cost")) or _as_float(rip.get("pack_cost")) or 5.0
    chance_big = _as_float(rip.get("prob_big_hit"))
    p95_ratio = _as_float(rip.get("p95_value_to_cost_ratio"))
    hit_ev_per_pack = _as_float(rip.get("hit_ev_per_pack"))
    effective_depth = _as_float(rip.get("effective_chase_count"))
    top1_share = _as_float(rip.get("top1_ev_share"))
    top3_share = _as_float(rip.get("top3_ev_share"))

    value_upside_score = _normalize_0_100((top1_value or 0.0) / pack_cost if pack_cost > 0 else None, 0.0, 50.0)
    top_stack_score = _normalize_0_100((top3_value or 0.0) / pack_cost if pack_cost > 0 else None, 0.0, 100.0)
    top5_stack_score = _normalize_0_100((top5_value or 0.0) / pack_cost if pack_cost > 0 else None, 0.0, 150.0)
    frequency_score = _normalize_0_100(chance_big, 0.0, 1.0)
    p95_score = _normalize_0_100(p95_ratio, 0.25, 5.0)
    hit_ev_score = _normalize_0_100((hit_ev_per_pack / pack_cost) if hit_ev_per_pack is not None and pack_cost > 0 else None, 0.0, 1.5)
    depth_score = _normalize_0_100(effective_depth, 1.0, 40.0)
    concentration_penalty = max(
        _normalize_0_100(top1_share, 0.0, 0.50) or 0.0,
        _normalize_0_100(top3_share, 0.0, 0.75) or 0.0,
    )
    breadth_bonus = min(100.0, depth_score or 0.0)

    components = {
        "top1_value_to_pack_cost": (value_upside_score, 0.22),
        "top3_value_to_pack_cost": (top_stack_score, 0.12),
        "top5_value_to_pack_cost": (top5_stack_score, 0.08),
        "chance_at_big_pull": (frequency_score, 0.16),
        "p95_value_to_cost": (p95_score, 0.16),
        "hit_ev_to_cost": (hit_ev_score, 0.12),
        "chase_depth": (breadth_bonus, 0.09),
        "concentration_penalty_inverse": (100.0 - concentration_penalty, 0.05),
    }
    available = [(score, weight) for score, weight in components.values() if score is not None]
    if not available:
        return None
    total_weight = sum(weight for _, weight in available)
    return _cap_score(sum(score * weight for score, weight in available) / total_weight)


def _add_variant_ranks(set_reports: List[Dict[str, Any]]) -> None:
    for field in VARIANT_FIELDS:
        ranked = sorted(
            [
                (idx, _as_float(report.get("variants", {}).get(field)))
                for idx, report in enumerate(set_reports)
                if _as_float(report.get("variants", {}).get(field)) is not None
            ],
            key=lambda item: item[1],
            reverse=True,
        )
        rank_by_index: Dict[int, int] = {}
        previous_value: Optional[float] = None
        previous_rank = 0
        for position, (idx, value) in enumerate(ranked, start=1):
            rank = previous_rank if previous_value is not None and value == previous_value else position
            rank_by_index[idx] = rank
            previous_value = value
            previous_rank = rank
        for idx, report in enumerate(set_reports):
            report.setdefault("variant_ranks", {})[field] = rank_by_index.get(idx)


def _build_correlations(set_reports: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for variant in VARIANT_FIELDS:
        for metric in FINANCIAL_METRIC_FIELDS:
            pairs = []
            for report in set_reports:
                x = _as_float(report.get("variants", {}).get(variant))
                y = _as_float(report.get("financial_metrics", {}).get(metric))
                if x is not None and y is not None:
                    pairs.append((x, y))
            pearson = _pearson(pairs)
            spearman = _spearman(pairs)
            max_abs = max(abs(pearson or 0.0), abs(spearman or 0.0)) if pairs else None
            rows.append(
                {
                    "variant": variant,
                    "metric": metric,
                    "n": len(pairs),
                    "pearson": pearson,
                    "spearman": spearman,
                    "interpretation": _correlation_interpretation(max_abs),
                }
            )
    return rows


def _build_focused_rows(
    set_reports: Sequence[Dict[str, Any]],
    focus_set_keys: Sequence[str],
) -> List[Dict[str, Any]]:
    by_key = {
        str(report.get("set_canonical_key") or "").lower(): report
        for report in set_reports
        if report.get("set_canonical_key")
    }
    rows: List[Dict[str, Any]] = []
    for key in focus_set_keys:
        report = _focused_report_by_key(by_key, key)
        if not report:
            rows.append({"set_canonical_key": key, "status": "missing_from_v2_or_latest_rip_data"})
            continue
        variants = report.get("variants", {})
        ranks = report.get("variant_ranks", {})
        current = report.get("current_v2", {})
        financial = report.get("financial_metrics", {})
        card_appeal = report.get("card_appeal_market_price_correlation") or {}
        baseline = _as_float(variants.get("pure_desirability_score_baseline"))
        alignment = _as_float(variants.get("market_salient_subject_alignment_score"))
        monetary = _as_float(variants.get("monetary_chase_appeal_score"))
        rows.append(
            {
                "status": "ok",
                "set_name": report.get("set_name"),
                "set_canonical_key": report.get("set_canonical_key"),
                "current_v2_score": baseline,
                "current_v2_rank": ranks.get("pure_desirability_score_baseline"),
                "variant_b_score": alignment,
                "variant_b_rank": ranks.get("market_salient_subject_alignment_score"),
                "variant_c_5_score": variants.get("pure_desirability_capped_adjustment_5"),
                "variant_c_5_rank": ranks.get("pure_desirability_capped_adjustment_5"),
                "variant_c_10_score": variants.get("pure_desirability_capped_adjustment_10"),
                "variant_c_10_rank": ranks.get("pure_desirability_capped_adjustment_10"),
                "variant_c_15_score": variants.get("pure_desirability_capped_adjustment_15"),
                "variant_c_15_rank": ranks.get("pure_desirability_capped_adjustment_15"),
                "monetary_chase_appeal_score": monetary,
                "monetary_chase_appeal_rank": ranks.get("monetary_chase_appeal_score"),
                "rip_80_20_score": variants.get("rip_desirability_80_20"),
                "rip_80_20_rank": ranks.get("rip_desirability_80_20"),
                "rip_70_30_score": variants.get("rip_desirability_70_30"),
                "rip_70_30_rank": ranks.get("rip_desirability_70_30"),
                "rip_60_40_score": variants.get("rip_desirability_60_40"),
                "rip_60_40_rank": ranks.get("rip_desirability_60_40"),
                "card_appeal_canonical_count": card_appeal.get("canonical_count"),
                "card_appeal_priced_count": card_appeal.get("priced_count"),
                "card_appeal_linked_count": card_appeal.get("linked_count"),
                "card_appeal_scored_linked_count": card_appeal.get("scored_linked_count"),
                "card_appeal_included_count": card_appeal.get("included_count"),
                "card_appeal_excluded_unpriced_count": card_appeal.get("excluded_unpriced_count"),
                "card_appeal_excluded_unlinked_count": card_appeal.get("excluded_unlinked_count"),
                "card_appeal_excluded_missing_score_count": card_appeal.get("excluded_missing_score_count"),
                "card_appeal_included_policy": card_appeal.get("included_policy"),
                "card_appeal_vs_market_price_n": card_appeal.get("n"),
                "card_appeal_vs_market_price_pearson": card_appeal.get("pearson"),
                "card_appeal_vs_market_price_spearman": card_appeal.get("spearman"),
                "card_appeal_sample_source": card_appeal.get("sample_source"),
                "score_delta_variant_b": _delta(alignment, baseline),
                "score_delta_variant_c_10": _delta(_as_float(variants.get("pure_desirability_capped_adjustment_10")), baseline),
                "score_delta_rip_70_30": _delta(_as_float(variants.get("rip_desirability_70_30")), baseline),
                "chase_subject_strength": current.get("chase_subject_strength"),
                "chase_subject_depth": current.get("chase_subject_depth"),
                "accessible_favorite_hits": current.get("accessible_favorite_hits"),
                "special_pack_chase_appeal": current.get("special_pack_chase_appeal"),
                "chase_depth": financial.get("effective_chase_count"),
                "stability_score": financial.get("stability_score"),
                "top_intended_design_chase_subjects_json": json.dumps((current.get("top_subjects") or [])[:10], ensure_ascii=False),
                "top_market_salient_chase_cards_json": json.dumps((report.get("market_salient_cards") or [])[:10], ensure_ascii=False),
                "change_judgment": _focused_change_judgment(report),
            }
        )
    return rows


def _focused_report_by_key(by_key: Dict[str, Dict[str, Any]], key: Any) -> Optional[Dict[str, Any]]:
    for candidate in _focus_key_candidates(key):
        report = by_key.get(str(candidate).lower())
        if report:
            return report
    return None


def _focus_key_candidates(key: Any) -> List[str]:
    text = str(key or "").strip()
    if not text:
        return []
    candidates = [text]
    alias = SET_KEY_COMPAT_ALIASES.get(text.lower())
    if alias and alias not in candidates:
        candidates.append(alias)
    return candidates


def _focused_change_judgment(report: Dict[str, Any]) -> str:
    variants = report.get("variants", {})
    baseline = _as_float(variants.get("pure_desirability_score_baseline"))
    alignment = _as_float(variants.get("market_salient_subject_alignment_score"))
    monetary = _as_float(variants.get("monetary_chase_appeal_score"))
    if baseline is None:
        return "missing_baseline"
    promoted = sum(1 for card in report.get("market_salient_cards") or [] if card.get("would_require_promotion_for_desirability_analysis"))
    captured = sum(1 for card in report.get("market_salient_cards") or [] if card.get("captured_by_current_rarity_bucket_logic"))
    if alignment is not None and alignment > baseline + 10 and promoted:
        return "possibly_justified_market_subject_gap"
    if monetary is not None and monetary > baseline + 20:
        return "monetary_appeal_high_keep_separate_from_pure"
    if captured >= 5:
        return "mostly_captured_by_current_v2"
    return "minor_or_inconclusive_change"


def _build_recommendation(
    set_reports: Sequence[Dict[str, Any]],
    correlations: Sequence[Dict[str, Any]],
    focused: Sequence[Dict[str, Any]],
) -> str:
    pure_watch = _max_variant_corr(correlations, "pure_desirability_capped_adjustment_10")
    baseline_watch = _max_variant_corr(correlations, "pure_desirability_score_baseline")
    monetary_watch = _max_variant_corr(correlations, "monetary_chase_appeal_score")
    rip_watch = _max_variant_corr(correlations, "rip_desirability_70_30")
    promoted_sets = sum(
        1
        for report in set_reports
        if any(card.get("would_require_promotion_for_desirability_analysis") for card in report.get("market_salient_cards") or [])
    )
    total_with_cards = sum(1 for report in set_reports if report.get("market_salient_cards"))
    focused_gap_rows = [
        row for row in focused
        if str(row.get("change_judgment") or "") in {
            "possibly_justified_market_subject_gap",
            "monetary_appeal_high_keep_separate_from_pure",
        }
    ]
    shrouded = _focused_by_key(focused, "shroudedFable")
    evolving = _focused_by_key(focused, "evolvingSkies")

    recommendation = (
        "Keep current V2 as Pure Desirability for now, add Monetary Chase Appeal as a separate downstream metric, "
        "and prototype Rip Desirability as a combined opening-desire metric outside the pure predictor."
    )
    if pure_watch and pure_watch.get("max_abs_correlation", 0) > 0.70:
        recommendation = (
            "Do not add the capped market-salient subject adjustment to Pure Desirability yet; use it as diagnostics "
            "while adding separate Monetary Chase Appeal and Rip Desirability prototypes."
        )

    lines = [
        "# Desirability V2 Chase Definition Audit Recommendation",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## A. Current Chase Depth Formula",
        "",
        "Chase Depth is the effective count derived from hit-card EV contribution concentration:",
        "",
        "1. Build hit-only card EV contributions from the EV pipeline.",
        "2. Treat negative card EV values as zero.",
        "3. Compute each card share: `p_i = card_ev_contribution_i / total_hit_card_ev`.",
        "4. Compute HHI: `sum(p_i^2)`.",
        "5. Compute raw Chase Depth / effective chase count: `1 / HHI` when HHI is positive.",
        "6. Normalize Chase Depth score with fixed anchors 1 to 40, higher is better.",
        "",
        "Stability uses coefficient of variation plus EV concentration metrics. The user-facing Stability interpretation reads top1/top3 EV share and effective chase count.",
        "",
        "## B. Does Chase Depth Find Cards V2 Misses?",
        "",
        f"Card-level simulation rows were available for {total_with_cards} sets in the latest RIP dataset. Within those rows, {promoted_sets} sets had meaningful market-salient Pokémon cards that required promotion beyond current V2 card bucket matching.",
        "",
        "The practical result: Chase Depth/value contribution is useful as a diagnostic card selector, but this run did not prove that current V2 is broadly missing market-salient Pokémon subjects. The main caveat is coverage: several older focused sets have V2 rows but no latest card-level RIP rows in this audit.",
        "",
        "## C. Focused Cases",
        "",
        f"- Shrouded Fable: current V2 {shrouded.get('current_v2_score', 'N/A')}, Variant B {shrouded.get('variant_b_score', 'N/A')}. The market-salient IR-heavy pool scores higher than current V2, but the top IR subjects were already captured as V2 major hits, so this looks more like weighting/component design than a missing-card problem.",
        f"- Evolving Skies: current V2 {evolving.get('current_v2_score', 'N/A')}, Variant B {evolving.get('variant_b_score', 'N/A')}. Alt arts resolve to desirable subjects like Umbreon, Dragonite, Rayquaza, Sylveon, and Espeon; current V2 already captures those subjects after name/subject matching.",
        "",
        "## D. Correlation Risk",
        "",
        f"- Baseline Pure Desirability max financial correlation: {_fmt_corr_summary(baseline_watch)}.",
        f"- Capped Pure adjustment, 10-point cap, max financial correlation: {_fmt_corr_summary(pure_watch)}.",
        f"- Monetary Chase Appeal max financial correlation: {_fmt_corr_summary(monetary_watch)}.",
        f"- Rip Desirability 70/30 max financial correlation: {_fmt_corr_summary(rip_watch)}.",
        "",
        "High correlation is acceptable for Monetary Chase Appeal and Rip Desirability, but it is risky for Pure Desirability. The 10-point capped adjustment remains near or above the overlap threshold in this run and does not solve the conceptual concern.",
        "",
        "## E-H. Recommendation",
        "",
        "- E. Keep current V2 as Pure Desirability for now.",
        "- F. Add a separate Monetary Chase Appeal score; it intentionally overlaps with market value and EV.",
        "- G. Introduce Rip Desirability as a downstream opening-desire blend, not as a replacement for Pure Desirability.",
        f"- H. Next implementation candidate: {recommendation}",
        f"- Focused sets with notable market/subject gaps requiring manual review: {len(focused_gap_rows)}.",
        "",
        "## Bottom Line",
        "",
        recommendation,
        "",
        "Implementation choice for the next step: keep V2 unchanged as `pure_desirability_score`, add `monetary_chase_appeal_score`, and keep `rip_desirability_score` downstream from Pure plus Monetary. Use market-salient subject alignment as a diagnostic until the gap cases are manually reviewed.",
        "",
        "## Variant Definitions Used In This Audit",
        "",
        "- Variant A: current V2 score as-is.",
        "- Variant B: EV-share-weighted subject desirability among meaningful market-salient cards; price/EV chooses and weights cards, subject desirability supplies the score.",
        "- Variant C: current V2 plus capped positive Variant B gap, tested at 5/10/15 points.",
        "- Variant D: separate monetary chase score using top-card value, top 3/5 value, big-hit chance, p95 upside, hit EV to cost, chase depth, and concentration.",
        "- Variant E: Pure plus Monetary blends at 80/20, 70/30, and 60/40.",
    ]
    return "\n".join(lines) + "\n"


def _focused_by_key(focused: Sequence[Dict[str, Any]], key: str) -> Dict[str, Any]:
    for row in focused:
        if str(row.get("set_canonical_key") or "").lower() == key.lower():
            return row
    return {}


def current_chase_depth_formula() -> Dict[str, Any]:
    return {
        "source_files": [
            "backend/calculations/evr/derived_metrics.py::compute_chase_dependency_metrics",
            "backend/calculations/evr/derived_metrics.py::_compute_hhi_from_ev_contributions",
            "backend/calculations/evr/derived_metrics.py::_compute_effective_chase_count",
            "backend/calculations/packCalcsRefractored/packCalculationOrchestrator.py::build_hit_and_non_hit_ev_contributions",
            "backend/interpretation/rips/pillars/stability.py::interpret_stability",
        ],
        "formula": {
            "card_share": "card_ev_contribution / sum(hit_card_ev_contribution)",
            "hhi_ev_concentration": "sum(card_share ** 2)",
            "effective_chase_count": "1 / hhi_ev_concentration",
            "chase_depth_score": "normalize effective_chase_count from anchor 1 to 40, higher is better",
        },
        "based_on": [
            "hit-only card EV contribution",
            "effective pull rate embedded in EV contribution",
            "market price embedded in EV contribution",
            "HHI/effective-number concentration math",
            "top1/top3/top5 EV share diagnostics",
        ],
        "not_based_on_directly": [
            "raw card price alone",
            "rarity labels alone",
            "subject desirability",
        ],
    }


def write_outputs(report: Dict[str, Any], *, output_dir: Path) -> Dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    audit_csv = output_dir / f"desirability_v2_chase_definition_audit_{timestamp}.csv"
    audit_json = output_dir / f"desirability_v2_chase_definition_audit_{timestamp}.json"
    corr_csv = output_dir / f"desirability_v2_variant_correlations_{timestamp}.csv"
    focused_csv = output_dir / f"desirability_v2_focused_variant_comparison_{timestamp}.csv"
    recommendation_md = output_dir / f"desirability_v2_variant_recommendation_{timestamp}.md"

    audit_fields = [
        "set_name",
        "set_canonical_key",
        *VARIANT_FIELDS,
        *[f"{field}_rank" for field in VARIANT_FIELDS],
        *COMPONENT_FIELDS,
        *FINANCIAL_METRIC_FIELDS,
        "market_salient_card_count",
        "market_salient_captured_count",
        "market_salient_promotion_count",
        "card_appeal_canonical_count",
        "card_appeal_priced_count",
        "card_appeal_linked_count",
        "card_appeal_scored_linked_count",
        "card_appeal_included_count",
        "card_appeal_excluded_unpriced_count",
        "card_appeal_excluded_unlinked_count",
        "card_appeal_excluded_missing_score_count",
        "card_appeal_vs_market_price_n",
        "card_appeal_vs_market_price_pearson",
        "card_appeal_vs_market_price_spearman",
        "card_appeal_included_policy",
        "top_market_cards_json",
    ]
    with audit_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=audit_fields)
        writer.writeheader()
        for report_row in report["sets"]:
            row = {
                "set_name": report_row.get("set_name"),
                "set_canonical_key": report_row.get("set_canonical_key"),
            }
            row.update(report_row.get("variants", {}))
            row.update({f"{key}_rank": value for key, value in (report_row.get("variant_ranks") or {}).items()})
            row.update({field: report_row.get("current_v2", {}).get(field) for field in COMPONENT_FIELDS})
            row.update(report_row.get("financial_metrics", {}))
            cards = report_row.get("market_salient_cards") or []
            row["market_salient_card_count"] = len(cards)
            row["market_salient_captured_count"] = sum(1 for card in cards if card.get("captured_by_current_rarity_bucket_logic"))
            row["market_salient_promotion_count"] = sum(1 for card in cards if card.get("would_require_promotion_for_desirability_analysis"))
            card_appeal = report_row.get("card_appeal_market_price_correlation") or {}
            row.update(
                {
                    "card_appeal_canonical_count": card_appeal.get("canonical_count"),
                    "card_appeal_priced_count": card_appeal.get("priced_count"),
                    "card_appeal_linked_count": card_appeal.get("linked_count"),
                    "card_appeal_scored_linked_count": card_appeal.get("scored_linked_count"),
                    "card_appeal_included_count": card_appeal.get("included_count"),
                    "card_appeal_excluded_unpriced_count": card_appeal.get("excluded_unpriced_count"),
                    "card_appeal_excluded_unlinked_count": card_appeal.get("excluded_unlinked_count"),
                    "card_appeal_excluded_missing_score_count": card_appeal.get("excluded_missing_score_count"),
                    "card_appeal_vs_market_price_n": card_appeal.get("n"),
                    "card_appeal_vs_market_price_pearson": card_appeal.get("pearson"),
                    "card_appeal_vs_market_price_spearman": card_appeal.get("spearman"),
                    "card_appeal_included_policy": card_appeal.get("included_policy"),
                }
            )
            row["top_market_cards_json"] = json.dumps(cards[:10], ensure_ascii=False)
            writer.writerow({field: _csv_value(row.get(field)) for field in audit_fields})

    with audit_json.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, default=str)

    corr_fields = ["variant", "metric", "n", "pearson", "spearman", "interpretation"]
    with corr_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=corr_fields)
        writer.writeheader()
        for row in report["correlations"]:
            writer.writerow({field: _csv_value(row.get(field)) for field in corr_fields})

    focused_fields = sorted({key for row in report["focused"] for key in row.keys()})
    with focused_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=focused_fields)
        writer.writeheader()
        for row in report["focused"]:
            writer.writerow({field: _csv_value(row.get(field)) for field in focused_fields})

    recommendation_md.write_text(report["recommendation_markdown"], encoding="utf-8")

    return {
        "audit_csv": audit_csv,
        "audit_json": audit_json,
        "correlations_csv": corr_csv,
        "focused_csv": focused_csv,
        "recommendation_md": recommendation_md,
    }


def _paged_select(query: Any, *, page_size: int = 1000) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    start = 0
    while True:
        response = query.range(start, start + page_size - 1).execute()
        page_rows = list(response.data or [])
        rows.extend(page_rows)
        if len(page_rows) < page_size:
            break
        start += page_size
    return rows


def _latest_by_set_id(rows: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    latest: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        set_id = str(row.get("set_id") or "")
        if not set_id:
            continue
        current = latest.get(set_id)
        row_time = str(row.get("built_at") or row.get("run_at") or row.get("updated_at") or "")
        current_time = str((current or {}).get("built_at") or (current or {}).get("run_at") or (current or {}).get("updated_at") or "")
        if current is None or row_time > current_time:
            latest[set_id] = row
    return latest


def _group_by(rows: Sequence[Dict[str, Any]], key: str) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        value = row.get(key)
        if value is not None:
            grouped[str(value)].append(row)
    return grouped


def _chunked(values: Sequence[str], size: int) -> Iterable[List[str]]:
    for index in range(0, len(values), size):
        yield list(values[index : index + size])


def _as_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _jsonish(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return value


def _norm(value: Any) -> str:
    return "".join(ch.lower() for ch in str(value or "") if ch.isalnum())


def _strip_parenthetical(value: Any) -> str:
    text = str(value or "").strip()
    while "(" in text and ")" in text and text.rfind("(") < text.rfind(")"):
        start = text.rfind("(")
        end = text.rfind(")")
        text = (text[:start] + text[end + 1 :]).strip()
    return text


def _normalize_0_100(value: Optional[float], min_value: float, max_value: float) -> Optional[float]:
    if value is None or not math.isfinite(value):
        return None
    if max_value <= min_value:
        return None
    return _cap_score(100.0 * ((value - min_value) / (max_value - min_value)))


def _cap_score(value: float) -> float:
    return round(max(0.0, min(100.0, float(value))), 4)


def _blend(left: Optional[float], right: Optional[float], left_weight: float, right_weight: float) -> Optional[float]:
    if left is None or right is None:
        return None
    return _cap_score(left * left_weight + right * right_weight)


def _delta(value: Optional[float], baseline: Optional[float]) -> Optional[float]:
    if value is None or baseline is None:
        return None
    return round(value - baseline, 4)


def _pearson(pairs: Sequence[Tuple[float, float]]) -> Optional[float]:
    if len(pairs) < 3:
        return None
    xs = [pair[0] for pair in pairs]
    ys = [pair[1] for pair in pairs]
    corr = _correlation(xs, ys)
    return round(corr, 6) if corr is not None else None


def _correlation(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    denom_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    denom_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    denominator = denom_x * denom_y
    if denominator <= 0:
        return None
    return numerator / denominator


def _spearman(pairs: Sequence[Tuple[float, float]]) -> Optional[float]:
    if len(pairs) < 3:
        return None
    ranked_x = _rank_values([pair[0] for pair in pairs])
    ranked_y = _rank_values([pair[1] for pair in pairs])
    corr = _correlation(ranked_x, ranked_y)
    return round(corr, 6) if corr is not None else None


def _rank_values(values: Sequence[float]) -> List[float]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(indexed):
        end = index
        while end + 1 < len(indexed) and indexed[end + 1][1] == indexed[index][1]:
            end += 1
        avg_rank = (index + 1 + end + 1) / 2.0
        for ranked_index in range(index, end + 1):
            original_index = indexed[ranked_index][0]
            ranks[original_index] = avg_rank
        index = end + 1
    return ranks


def _correlation_interpretation(value: Optional[float]) -> str:
    if value is None:
        return "insufficient_data"
    if value < 0.50:
        return "healthy_separation"
    if value <= 0.70:
        return "watch_carefully"
    return "likely_overlap"


def _max_variant_corr(correlations: Sequence[Dict[str, Any]], variant: str) -> Optional[Dict[str, Any]]:
    rows = [row for row in correlations if row.get("variant") == variant and row.get("pearson") is not None]
    if not rows:
        return None
    best = max(
        rows,
        key=lambda row: max(abs(_as_float(row.get("pearson")) or 0.0), abs(_as_float(row.get("spearman")) or 0.0)),
    )
    return {
        "metric": best.get("metric"),
        "pearson": best.get("pearson"),
        "spearman": best.get("spearman"),
        "max_abs_correlation": max(abs(_as_float(best.get("pearson")) or 0.0), abs(_as_float(best.get("spearman")) or 0.0)),
        "interpretation": best.get("interpretation"),
    }


def _fmt_corr_summary(row: Optional[Dict[str, Any]]) -> str:
    if not row:
        return "insufficient data"
    return (
        f"{row.get('metric')} pearson={row.get('pearson')} "
        f"spearman={row.get('spearman')} ({row.get('interpretation')})"
    )


def _csv_value(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return value


if __name__ == "__main__":
    raise SystemExit(main())
