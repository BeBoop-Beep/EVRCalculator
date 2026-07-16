from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import logging
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.desirability.composite import COMPOSITE_SCORING_VERSION  # noqa: E402
from backend.desirability.product_support import (  # noqa: E402
    PARTIAL_BOOSTER_SET,
    PRODUCT_SUPPORT_VERSION,
    classify_product_support,
)
from backend.desirability.rankability import RANKABLE_STATUSES  # noqa: E402
from backend.desirability.rarity_buckets import HIT_POLICY_VERSION  # noqa: E402
from backend.desirability.set_components import (  # noqa: E402
    SCORING_VERSION,
    build_card_facts,
    build_set_coverage_audit,
    collapse_subject_rollups,
    compute_component_scores,
    compute_counts,
)
from backend.scripts.build_pokemon_set_hit_desirability_summaries import (  # noqa: E402
    describe_composite_score_groups,
    select_latest_complete_composite_score_group,
)
from backend.scripts.run_pokemon_set_scrape import (  # noqa: E402
    build_valid_set_key_registry,
    normalize_set_key_filter,
)


logger = logging.getLogger(__name__)

COMPONENT_TABLE = "pokemon_set_desirability_component_scores"
LINK_TABLE = "pokemon_card_desirability_links"
UPSERT_BATCH_SIZE = 25

# v2: product support is classified from set metadata BEFORE any data-quality
# check, so fixed-contents products are reported as unsupported_product_type
# instead of being misdiagnosed as unavailable_missing_rarity. Reason codes
# renamed accordingly (missing_rarity -> missing_rarity_mapping; a supported
# booster set with no hit ladder is now no_eligible_hit_structure).
METRIC_STATUS_VERSION = "set_metric_status_v2"
# Below this rarity/subject-link coverage a set's components are computed from
# too little of its checklist to be treated as a clean measurement.
PARTIAL_COVERAGE_THRESHOLD = 0.50
LEGACY_COVERAGE_AUDIT_SET_KEYS = frozenset(
    {
        "celebrations",
        "celebrationsClassicCollection",
        "legendaryCollection",
        "base",
        "fossil",
        "jungle",
        "gymChallenge",
        "gymHeroes",
        "expeditionBaseSet",
        "aquapolis",
        "skyridge",
        "hsTriumphant",
        "hsUndaunted",
        "majesticDawn",
        "rubyAndSapphire",
        "sandstorm",
        "arceus",
    }
)


class PokemonSetDesirabilityComponentsError(RuntimeError):
    pass


