"""Which component row a Collector Appeal calculation is allowed to read.

THE DEFECT THIS MODULE EXISTS TO PREVENT
----------------------------------------
``pokemon_set_desirability_component_scores`` is NOT one row per set. It is one
row per (set, scoring_version, hit_policy_version, composite_scoring_version,
fan_popularity_snapshot_id, config_fingerprint) - the table's actual unique key.
Production holds several hundred rows across 171 sets and three hit policies
(512 at the time of writing; the count grows with every rebuild, which is why no
caller should hardcode it - report it from the read instead).

The previous loader took "the latest row per set by ``built_at``". That rule is
not merely imprecise, it is WRONG IN PRODUCTION TODAY: the newest rows for all
171 sets carry ``hit_policy_version = ..._v1``, while the code computes - and
the formula fingerprint certifies - ``..._v2_coverage_cleanup``. Every diagnostics
block written under that rule would have stamped a v2 certificate onto v1 inputs.
The row would then look current forever, because the fingerprint it carries is
the one the checker expects.

Note the direction of the trap: the wrong rows are NEWER, not older. "Take the
latest" and "take the version we compute under" are different questions, and
recency is not evidence of agreement. So the contract here is VERSION-EXACT and
recency is only a tiebreak WITHIN an exact-version match.

WHAT ABSENCE MEANS
------------------
A set with no exact-version row is UNAVAILABLE - reported, with the versions it
does have, as ``missing_current_component_source_row``. It never falls back to a
near-miss row. Falling back is how a v1 row acquires a v2 certificate; refusing
is how the gap stays visible until someone rebuilds it.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Mapping, Optional, Sequence

from backend.desirability.composite import COMPOSITE_SCORING_VERSION
from backend.desirability.rarity_buckets import HIT_POLICY_VERSION
from backend.desirability.set_components import SCORING_VERSION

COMPONENT_TABLE = "pokemon_set_desirability_component_scores"
COMPONENT_SOURCE_CONTRACT_VERSION = "component_source_contract_v1_version_exact"

# The table's REAL unique key, verified against pg_indexes
# (``pokemon_set_desirability_component_unique_key``). Encoded here so a test can
# assert against the schema rather than against a fake that accepts any key.
COMPONENT_UNIQUE_KEY: Sequence[str] = (
    "set_id",
    "scoring_version",
    "hit_policy_version",
    "composite_scoring_version",
    "fan_popularity_snapshot_id",
    "config_fingerprint",
)
COMPONENT_PRIMARY_KEY = "id"

# ``set_id`` alone is NOT unique (several rows per set) and must never be used as
# a conflict target. Named so the prohibition is testable, not just documented.
COMPONENT_NON_UNIQUE_COLUMNS: Sequence[str] = ("set_id", "set_canonical_key", "built_at")

# The expected source versions, read LIVE from the modules that define them, so
# the contract cannot drift from what the code actually computes.
EXPECTED_SCORING_VERSION = SCORING_VERSION
EXPECTED_HIT_POLICY_VERSION = HIT_POLICY_VERSION
EXPECTED_COMPOSITE_SCORING_VERSION = COMPOSITE_SCORING_VERSION

MISSING_CURRENT_COMPONENT_SOURCE_ROW = "missing_current_component_source_row"
DUPLICATE_CURRENT_COMPONENT_SOURCE_ROW = "duplicate_current_component_source_row"

# Every column the calculation, the identity, or the concurrency check needs.
# Explicit rather than ``*``: a read that silently stops returning a column the
# identity depends on should fail, not quietly emit a null identity.
COMPONENT_SOURCE_COLUMNS = ",".join(
    (
        "id",
        "set_id",
        "set_name",
        "set_canonical_key",
        "scoring_version",
        "hit_policy_version",
        "composite_scoring_version",
        "fan_popularity_snapshot_id",
        "current_trend_snapshot_ids",
        "config_fingerprint",
        "source_config_path",
        "set_desirability_score",
        "chase_subject_strength",
        "chase_subject_depth",
        "accessible_favorite_hits",
        "special_pack_chase_appeal",
        "hit_eligible_card_count",
        "scored_hit_eligible_card_count",
        "unique_subject_count",
        "duplicate_subject_count",
        "premium_chase_subject_count",
        "major_hit_subject_count",
        "accessible_hit_count",
        "trainer_hit_count",
        "unmatched_hit_count",
        "top_subjects_json",
        "subject_rollups_json",
        "rarity_bucket_counts_json",
        "special_pack_summary_json",
        "component_inputs_json",
        "diagnostics_json",
        "warnings_json",
        "built_at",
        "created_at",
        "updated_at",
    )
)


# The columns the SELECTOR itself reads: the version triple it matches on, the
# unique-key fields a duplicate is diagnosed with, and the identity a caller
# reports. A reader that needs different payload columns adds them via
# :func:`selector_columns` rather than hand-writing this list - a second loader
# with its own column list is a second place for the contract to drift.
COMPONENT_IDENTITY_COLUMNS: Sequence[str] = (
    "id",
    "set_id",
    "set_name",
    "set_canonical_key",
    "scoring_version",
    "hit_policy_version",
    "composite_scoring_version",
    "fan_popularity_snapshot_id",
    "config_fingerprint",
    "built_at",
)


def selector_columns(*extra: str) -> str:
    """The selector's identity columns plus a caller's payload columns.

    Callers pass only what THEY need to compute with; the identity columns come
    from here so no caller can accidentally select a row set the selector cannot
    diagnose. Order is stable so two readers issue byte-identical queries.
    """
    columns: List[str] = list(COMPONENT_IDENTITY_COLUMNS)
    for column in extra:
        if column not in columns:
            columns.append(column)
    return ",".join(columns)


def expected_source_versions() -> Dict[str, str]:
    """The exact versions a usable component row must carry."""
    return {
        "scoring_version": EXPECTED_SCORING_VERSION,
        "hit_policy_version": EXPECTED_HIT_POLICY_VERSION,
        "composite_scoring_version": EXPECTED_COMPOSITE_SCORING_VERSION,
    }


def row_versions(row: Mapping[str, Any]) -> Dict[str, Optional[str]]:
    """The version triple a row actually carries."""
    return {
        "scoring_version": _text(row.get("scoring_version")),
        "hit_policy_version": _text(row.get("hit_policy_version")),
        "composite_scoring_version": _text(row.get("composite_scoring_version")),
    }


def matches_expected_versions(row: Mapping[str, Any]) -> bool:
    """True only on an exact match of all three versions. No near misses."""
    return row_versions(row) == expected_source_versions()


def select_component_source_rows(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Partition every component row into exact-version / missing / duplicate.

    Returns the selection AND the evidence for it: which sets have an
    exact-version row, which do not (with the versions they DO have, so the gap
    is diagnosable without a second query), and which have more than one.

    A duplicate is not silently resolved. Two rows matching the version triple
    differ in ``fan_popularity_snapshot_id`` or ``config_fingerprint`` - both
    part of the unique key - so picking one would be picking an input set, which
    is an operator's decision, not a loader's.
    """
    expected = expected_source_versions()

    by_set: Dict[str, List[Mapping[str, Any]]] = {}
    exact_by_set: Dict[str, List[Mapping[str, Any]]] = {}
    for row in rows:
        set_id = _text(row.get("set_id"))
        if not set_id:
            continue
        by_set.setdefault(set_id, []).append(row)
        if matches_expected_versions(row):
            exact_by_set.setdefault(set_id, []).append(row)

    selected: Dict[str, Mapping[str, Any]] = {}
    duplicates: List[Dict[str, Any]] = []
    for set_id, candidates in exact_by_set.items():
        if len(candidates) == 1:
            selected[set_id] = candidates[0]
            continue
        duplicates.append(
            {
                "set_id": set_id,
                "set_name": _text(candidates[0].get("set_name")),
                "reason": DUPLICATE_CURRENT_COMPONENT_SOURCE_ROW,
                "row_count": len(candidates),
                "rows": [
                    {
                        "id": _text(candidate.get("id")),
                        "fan_popularity_snapshot_id": _text(candidate.get("fan_popularity_snapshot_id")),
                        "config_fingerprint": _text(candidate.get("config_fingerprint")),
                        "built_at": _text(candidate.get("built_at")),
                    }
                    for candidate in candidates
                ],
            }
        )

    missing: List[Dict[str, Any]] = []
    for set_id, candidates in by_set.items():
        if set_id in exact_by_set:
            continue
        missing.append(
            {
                "set_id": set_id,
                "set_name": _text(candidates[0].get("set_name")),
                "set_canonical_key": _text(candidates[0].get("set_canonical_key")),
                "reason": MISSING_CURRENT_COMPONENT_SOURCE_ROW,
                "expected_versions": dict(expected),
                "available_versions": sorted(
                    (
                        {
                            "id": _text(candidate.get("id")),
                            **row_versions(candidate),
                            "built_at": _text(candidate.get("built_at")),
                        }
                        for candidate in candidates
                    ),
                    key=lambda entry: str(entry.get("built_at")),
                    reverse=True,
                ),
            }
        )

    return {
        "contract_version": COMPONENT_SOURCE_CONTRACT_VERSION,
        "expected_versions": dict(expected),
        "selected": selected,
        "missing": sorted(missing, key=lambda entry: str(entry["set_id"])),
        "duplicates": sorted(duplicates, key=lambda entry: str(entry["set_id"])),
        "counts": {
            "rows_scanned": len(rows),
            "sets_scanned": len(by_set),
            "exact_version_rows_found": len(selected),
            "sets_missing_exact_version_row": len(missing),
            "sets_with_duplicate_exact_version_rows": len(duplicates),
        },
        "version_distribution": _version_distribution(rows),
    }


