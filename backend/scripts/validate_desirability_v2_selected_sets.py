from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.desirability.composite import COMPOSITE_SCORING_VERSION  # noqa: E402
from backend.desirability.rarity_buckets import BUCKET_PRIORITY, HIT_POLICY_VERSION  # noqa: E402
from backend.desirability.set_components import (  # noqa: E402
    SCORING_VERSION,
    build_canonical_card_price_index,
    build_card_appeal_coverage_diagnostics,
)


V2_TABLE = "pokemon_set_desirability_component_scores"
DEFAULT_TARGET_SET_KEYS = [
    "prismaticEvolutions",
    "ascendedHeroes",
    "scarletAndViolet151",
    "evolvingSkies",
    "paldeanFates",
    "whiteFlare",
    "blackBolt",
    "celebrations",
    "celebrationsClassicCollection",
    "legendaryCollection",
    "base",
    "skyridge",
    "shroudedFable",
]

COMPONENT_FIELDS = [
    "chase_subject_strength",
    "chase_subject_depth",
    "accessible_favorite_hits",
    "special_pack_chase_appeal",
]

COVERAGE_AUDIT_FIELDS = [
    "canonical_card_count",
    "hit_like_card_count",
    "pokemon_linked_hit_count",
    "non_pokemon_hit_count",
    "unknown_rarity_count",
    "premium_chase_count",
    "major_hit_count",
    "accessible_hit_count",
    "rarity_override_count",
]

CARD_APPEAL_COVERAGE_FIELDS = [
    "canonical_count",
    "priced_count",
    "linked_count",
    "scored_linked_count",
    "included_count",
    "excluded_unpriced_count",
    "excluded_unlinked_count",
    "excluded_missing_score_count",
    "included_policy",
]

SET_KEY_COMPAT_ALIASES = {
    "scarletandviolet": "scarletAndVioletBase",
}


class DesirabilityV2ValidationError(RuntimeError):
    pass


class DesirabilityV2ValidationRepository:
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
            self.client.table(V2_TABLE)
            .select(
                "set_id,set_name,set_canonical_key,scoring_version,hit_policy_version,"
                "composite_scoring_version,fan_popularity_snapshot_id,current_trend_snapshot_ids,"
                "config_fingerprint,set_desirability_score,chase_subject_strength,"
                "chase_subject_depth,accessible_favorite_hits,special_pack_chase_appeal,"
                "hit_eligible_card_count,scored_hit_eligible_card_count,unique_subject_count,"
                "duplicate_subject_count,premium_chase_subject_count,major_hit_subject_count,"
                "accessible_hit_count,trainer_hit_count,unmatched_hit_count,top_subjects_json,"
                "subject_rollups_json,rarity_bucket_counts_json,special_pack_summary_json,"
                "component_inputs_json,diagnostics_json,warnings_json,built_at,updated_at"
            )
            .eq("scoring_version", scoring_version)
            .eq("hit_policy_version", hit_policy_version)
            .eq("composite_scoring_version", composite_scoring_version)
            .order("built_at", desc=True)
        )

    def list_sets_by_keys(self, canonical_keys: Sequence[str]) -> List[Dict[str, Any]]:
        keys = [str(key) for key in canonical_keys if key]
        if not keys:
            return []
        return _paged_select(
            self.client.table("sets")
            .select("id,name,canonical_key")
            .in_("canonical_key", keys)
        )

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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only Desirability V2 audit for selected Pokemon sets."
    )
    parser.add_argument(
        "--sets",
        nargs="+",
        default=DEFAULT_TARGET_SET_KEYS,
        help="sets.canonical_key values to audit. Defaults to the curated V2 validation list.",
    )
    parser.add_argument("--scoring-version", default=SCORING_VERSION)
    parser.add_argument("--hit-policy-version", default=HIT_POLICY_VERSION)
    parser.add_argument("--composite-scoring-version", default=COMPOSITE_SCORING_VERSION)
    parser.add_argument(
        "--output-dir",
        default="logs",
        help="Directory for desirability_v2_validation_<timestamp>.csv/json outputs.",
    )
    return parser


def load_backend_env() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    load_dotenv(env_path, override=False)