class PokemonSetDesirabilityComponentsRepository:
    def __init__(self, client: Optional[Any] = None):
        if client is None:
            from backend.db.clients.supabase_client import supabase

            client = supabase
        self.client = client

    def list_sets(self, *, set_id: Optional[str], canonical_key: Optional[str], limit: Optional[int]) -> List[Dict[str, Any]]:
        query = self.client.table("sets").select("id,name,canonical_key").order("name")
        if set_id:
            query = query.eq("id", set_id)
        if canonical_key:
            query = query.eq("canonical_key", canonical_key)
        if limit is not None:
            query = query.limit(int(limit))
        response = query.execute()
        return list(response.data or [])

    def list_pokemon_references(self) -> List[Dict[str, Any]]:
        return _paged_select(
            self.client.table("pokemon_reference")
            .select("id,pokedex_number,canonical_name,display_name")
            .order("pokedex_number")
        )

    def list_composite_scores(self, *, scoring_version: str) -> List[Dict[str, Any]]:
        return _paged_select(
            self.client.table("pokemon_desirability_composite_scores")
            .select(
                "id,pokemon_reference_id,pokedex_number,pokemon_name,"
                "fan_popularity_score,fan_popularity_rank,fan_popularity_snapshot_id,"
                "current_trend_score,current_trend_rank,current_trend_snapshot_id,"
                "desirability_score,desirability_rank,desirability_tier,"
                "scoring_version,created_at,updated_at"
            )
            .eq("scoring_version", scoring_version)
        )

    def list_canonical_cards(self, set_ids: Sequence[str]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for chunk in _chunked(list(set_ids), 200):
            rows.extend(
                _paged_select(
                    self.client.table("pokemon_canonical_cards")
                    .select(
                        "id,set_id,pokemon_tcg_api_card_id,name,supertype,subtypes,rarity,"
                        "number,printed_number,national_pokedex_numbers,image_small_url,image_large_url"
                    )
                    .in_("set_id", list(chunk))
                    .order("number")
                    .order("name")
                )
            )
        return rows

    def list_card_links(self, *, card_ids: Sequence[str]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for chunk in _chunked(list(card_ids), 200):
            rows.extend(
                _paged_select(
                    self.client.table(LINK_TABLE)
                    .select(
                        "id,pokemon_canonical_card_id,pokemon_reference_id,pokedex_number,"
                        "link_position,link_count,contribution_weight,match_method,"
                        "match_confidence,is_hit_eligible,hit_policy_version,source,notes"
                    )
                    .in_("pokemon_canonical_card_id", list(chunk))
                )
            )
        return rows

    def list_existing_component_scores(
        self,
        *,
        set_ids: Sequence[str],
        scoring_version: str,
        hit_policy_version: str,
        composite_scoring_version: str,
        fan_popularity_snapshot_id: Any,
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for chunk in _chunked(list(set_ids), 200):
            rows.extend(
                _paged_select(
                    self.client.table(COMPONENT_TABLE)
                    .select(
                        "id,set_id,scoring_version,hit_policy_version,"
                        "composite_scoring_version,fan_popularity_snapshot_id,config_fingerprint,"
                        "current_trend_snapshot_ids"
                    )
                    .in_("set_id", list(chunk))
                    .eq("scoring_version", scoring_version)
                    .eq("hit_policy_version", hit_policy_version)
                    .eq("composite_scoring_version", composite_scoring_version)
                    .eq("fan_popularity_snapshot_id", str(fan_popularity_snapshot_id))
                )
            )
        return rows

    def upsert_component_scores(self, rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        written: List[Dict[str, Any]] = []
        if not rows:
            return written
        on_conflict = (
            "set_id,scoring_version,hit_policy_version,composite_scoring_version,"
            "fan_popularity_snapshot_id,config_fingerprint"
        )
        for chunk in _chunked(list(rows), UPSERT_BATCH_SIZE):
            response = (
                self.client.table(COMPONENT_TABLE)
                .upsert(list(chunk), on_conflict=on_conflict)
                .execute()
            )
            written.extend(response.data or [])
        return written


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build Pokemon set Desirability V2 component scores.")
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument("--set-id", help="sets.id to process")
    selector.add_argument("--canonical-key", help="sets.canonical_key to process")
    selector.add_argument("--set-key", dest="canonical_key_alias", help="Alias for --canonical-key")

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Preview without writing rows")
    mode.add_argument("--commit", action="store_true", help="Write rows to Supabase")

    parser.add_argument("--limit", type=int, default=None)

    # Scheduled runs must use --rebuild-changed. A full rebuild is a manual,
    # deliberate act: it rewrites every set row against the current sources.
    rebuild = parser.add_mutually_exclusive_group()
    rebuild.add_argument(
        "--rebuild-changed",
        action="store_true",
        help="Rebuild only sets whose desirability inputs changed (THE DEFAULT).",
    )
    rebuild.add_argument(
        "--rebuild-all",
        action="store_true",
        help="Rebuild every selected set regardless of input changes. Manual use only.",
    )
    rebuild.add_argument("--force", action="store_true", help="Deprecated alias for --rebuild-all.")
    parser.add_argument("--scoring-version", default=SCORING_VERSION)
    parser.add_argument("--hit-policy-version", default=HIT_POLICY_VERSION)
    parser.add_argument("--composite-scoring-version", default=COMPOSITE_SCORING_VERSION)
    parser.add_argument("--min-composite-coverage", type=float, default=0.95)
    parser.add_argument("--log-level", default="INFO")
    return parser


def load_backend_env() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    load_dotenv(env_path, override=False)


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    load_backend_env()

    dry_run = not args.commit
    if args.dry_run:
        dry_run = True

    canonical_key = args.canonical_key or args.canonical_key_alias
    report = build_component_scores_report(
        repository=PokemonSetDesirabilityComponentsRepository(),
        set_id=args.set_id,
        canonical_key=canonical_key,
        limit=args.limit,
        force=bool(args.rebuild_all or args.force),
        scoring_version=args.scoring_version,
        hit_policy_version=args.hit_policy_version,
        composite_scoring_version=args.composite_scoring_version,
        min_composite_coverage=args.min_composite_coverage,
        dry_run=dry_run,
    )
    print(_format_summary_table(report))
    print(json.dumps(_jsonable(report), indent=2, sort_keys=True))
    return 0 if report.get("status") in {"dry_run", "committed"} else 1


def build_component_scores_report(
    *,
    repository: Any,
    set_id: Optional[str],
    canonical_key: Optional[str],
    limit: Optional[int],
    force: bool,
    scoring_version: str,
    hit_policy_version: str,
    composite_scoring_version: str,
    min_composite_coverage: float,
    dry_run: bool,
) -> Dict[str, Any]:
    registry = build_valid_set_key_registry()
    resolved_key = None
    if canonical_key:
        resolution = normalize_set_key_filter(canonical_key, registry)
        resolved_key = resolution.get("resolved_set_key_filter")
        if not resolved_key:
            raise PokemonSetDesirabilityComponentsError(f"Unknown canonical key {canonical_key!r}")

    references = repository.list_pokemon_references()
    reference_count = len({row.get("id") for row in references if row.get("id") is not None})
    composite_rows = repository.list_composite_scores(scoring_version=composite_scoring_version)
    selection = select_latest_complete_composite_score_group(
        composite_rows=composite_rows,
        reference_count=reference_count,
        scoring_version=composite_scoring_version,
        min_coverage=min_composite_coverage,
    )
    if selection is None:
        return {
            "status": "missing_acceptable_composite_score_group",
            "dry_run": dry_run,
            "scoring_version": scoring_version,
            "hit_policy_version": hit_policy_version,
            "composite_scoring_version": composite_scoring_version,
            "candidate_composite_groups": describe_composite_score_groups(
                composite_rows=composite_rows,
                reference_count=reference_count,
                scoring_version=composite_scoring_version,
            ),
        }

    sets = repository.list_sets(set_id=set_id, canonical_key=resolved_key, limit=limit)
    if not sets:
        return {
            "status": "no_sets_found",
            "dry_run": dry_run,
            "requested_set_id": set_id,
            "requested_canonical_key": canonical_key,
            "resolved_canonical_key": resolved_key,
        }

    set_by_id = {str(row["id"]): row for row in sets if row.get("id") is not None}
    cards = repository.list_canonical_cards(sorted(set_by_id.keys()))
    cards_by_set: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for card in cards:
        set_row = set_by_id.get(str(card.get("set_id"))) or {}
        card["set_name"] = set_row.get("name")
        card["set_canonical_key"] = set_row.get("canonical_key")
        cards_by_set[str(card.get("set_id"))].append(card)

    card_ids = [str(card.get("id")) for card in cards if card.get("id") is not None]
    links = repository.list_card_links(card_ids=card_ids)
    links_by_card: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for link in links:
        links_by_card[str(link.get("pokemon_canonical_card_id"))].append(link)

    scores_by_reference = {
        int(row["pokemon_reference_id"]): row
        for row in selection["rows"]
        if row.get("pokemon_reference_id") is not None
    }
    references_by_pokedex = {
        int(row["pokedex_number"]): row
        for row in references
        if row.get("pokedex_number") is not None
    }

    config_map = registry.get("config_map", {})
    built_at = datetime.now(timezone.utc).isoformat()
    rows = []
    for set_row in sets:
        set_cards = cards_by_set.get(str(set_row.get("id")), [])
        set_links = [
            link
            for card in set_cards
            for link in links_by_card.get(str(card.get("id")), [])
        ]
        rows.append(
            build_set_component_score_row(
                set_row=set_row,
                cards=set_cards,
                links=set_links,
                scores_by_reference=scores_by_reference,
                references_by_pokedex=references_by_pokedex,
                set_config=config_map.get(set_row.get("canonical_key")),
                scoring_version=scoring_version,
                hit_policy_version=hit_policy_version,
                composite_scoring_version=composite_scoring_version,
                composite_metadata=selection["metadata"],
                built_at=built_at,
            )
        )

    existing_rows = []
    if rows and not dry_run:
        existing_rows = repository.list_existing_component_scores(
            set_ids=[str(row["set_id"]) for row in rows],
            scoring_version=scoring_version,
            hit_policy_version=hit_policy_version,
            composite_scoring_version=composite_scoring_version,
            fan_popularity_snapshot_id=selection["metadata"].get("fan_popularity_snapshot_id"),
        )
    existing_keys = {_source_identity_key(row) for row in existing_rows}
    rows_to_write = [
        row
        for row in rows
        if force or _source_identity_key(row) not in existing_keys
    ]
    insert_or_update_count = len(rows_to_write)
    skipped_existing_count = len(rows) - insert_or_update_count

    written_rows: List[Dict[str, Any]] = []
    if not dry_run:
        written_rows = repository.upsert_component_scores(rows_to_write)

    return {
        "status": "dry_run" if dry_run else "committed",
        "dry_run": dry_run,
        "requested_set_id": set_id,
        "requested_canonical_key": canonical_key,
        "resolved_canonical_key": resolved_key,
        "sets_loaded": len(sets),
        "canonical_cards_loaded": len(cards),
        "card_links_loaded": len(links),
        "rows_generated": len(rows),
        "rows_skipped_existing": skipped_existing_count,
        "rows_to_write": 0 if dry_run else insert_or_update_count,
        "written_rows_returned": len(written_rows),
        "force": force,
        "rebuild_mode": "rebuild_all" if force else "rebuild_changed",
        "staleness_key": "set_id + config_fingerprint + current_trend_snapshot_ids",
        "scoring_version": scoring_version,
        "hit_policy_version": hit_policy_version,
        "composite_scoring_version": composite_scoring_version,
        "selected_composite_group": selection["metadata"],
        "summary_rows": _summary_rows(rows),
        "legacy_coverage_audit_rows": _legacy_coverage_audit_rows(rows),
        "zero_or_near_zero_rows": _zero_or_near_zero_rows(rows),
        "warning_category_counts": _warning_category_counts(rows),
        "metric_status_counts": _metric_status_counts(rows),
        "unrankable_sets": _unrankable_sets(rows),
    }


def build_set_component_score_row(
    *,
    set_row: Dict[str, Any],
    cards: Sequence[Dict[str, Any]],
    links: Sequence[Dict[str, Any]],
    scores_by_reference: Dict[int, Dict[str, Any]],
    references_by_pokedex: Optional[Dict[int, Dict[str, Any]]] = None,
    set_config: Any = None,
    scoring_version: str,
    hit_policy_version: str,
    composite_scoring_version: str,
    composite_metadata: Dict[str, Any],
    built_at: str,
) -> Dict[str, Any]:
    card_facts, fact_warnings = build_card_facts(
        cards=cards,
        links=links,
        scores_by_reference=scores_by_reference,
        references_by_pokedex=references_by_pokedex,
    )
    rollups = collapse_subject_rollups(card_facts)
    components = compute_component_scores(subject_rollups=rollups, card_facts=card_facts, set_config=set_config)
    counts = compute_counts(card_facts=card_facts, subject_rollups=rollups)
    config_trace = _config_trace(set_config)
    warnings = sorted(set(fact_warnings + list(components.get("warnings_json") or [])))
    coverage_audit = build_set_coverage_audit(set_row=set_row, cards=cards, card_facts=card_facts)
    metric_status = build_metric_status(coverage_audit, set_row)
    if not metric_status["rankable"]:
        warnings = sorted(set(warnings + [f"{metric_status['metric_status']}: {metric_status['availability_reason']}"]))
    db_count_fields = {
        "hit_eligible_card_count",
        "scored_hit_eligible_card_count",
        "unique_subject_count",
        "duplicate_subject_count",
        "premium_chase_subject_count",
        "major_hit_subject_count",
        "accessible_hit_count",
        "trainer_hit_count",
        "unmatched_hit_count",
    }

    return {
        "set_id": set_row.get("id"),
        "set_name": set_row.get("name"),
        "set_canonical_key": set_row.get("canonical_key"),
        "scoring_version": scoring_version,
        "hit_policy_version": hit_policy_version,
        "composite_scoring_version": composite_scoring_version,
        "fan_popularity_snapshot_id": str(composite_metadata.get("fan_popularity_snapshot_id")),
        "current_trend_snapshot_ids": composite_metadata.get("current_trend_snapshot_ids") or [],
        "source_config_path": config_trace["source_config_path"],
        "config_fingerprint": config_trace["config_fingerprint"],
        "set_desirability_score": components["set_desirability_score"],
        "chase_subject_strength": components["chase_subject_strength"],
        "chase_subject_depth": components["chase_subject_depth"],
        "accessible_favorite_hits": components["accessible_favorite_hits"],
        "special_pack_chase_appeal": components["special_pack_chase_appeal"],
        **{key: value for key, value in counts.items() if key in db_count_fields},
        "top_subjects_json": components["top_subjects_json"],
        "subject_rollups_json": rollups,
        "rarity_bucket_counts_json": counts["rarity_bucket_counts_json"],
        "special_pack_summary_json": components["special_pack_summary_json"],
        "component_inputs_json": components["component_inputs_json"],
        "diagnostics_json": {
            **components["diagnostics_json"],
            "canonical_cards_seen": len(cards),
            "desirability_links_seen": len(links),
            "card_fact_count": len(card_facts),
            "config_trace": config_trace,
            "coverage_audit": coverage_audit,
            # Consumers MUST check metric_status before ranking a set: an
            # unavailable set scores 0.0 on every component and would otherwise
            # rank as the least appealing product in the catalogue.
            **metric_status,
        },
        "warnings_json": warnings,
        "built_at": built_at,
        "updated_at": built_at,
    }


def build_metric_status(coverage_audit: Dict[str, Any], set_row: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Classify why a set's components look the way they do.

    A set whose cards cannot be classified scores 0.0 on every component, which
    is indistinguishable from a genuinely unappealing set and ranks it as the
    worst product in the catalogue. The score is not evidence of low appeal; it
    is the absence of evidence. Callers must read metric_status before ranking.

    ORDER MATTERS. Product support is decided FIRST, from set metadata, before
    any data-quality check runs. The previous version checked data first and so
    reported ``unavailable_missing_rarity`` for all 36 affected production sets
    - blaming a rarity mapping that is not broken. Those sets have full rarity
    data and resolved subject links; they have no hit-eligible cards because a
    Trainer Kit or McDonald's Collection has no booster pack. Diagnosing product
    type from a data symptom sends someone to fix data that is already correct.

    The two families stay strictly separate:
      unsupported_product_type -> outside the model, permanent, not a defect.
      unavailable_*            -> should be supported, data is incomplete, fix it.

    pull_rate_coverage_pct is intentionally None: pull rates are not resolved at
    this layer, so there is nothing to measure yet. Reporting a number here would
    be fabrication.
    """
    canonical = int(coverage_audit.get("canonical_card_count") or 0)
    unknown_rarity = int(coverage_audit.get("unknown_rarity_count") or 0)
    hit_eligible = int(coverage_audit.get("hit_like_card_count") or 0)
    linked_hits = int(coverage_audit.get("pokemon_linked_hit_count") or 0)
    classified = max(canonical - unknown_rarity, 0)

    rarity_coverage = (classified / canonical) if canonical else None
    link_coverage = (linked_hits / hit_eligible) if hit_eligible else None

    support = classify_product_support(
        set_canonical_key=(set_row or {}).get("canonical_key"),
        set_name=(set_row or {}).get("name"),
        set_series=(set_row or {}).get("series"),
    )

    if not support["supported"]:
        # Decided from metadata alone; the data checks below are not consulted.
        status, reason = "unsupported_product_type", support["product_support_reason"]
        product_support_type = support["product_support_type"]
    elif canonical == 0:
        status, reason = "unsupported_product_type", "No canonical cards are mapped for this set."
        product_support_type = support["product_support_type"]
    elif classified == 0:
        status, reason = (
            "unavailable_missing_rarity_mapping",
            f"All {canonical} canonical cards have unknown rarity; components cannot be computed.",
        )
        product_support_type = support["product_support_type"]
    elif hit_eligible == 0:
        # A SUPPORTED booster set with no hit-eligible card is a real defect:
        # unlike the unsupported cohort above, this set should have a hit ladder.
        status, reason = (
            "unavailable_no_eligible_hit_structure",
            f"This booster set has no card in any hit rarity bucket ({unknown_rarity}/{canonical} "
            "unknown rarity). Expected a hit ladder for a supported product.",
        )
        product_support_type = support["product_support_type"]
    elif linked_hits == 0:
        status, reason = (
            "unavailable_missing_subject_links",
            f"None of the {hit_eligible} hit-eligible cards resolve to a Pokemon subject.",
        )
        product_support_type = support["product_support_type"]
    elif (rarity_coverage or 0) < PARTIAL_COVERAGE_THRESHOLD or (link_coverage or 0) < PARTIAL_COVERAGE_THRESHOLD:
        status, reason = (
            "partial",
            f"Coverage below {PARTIAL_COVERAGE_THRESHOLD:.0%}: rarity={_pct(rarity_coverage)}, subject links={_pct(link_coverage)}.",
        )
        product_support_type = PARTIAL_BOOSTER_SET
    else:
        status, reason = "valid", None
        product_support_type = support["product_support_type"]

    return {
        "metric_status": status,
        "availability_reason": reason,
        "rankable": status in RANKABLE_STATUSES,
        "product_support_type": product_support_type,
        "product_family": support["product_family"],
        "product_support_reason": support["product_support_reason"],
        "product_support_matched_on": support["matched_on"],
        "product_support_version": PRODUCT_SUPPORT_VERSION,
        "canonical_card_count": canonical,
        "classified_card_count": classified,
        "hit_eligible_card_count": hit_eligible,
        "rarity_coverage_pct": round(rarity_coverage * 100, 2) if rarity_coverage is not None else None,
        "subject_link_coverage_pct": round(link_coverage * 100, 2) if link_coverage is not None else None,
        "pull_rate_coverage_pct": None,
        "status_version": METRIC_STATUS_VERSION,
    }


def _pct(value: Optional[float]) -> str:
    return "n/a" if value is None else f"{value:.0%}"


def _normalized_snapshot_ids(value: Any) -> str:
    """Order-independent, storage-shape-independent rendering of snapshot ids.

    Existing rows arrive from Supabase as jsonb; freshly built rows hold a plain
    list. Both must key identically or every set looks stale on every run.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return value
    if isinstance(value, (list, tuple, set)):
        return ",".join(sorted(str(item) for item in value))
    return str(value)


def _source_identity_key(row: Dict[str, Any]) -> Tuple[str, str, str]:
    """Identity of the *inputs* a component row was built from.

    config_fingerprint hashes only the static per-set Python config, so it never
    changes when desirability source data changes. Keying staleness on it alone
    meant a refreshed Trends snapshot could not invalidate a single set row.
    The trend snapshot ids are part of the identity for that reason.
    """
    return (
        str(row.get("set_id")),
        str(row.get("config_fingerprint")),
        _normalized_snapshot_ids(row.get("current_trend_snapshot_ids")),
    )


def _config_trace(set_config: Any) -> Dict[str, Any]:
    if set_config is None:
        payload = {}
        source_path = None
    else:
        source_path = inspect.getsourcefile(set_config)
        payload = {
            "module": getattr(set_config, "__module__", None),
            "qualname": getattr(set_config, "__qualname__", None),
            "SET_NAME": getattr(set_config, "SET_NAME", None),
            "SET_ID": getattr(set_config, "SET_ID", None),
            "GOD_PACK_CONFIG": getattr(set_config, "GOD_PACK_CONFIG", None),
            "DEMI_GOD_PACK_CONFIG": getattr(set_config, "DEMI_GOD_PACK_CONFIG", None),
            "CHASE_METRICS_EXCLUDED_RARITIES": sorted(getattr(set_config, "CHASE_METRICS_EXCLUDED_RARITIES", set()) or []),
        }
    serialized = json.dumps(_jsonable(payload), sort_keys=True, separators=(",", ":"))
    return {
        "source_config_path": source_path,
        "config_fingerprint": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
    }


def _summary_rows(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "set_name": row.get("set_name"),
            "set_canonical_key": row.get("set_canonical_key"),
            "v2_score": row.get("set_desirability_score"),
            "strength": row.get("chase_subject_strength"),
            "depth": row.get("chase_subject_depth"),
            "accessible": row.get("accessible_favorite_hits"),
            "special_pack": row.get("special_pack_chase_appeal"),
            "top_subjects": [
                subject.get("subject_name")
                for subject in (row.get("top_subjects_json") or [])[:3]
            ],
            "warnings": row.get("warnings_json") or [],
            "warning_category_counts": ((row.get("diagnostics_json") or {}).get("hit_link_category_counts") or {}),
        }
        for row in sorted(rows, key=lambda item: item.get("set_desirability_score") or 0.0, reverse=True)
    ]


def _metric_status_counts(rows: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for row in rows:
        status = str(((row.get("diagnostics_json") or {}).get("metric_status")) or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def _unrankable_sets(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sets that must be excluded from appeal rankings rather than shown as 0.0."""
    unrankable = []
    for row in rows:
        diagnostics = row.get("diagnostics_json") or {}
        if diagnostics.get("rankable", True):
            continue
        unrankable.append(
            {
                "set_name": row.get("set_name"),
                "set_canonical_key": row.get("set_canonical_key"),
                "metric_status": diagnostics.get("metric_status"),
                "availability_reason": diagnostics.get("availability_reason"),
                "canonical_card_count": diagnostics.get("canonical_card_count"),
                "rarity_coverage_pct": diagnostics.get("rarity_coverage_pct"),
                "set_desirability_score": row.get("set_desirability_score"),
            }
        )
    return sorted(unrankable, key=lambda item: str(item.get("set_canonical_key") or ""))


def _legacy_coverage_audit_rows(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    audit_rows = []
    for row in rows:
        if row.get("set_canonical_key") not in LEGACY_COVERAGE_AUDIT_SET_KEYS:
            continue
        audit = ((row.get("diagnostics_json") or {}).get("coverage_audit") or {})
        if audit:
            audit_rows.append(audit)
    return sorted(audit_rows, key=lambda item: str(item.get("set_canonical_key") or ""))


def _zero_or_near_zero_rows(rows: Sequence[Dict[str, Any]], *, threshold: float = 5.0) -> List[Dict[str, Any]]:
    near_zero = []
    for row in rows:
        score = _float_or_none(row.get("set_desirability_score"))
        if score is None or score > threshold:
            continue
        audit = ((row.get("diagnostics_json") or {}).get("coverage_audit") or {})
        near_zero.append(
            {
                "set_name": row.get("set_name"),
                "set_canonical_key": row.get("set_canonical_key"),
                "v2_score": score,
                "chase_subject_strength": row.get("chase_subject_strength"),
                "chase_subject_depth": row.get("chase_subject_depth"),
                "accessible_favorite_hits": row.get("accessible_favorite_hits"),
                "special_pack_chase_appeal": row.get("special_pack_chase_appeal"),
                "audit_summary": {
                    "canonical_card_count": audit.get("canonical_card_count"),
                    "hit_like_card_count": audit.get("hit_like_card_count"),
                    "pokemon_linked_hit_count": audit.get("pokemon_linked_hit_count"),
                    "non_pokemon_hit_count": audit.get("non_pokemon_hit_count"),
                    "unknown_rarity_count": audit.get("unknown_rarity_count"),
                    "excluded_rarity_count": audit.get("excluded_rarity_count"),
                    "hit_link_category_counts": audit.get("hit_link_category_counts"),
                },
                "warnings": row.get("warnings_json") or [],
            }
        )
    return sorted(near_zero, key=lambda item: (item.get("v2_score") or 0.0, item.get("set_name") or ""))


def _warning_category_counts(rows: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    totals: Dict[str, int] = defaultdict(int)
    for row in rows:
        counts = ((row.get("diagnostics_json") or {}).get("hit_link_category_counts") or {})
        for key, value in counts.items():
            totals[str(key)] += int(value or 0)
    return dict(sorted(totals.items()))


def _format_summary_table(report: Dict[str, Any]) -> str:
    rows = report.get("summary_rows") or []
    if not rows:
        return "No V2 component rows generated."
    headers = ["Set", "V2", "Strength", "Depth", "Access", "Special", "Top Subjects"]
    widths = [28, 7, 9, 7, 7, 8, 36]
    lines = [" ".join(header.ljust(width) for header, width in zip(headers, widths))]
    lines.append(" ".join("-" * width for width in widths))
    for row in rows[:25]:
        values = [
            str(row.get("set_name") or "")[:28],
            _fmt(row.get("v2_score")),
            _fmt(row.get("strength")),
            _fmt(row.get("depth")),
            _fmt(row.get("accessible")),
            _fmt(row.get("special_pack")),
            ", ".join(row.get("top_subjects") or [])[:36],
        ]
        lines.append(" ".join(value.ljust(width) for value, width in zip(values, widths)))
    return "\n".join(lines)


def _fmt(value: Any) -> str:
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return "-"


def _float_or_none(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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


def _chunked(values: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    for index in range(0, len(values), size):
        yield values[index:index + size]


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
    except PokemonSetDesirabilityComponentsError as exc:
        print(f"[pokemon-set-desirability-components][ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)