def _version_distribution(rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Every version triple present, with row and set counts. The audit trail."""
    buckets: Dict[tuple, Dict[str, Any]] = {}
    for row in rows:
        versions = row_versions(row)
        key = (versions["scoring_version"], versions["hit_policy_version"], versions["composite_scoring_version"])
        bucket = buckets.setdefault(key, {**versions, "row_count": 0, "set_ids": set()})
        bucket["row_count"] += 1
        set_id = _text(row.get("set_id"))
        if set_id:
            bucket["set_ids"].add(set_id)
    distribution = []
    for bucket in buckets.values():
        entry = dict(bucket)
        entry["set_count"] = len(entry.pop("set_ids"))
        entry["is_expected"] = (
            entry["scoring_version"] == EXPECTED_SCORING_VERSION
            and entry["hit_policy_version"] == EXPECTED_HIT_POLICY_VERSION
            and entry["composite_scoring_version"] == EXPECTED_COMPOSITE_SCORING_VERSION
        )
        distribution.append(entry)
    return sorted(distribution, key=lambda entry: -entry["row_count"])


def build_source_identity(row: Mapping[str, Any]) -> Dict[str, Any]:
    """The identity of the exact row a diagnostics block was computed FROM.

    Distinct from the FORMULA identity on purpose. The formula fingerprint says
    "these are the rules I applied"; this says "these are the inputs I applied
    them to". Storing only the first is what allowed a v2 certificate to land on
    v1 inputs: the certificate was true about the rules and silent about the row.
    """
    return {
        "component_row_id": _text(row.get("id")),
        "set_id": _text(row.get("set_id")),
        "scoring_version": _text(row.get("scoring_version")),
        "hit_policy_version": _text(row.get("hit_policy_version")),
        "composite_scoring_version": _text(row.get("composite_scoring_version")),
        "fan_popularity_snapshot_id": _text(row.get("fan_popularity_snapshot_id")),
        "config_fingerprint": _text(row.get("config_fingerprint")),
        "current_trend_snapshot_ids": row.get("current_trend_snapshot_ids"),
        "source_config_path": _text(row.get("source_config_path")),
        "built_at": _text(row.get("built_at")),
        "updated_at": _text(row.get("updated_at")),
        "unique_key": list(COMPONENT_UNIQUE_KEY),
        "contract_version": COMPONENT_SOURCE_CONTRACT_VERSION,
    }


def source_identity_matches_row(identity: Mapping[str, Any], row: Mapping[str, Any]) -> bool:
    """Does a diagnostics block's source identity describe THIS row?

    The invariant behind blocker #2. A v1 row must never carry a block whose
    identity claims v2 coverage-cleanup inputs.
    """
    for field in ("scoring_version", "hit_policy_version", "composite_scoring_version",
                  "fan_popularity_snapshot_id", "config_fingerprint"):
        if _text(identity.get(field)) != _text(row.get(field)):
            return False
    return _text(identity.get("component_row_id")) == _text(row.get("id"))


def rebuild_command_for(set_id: str, set_name: Optional[str] = None) -> str:
    """The exact dry-run command that would rebuild ONE set's current-version row.

    Returned as text, never executed. Rebuilding is a separate, separately
    approved operation: it writes a new component row with real scores, which is
    a far larger action than adding a diagnostics block.
    """
    # The set name goes on its own comment line, never trailing a continuation:
    # `\  # name` escapes the space rather than the newline, which silently
    # breaks the command for whoever copies it out of the report.
    header = f"# {set_name}\n" if set_name else ""
    return (
        f"{header}"
        "python backend/scripts/build_pokemon_set_desirability_component_scores.py \\\n"
        f"  --set-id {set_id} \\\n"
        f"  --hit-policy-version {EXPECTED_HIT_POLICY_VERSION} \\\n"
        "  --dry-run"
    )


def build_component_source_manifest(selected: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    """A deterministic hash of the EXACT selected rows, identity and all.

    The previous manifest hashed set_id + built_at + score only, which meant the
    generated payload could change while the manifest held still - an approval
    token that does not cover what it approves. This hashes every field the
    calculation and the identity read.
    """
    digest_input = []
    for set_id in sorted(selected, key=str):
        row = selected[set_id]
        digest_input.append(
            {
                "id": _text(row.get("id")),
                "set_id": str(set_id),
                "versions": row_versions(row),
                "fan_popularity_snapshot_id": _text(row.get("fan_popularity_snapshot_id")),
                "config_fingerprint": _text(row.get("config_fingerprint")),
                "set_desirability_score": _normalize_number(row.get("set_desirability_score")),
                "counts": {
                    field: row.get(field)
                    for field in (
                        "hit_eligible_card_count",
                        "scored_hit_eligible_card_count",
                        "unique_subject_count",
                        "duplicate_subject_count",
                        "premium_chase_subject_count",
                        "major_hit_subject_count",
                        "accessible_hit_count",
                        "trainer_hit_count",
                        "unmatched_hit_count",
                    )
                },
                "subject_rollups_json": _canonical(row.get("subject_rollups_json")),
                "diagnostics_json": _canonical(row.get("diagnostics_json")),
                "component_inputs_json": _canonical(row.get("component_inputs_json")),
                "built_at": _text(row.get("built_at")),
                "updated_at": _text(row.get("updated_at")),
            }
        )
    blob = json.dumps(digest_input, sort_keys=True, separators=(",", ":"), default=str)
    return {
        "row_count": len(digest_input),
        "manifest_hash": hashlib.sha256(blob.encode("utf-8")).hexdigest(),
        "algorithm": "sha256",
        "contract_version": COMPONENT_SOURCE_CONTRACT_VERSION,
        "expected_versions": expected_source_versions(),
    }


def _canonical(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _canonical(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, float):
        return repr(value)
    return value


def _normalize_number(value: Any) -> Optional[str]:
    try:
        return repr(round(float(value), 6))
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> Optional[str]:
    return None if value is None else str(value)