def main() -> int:
    args = build_parser().parse_args()
    load_backend_env()
    report = build_validation_report(
        repository=DesirabilityV2ValidationRepository(),
        target_set_keys=args.sets,
        scoring_version=args.scoring_version,
        hit_policy_version=args.hit_policy_version,
        composite_scoring_version=args.composite_scoring_version,
    )
    print(format_terminal_table(report["rows"]))
    csv_path, json_path = write_outputs(report, output_dir=Path(args.output_dir))
    print(f"\nCSV written: {csv_path}")
    print(f"JSON written: {json_path}")
    return 1 if report["missing_set_keys"] else 0


def build_validation_report(
    *,
    repository: Any,
    target_set_keys: Sequence[str],
    scoring_version: str,
    hit_policy_version: str,
    composite_scoring_version: str,
) -> Dict[str, Any]:
    raw_rows = repository.list_v2_rows(
        scoring_version=scoring_version,
        hit_policy_version=hit_policy_version,
        composite_scoring_version=composite_scoring_version,
    )
    latest_by_set = _latest_by_set(raw_rows)
    ranks = _rank_rows(latest_by_set.values())
    latest_by_key = {
        str(row.get("set_canonical_key") or "").lower(): row
        for row in latest_by_set.values()
        if row.get("set_canonical_key")
    }
    set_rows_by_key = _set_rows_by_key(repository, target_set_keys)
    target_v2_rows = []
    for set_key in target_set_keys:
        row = _first_matching_key(latest_by_key, set_key)
        if row:
            target_v2_rows.append(row)
    coverage_identity_rows = list(target_v2_rows)
    v2_set_ids = {str(row.get("set_id")) for row in target_v2_rows if row.get("set_id") is not None}
    for set_key in target_set_keys:
        set_row = set_rows_by_key.get(str(set_key).lower())
        if set_row and str(set_row.get("id")) not in v2_set_ids:
            coverage_identity_rows.append({"set_id": set_row.get("id")})
    card_appeal_coverage_by_set = _card_appeal_coverage_by_set(
        repository=repository,
        rows=coverage_identity_rows,
        composite_scoring_version=composite_scoring_version,
    )

    rows: List[Dict[str, Any]] = []
    missing_set_keys: List[str] = []
    for set_key in target_set_keys:
        row = _first_matching_key(latest_by_key, set_key)
        if not row:
            set_row = _first_matching_key(set_rows_by_key, set_key)
            if not set_row:
                missing_set_keys.append(set_key)
            rows.append(
                _missing_row(
                    set_key,
                    set_row=set_row,
                    card_appeal_coverage=card_appeal_coverage_by_set.get(str((set_row or {}).get("id"))),
                )
            )
            continue
        rows.append(
            _audit_row(
                row,
                rank=ranks.get(str(row.get("set_id"))),
                card_appeal_coverage=card_appeal_coverage_by_set.get(str(row.get("set_id"))),
            )
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_table": V2_TABLE,
        "read_only": True,
        "scoring_version": scoring_version,
        "hit_policy_version": hit_policy_version,
        "composite_scoring_version": composite_scoring_version,
        "target_set_keys": list(target_set_keys),
        "v2_rows_loaded": len(raw_rows),
        "latest_v2_sets_ranked": len(latest_by_set),
        "missing_set_keys": missing_set_keys,
        "rows": rows,
    }


def format_terminal_table(rows: Sequence[Dict[str, Any]]) -> str:
    if not rows:
        return "No Desirability V2 validation rows found."
    headers = [
        "Set",
        "V2",
        "Rank",
        "Str",
        "Depth",
        "Access",
        "Spec",
        "Coverage",
        "Card Appeal",
        "Issue Signals",
        "Top Subjects",
    ]
    widths = [28, 7, 5, 6, 7, 7, 6, 31, 36, 34, 42]
    lines = [" ".join(header.ljust(width) for header, width in zip(headers, widths))]
    lines.append(" ".join("-" * width for width in widths))
    for row in rows:
        coverage = row.get("coverage_audit_summary") or {}
        card_appeal = row.get("card_appeal_coverage_diagnostics") or {}
        values = [
            str(row.get("set_name") or row.get("set_canonical_key") or "")[:28],
            _fmt(row.get("v2_score")),
            _rank(row.get("v2_rank")),
            _fmt(row.get("chase_subject_strength")),
            _fmt(row.get("chase_subject_depth")),
            _fmt(row.get("accessible_favorite_hits")),
            _fmt(row.get("special_pack_chase_appeal")),
            _coverage_summary(coverage)[:31],
            _card_appeal_summary(card_appeal)[:36],
            str(row.get("audit_issue_signals") or "")[:34],
            ", ".join(subject.get("subject_name") or "" for subject in row.get("top_10_subject_rollups") or [])[:42],
        ]
        lines.append(" ".join(value.ljust(width) for value, width in zip(values, widths)))

    return "\n".join(lines)


def write_outputs(report: Dict[str, Any], *, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    csv_path = output_dir / f"desirability_v2_validation_{timestamp}.csv"
    json_path = output_dir / f"desirability_v2_validation_{timestamp}.json"
    write_csv(report["rows"], csv_path)
    json_path.write_text(json.dumps(_jsonable(report), indent=2, sort_keys=True), encoding="utf-8")
    return csv_path, json_path


def write_csv(rows: Sequence[Dict[str, Any]], path: Path) -> None:
    fieldnames = [
        "set_name",
        "set_canonical_key",
        "v2_score",
        "v2_rank",
        *COMPONENT_FIELDS,
        "top_10_subject_rollups_json",
        "rarity_bucket_counts_json",
        "hit_link_category_counts_json",
        "warning_summary",
        "warnings_json",
        "audit_issue_signals",
        *COVERAGE_AUDIT_FIELDS,
        *[f"card_appeal_{field}" for field in CARD_APPEAL_COVERAGE_FIELDS],
        "top_hit_like_rows_json",
        "built_at",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            coverage = row.get("coverage_audit_summary") or {}
            card_appeal = row.get("card_appeal_coverage_diagnostics") or {}
            payload = {
                **{field: row.get(field) for field in fieldnames},
                "top_10_subject_rollups_json": json.dumps(
                    _jsonable(row.get("top_10_subject_rollups") or []),
                    sort_keys=True,
                ),
                "rarity_bucket_counts_json": json.dumps(
                    _jsonable(row.get("rarity_bucket_counts_json") or {}),
                    sort_keys=True,
                ),
                "hit_link_category_counts_json": json.dumps(
                    _jsonable(row.get("hit_link_category_counts") or {}),
                    sort_keys=True,
                ),
                "warnings_json": json.dumps(_jsonable(row.get("warnings") or []), sort_keys=True),
                "top_hit_like_rows_json": json.dumps(
                    _jsonable(coverage.get("top_hit_like_rows") or []),
                    sort_keys=True,
                ),
            }
            for field in COVERAGE_AUDIT_FIELDS:
                payload[field] = coverage.get(field)
            for field in CARD_APPEAL_COVERAGE_FIELDS:
                payload[f"card_appeal_{field}"] = card_appeal.get(field)
            writer.writerow({field: payload.get(field) for field in fieldnames})


def _card_appeal_coverage_by_set(
    *,
    repository: Any,
    rows: Sequence[Dict[str, Any]],
    composite_scoring_version: str,
) -> Dict[str, Dict[str, Any]]:
    set_ids = sorted({str(row.get("set_id")) for row in rows if row.get("set_id") is not None})
    if not set_ids:
        return {}
    required_methods = (
        "list_canonical_cards",
        "list_card_links",
        "list_composite_scores",
        "list_legacy_cards",
        "list_card_variants",
        "get_near_mint_condition_id",
        "list_latest_price_rows",
    )
    if not all(hasattr(repository, method) for method in required_methods):
        return {}

    canonical_cards = repository.list_canonical_cards(set_ids)
    links = repository.list_card_links([str(card.get("id")) for card in canonical_cards if card.get("id") is not None])
    composite_scores = repository.list_composite_scores(scoring_version=composite_scoring_version)
    legacy_cards = repository.list_legacy_cards(set_ids)
    variant_rows = repository.list_card_variants([str(card.get("id")) for card in legacy_cards if card.get("id") is not None])
    condition_id = repository.get_near_mint_condition_id()
    latest_price_rows = repository.list_latest_price_rows(
        [str(row.get("id")) for row in variant_rows if row.get("id") is not None],
        condition_id,
    )
    prices_by_card = build_canonical_card_price_index(
        canonical_cards=canonical_cards,
        legacy_cards=legacy_cards,
        variant_rows=variant_rows,
        latest_price_rows=latest_price_rows,
    )
    cards_by_set = _group_by(canonical_cards, "set_id")
    links_by_card = _group_by(links, "pokemon_canonical_card_id")
    scores_by_reference = {
        str(row.get("pokemon_reference_id")): row
        for row in composite_scores
        if row.get("pokemon_reference_id") is not None
    }

    diagnostics_by_set: Dict[str, Dict[str, Any]] = {}
    for set_id in set_ids:
        set_cards = cards_by_set.get(set_id, [])
        set_card_ids = {str(card.get("id")) for card in set_cards if card.get("id") is not None}
        diagnostics_by_set[set_id] = build_card_appeal_coverage_diagnostics(
            cards=set_cards,
            links=[link for card_id in set_card_ids for link in links_by_card.get(card_id, [])],
            scores_by_reference=scores_by_reference,
            prices_by_card={card_id: prices_by_card[card_id] for card_id in set_card_ids if card_id in prices_by_card},
        )
    return diagnostics_by_set


def _set_rows_by_key(repository: Any, target_set_keys: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    if not hasattr(repository, "list_sets_by_keys"):
        return {}
    rows = repository.list_sets_by_keys(_expanded_target_keys(target_set_keys))
    by_key = {
        str(row.get("canonical_key") or "").lower(): row
        for row in rows
        if row.get("canonical_key")
    }
    for requested_key in target_set_keys:
        row = _first_matching_key(by_key, requested_key)
        if row:
            by_key[str(requested_key).lower()] = row
    return by_key


def _first_matching_key(rows_by_key: Dict[str, Dict[str, Any]], key: Any) -> Optional[Dict[str, Any]]:
    for candidate in _target_key_candidates(key):
        row = rows_by_key.get(str(candidate).lower())
        if row:
            return row
    return None


def _expanded_target_keys(keys: Sequence[str]) -> List[str]:
    expanded: List[str] = []
    for key in keys:
        for candidate in _target_key_candidates(key):
            if candidate not in expanded:
                expanded.append(candidate)
    return expanded


def _target_key_candidates(key: Any) -> List[str]:
    text = str(key or "").strip()
    if not text:
        return []
    candidates = [text]
    alias = SET_KEY_COMPAT_ALIASES.get(text.lower())
    if alias and alias not in candidates:
        candidates.append(alias)
    return candidates


def _audit_row(row: Dict[str, Any], *, rank: Optional[int], card_appeal_coverage: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    diagnostics = row.get("diagnostics_json") if isinstance(row.get("diagnostics_json"), dict) else {}
    coverage_audit = diagnostics.get("coverage_audit") if isinstance(diagnostics, dict) else {}
    if not isinstance(coverage_audit, dict):
        coverage_audit = {}
    hit_link_counts = diagnostics.get("hit_link_category_counts") if isinstance(diagnostics, dict) else {}
    if not isinstance(hit_link_counts, dict):
        hit_link_counts = {}

    warnings = row.get("warnings_json") if isinstance(row.get("warnings_json"), list) else []
    top_subjects = _top_subject_rollups(row.get("subject_rollups_json") or [], limit=10)
    coverage_summary = {
        field: coverage_audit.get(field)
        for field in COVERAGE_AUDIT_FIELDS
    }
    coverage_summary["top_hit_like_rows"] = coverage_audit.get("top_hit_like_rows") or []
    card_appeal_summary = {
        field: (card_appeal_coverage or {}).get(field)
        for field in CARD_APPEAL_COVERAGE_FIELDS
    }

    return {
        "set_name": row.get("set_name"),
        "set_canonical_key": row.get("set_canonical_key"),
        "v2_score": _float_or_none(row.get("set_desirability_score")),
        "v2_rank": rank,
        "chase_subject_strength": _float_or_none(row.get("chase_subject_strength")),
        "chase_subject_depth": _float_or_none(row.get("chase_subject_depth")),
        "accessible_favorite_hits": _float_or_none(row.get("accessible_favorite_hits")),
        "special_pack_chase_appeal": _float_or_none(row.get("special_pack_chase_appeal")),
        "top_10_subject_rollups": top_subjects,
        "rarity_bucket_counts_json": row.get("rarity_bucket_counts_json") or {},
        "hit_link_category_counts": {str(key): int(value or 0) for key, value in sorted(hit_link_counts.items())},
        "warning_summary": _warning_summary(warnings, hit_link_counts, coverage_audit),
        "warnings": warnings,
        "audit_issue_signals": _audit_issue_signals(hit_link_counts, coverage_audit),
        "coverage_audit_summary": coverage_summary,
        "card_appeal_coverage_diagnostics": card_appeal_summary,
        "built_at": row.get("built_at"),
        "source": {
            "set_id": row.get("set_id"),
            "fan_popularity_snapshot_id": row.get("fan_popularity_snapshot_id"),
            "current_trend_snapshot_ids": row.get("current_trend_snapshot_ids"),
            "config_fingerprint": row.get("config_fingerprint"),
            "diagnostics_json": diagnostics,
            "component_inputs_json": row.get("component_inputs_json") or {},
            "special_pack_summary_json": row.get("special_pack_summary_json") or {},
        },
    }


def _top_subject_rollups(value: Any, *, limit: int) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows = [row for row in value if isinstance(row, dict)]
    rows.sort(key=_subject_sort_key, reverse=True)
    return [
        {
            "subject_name": row.get("subject_name"),
            "max_desirability_score": _float_or_none(row.get("max_desirability_score")),
            "best_rarity_bucket": row.get("best_rarity_bucket"),
            "representative_card_name": row.get("representative_card_name"),
            "representative_rarity": row.get("representative_rarity"),
            "premium_chase_card_count": int(row.get("premium_chase_card_count") or 0),
            "major_hit_card_count": int(row.get("major_hit_card_count") or 0),
            "accessible_hit_card_count": int(row.get("accessible_hit_card_count") or 0),
            "rarity_buckets_present": row.get("rarity_buckets_present") or [],
        }
        for row in rows[:limit]
    ]


def _subject_sort_key(row: Dict[str, Any]) -> tuple[Any, ...]:
    return (
        _float_or_none(row.get("max_desirability_score")) or -1.0,
        BUCKET_PRIORITY.get(str(row.get("best_rarity_bucket")), 0),
        int(row.get("premium_chase_card_count") or 0),
        int(row.get("major_hit_card_count") or 0),
        int(row.get("accessible_hit_card_count") or 0),
        str(row.get("subject_name") or ""),
    )


def _warning_summary(
    warnings: Sequence[Any],
    hit_link_counts: Dict[str, Any],
    coverage_audit: Dict[str, Any],
) -> str:
    parts: List[str] = []
    if warnings:
        parts.append("; ".join(str(item) for item in warnings))
    signal_counts = {
        "unknown_rarity": coverage_audit.get("unknown_rarity_count"),
        "unsupported_subject_hit": hit_link_counts.get("unsupported_subject_hit_count"),
        "unmatched_pokemon_hit": hit_link_counts.get("unmatched_pokemon_hit_count"),
        "true_missing_link": hit_link_counts.get("true_missing_link_count"),
        "unknown_or_unclassified_hit": hit_link_counts.get("unknown_or_unclassified_hit_count"),
    }
    non_zero = _compact_counts({key: value for key, value in signal_counts.items() if int(value or 0)})
    if non_zero:
        parts.append(non_zero)
    return " | ".join(parts) if parts else "no actionable warnings"


def _audit_issue_signals(hit_link_counts: Dict[str, Any], coverage_audit: Dict[str, Any]) -> str:
    missing_link_count = int(hit_link_counts.get("unmatched_pokemon_hit_count") or 0) + int(
        hit_link_counts.get("true_missing_link_count") or 0
    )
    signals = {
        "unk_rarity": coverage_audit.get("unknown_rarity_count"),
        "missing_link": missing_link_count,
        "unsupported": hit_link_counts.get("unsupported_subject_hit_count"),
        "non_pokemon": hit_link_counts.get("expected_non_pokemon_hit_count"),
    }
    non_zero = {key: value for key, value in signals.items() if int(value or 0)}
    return _compact_counts(non_zero) if non_zero else "none"


def _coverage_summary(coverage: Dict[str, Any]) -> str:
    return (
        f"c={_dash(coverage.get('canonical_card_count'))} "
        f"h={_dash(coverage.get('hit_like_card_count'))} "
        f"l={_dash(coverage.get('pokemon_linked_hit_count'))} "
        f"unk={_dash(coverage.get('unknown_rarity_count'))} "
        f"ovr={_dash(coverage.get('rarity_override_count'))}"
    )


def _card_appeal_summary(coverage: Dict[str, Any]) -> str:
    return (
        f"c={_dash(coverage.get('canonical_count'))} "
        f"p={_dash(coverage.get('priced_count'))} "
        f"l={_dash(coverage.get('linked_count'))} "
        f"s={_dash(coverage.get('scored_linked_count'))} "
        f"incl={_dash(coverage.get('included_count'))} "
        f"no$={_dash(coverage.get('excluded_unpriced_count'))} "
        f"nolink={_dash(coverage.get('excluded_unlinked_count'))} "
        f"noscore={_dash(coverage.get('excluded_missing_score_count'))}"
    )


def _missing_row(
    set_key: str,
    *,
    set_row: Optional[Dict[str, Any]] = None,
    card_appeal_coverage: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    card_appeal_summary = {
        field: (card_appeal_coverage or {}).get(field)
        for field in CARD_APPEAL_COVERAGE_FIELDS
    }
    return {
        "set_name": (set_row or {}).get("name"),
        "set_canonical_key": (set_row or {}).get("canonical_key") or set_key,
        "v2_score": None,
        "v2_rank": None,
        "chase_subject_strength": None,
        "chase_subject_depth": None,
        "accessible_favorite_hits": None,
        "special_pack_chase_appeal": None,
        "top_10_subject_rollups": [],
        "rarity_bucket_counts_json": {},
        "hit_link_category_counts": {},
        "warning_summary": "missing latest V2 component row for requested set",
        "warnings": ["missing latest V2 component row for requested set"],
        "audit_issue_signals": "missing_v2_row=1",
        "coverage_audit_summary": {},
        "card_appeal_coverage_diagnostics": card_appeal_summary,
        "built_at": None,
        "source": {"set_id": (set_row or {}).get("id")} if set_row else {},
    }


def _latest_by_set(rows: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    latest: Dict[str, Dict[str, Any]] = {}
    for row in sorted(rows, key=_built_at_sort_key, reverse=True):
        set_id = str(row.get("set_id") or "")
        if set_id and set_id not in latest:
            latest[set_id] = row
    return latest


def _rank_rows(rows: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    ranked = [
        row
        for row in rows
        if row.get("set_id") is not None and _float_or_none(row.get("set_desirability_score")) is not None
    ]
    ranked.sort(key=lambda item: _float_or_none(item.get("set_desirability_score")) or 0.0, reverse=True)
    return {str(row["set_id"]): index for index, row in enumerate(ranked, start=1)}


def _built_at_sort_key(row: Dict[str, Any]) -> tuple[str, str]:
    return (str(row.get("built_at") or ""), str(row.get("updated_at") or ""))


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


def _group_by(rows: Sequence[Dict[str, Any]], key: str) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        value = row.get(key)
        if value is not None:
            grouped.setdefault(str(value), []).append(row)
    return grouped


def _chunked(values: Sequence[str], size: int) -> Iterable[List[str]]:
    for index in range(0, len(values), size):
        yield list(values[index : index + size])


def _fmt(value: Any) -> str:
    parsed = _float_or_none(value)
    return "-" if parsed is None else f"{parsed:.1f}"


def _rank(value: Any) -> str:
    return "-" if value is None else str(value)


def _dash(value: Any) -> str:
    return "-" if value is None else str(value)


def _compact_counts(counts: Dict[str, Any]) -> str:
    return "; ".join(f"{key}={int(value or 0)}" for key, value in sorted(counts.items()))


def _float_or_none(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, set):
        return sorted(_jsonable(item) for item in value)
    return value


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DesirabilityV2ValidationError as exc:
        print(f"[desirability-v2-validation][ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)
