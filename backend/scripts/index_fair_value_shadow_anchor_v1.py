"""FV-S3 anchor publication builder (pure; no I/O, no prices of any kind).

Builds the *anchor publication* half of the prospective shadow ledger for
``EXPLICIT_NM_SOLD_CLEARING_ANCHOR_V1``. It applies the frozen FV-S2 rule unchanged
(``index_fair_value_sold_clearing_anchor``) on top of an information-availability gate.

Boundary (tested, see test_index_fair_value_shadow_s3.py):
* This module never imports or references the evaluation/component modules.
* ``build_anchor_publication`` has no parameter that could carry a comparison price,
  and refuses any evidence row or metadata carrying a price-like comparison key.
* Prospective availability: a transaction is eligible only if it was *collected by us*
  (``collected_at``) AND, when the provider stamped it, *ingested by the provider*
  (``ingested_at``) at or before ``information_cutoff``. ``sold_at`` alone is never enough.
* Evidence enrichment is first-seen provider state: ``FIRST_SEEN_PROVIDER_ENRICHMENT_RESEARCH_ONLY``.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections import Counter
from datetime import date, datetime, time, timezone
from typing import Any, Mapping, Sequence

from backend.scripts import index_fair_value_sold_clearing_anchor as rules

PUBLICATION_SCHEMA_VERSION = "fv_shadow_anchor_publication_v1"
RULE_VERSION = rules.RULE_VERSION
ENRICHMENT_POLICY = "FIRST_SEEN_PROVIDER_ENRICHMENT_RESEARCH_ONLY"
STATUS_PROSPECTIVE = "PROSPECTIVE_AS_KNOWN_AT_CUTOFF"
STATUS_RETROSPECTIVE = rules.EVIDENCE_SEMANTICS  # RETROSPECTIVE_BACKFILLED_EVIDENCE
STATUS_REPLAY = "AS_KNOWN_AT_CUTOFF_REPLAY_NOT_PROSPECTIVE"
NOT_COLLECTED_AT_CUTOFF = "NOT_COLLECTED_AT_CUTOFF"
NOT_INGESTED_AT_CUTOFF = "NOT_INGESTED_BY_PROVIDER_AT_CUTOFF"
UNPARSEABLE_AVAILABILITY = "UNPARSEABLE_AVAILABILITY_TIMESTAMP"
_NS = uuid.UUID("7d0b3c1e-52a4-4f4e-9b0a-0f53a0c11a01")

# Any key that smells like an evaluation/comparison price is refused outright.
_PRICE_LEAK = re.compile(
    r"((market|target|comparison|tcgplayer|outcome|realized|structural).*(price|usd|error|value))"
    r"|((price|usd).*(market|target|comparison|tcgplayer))",
    re.I,
)
_ALLOWED_ROW_KEYS_WITH_PRICE = frozenset({"price"})


class ShadowAnchorError(RuntimeError):
    pass


def _utc(value: Any, *, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ShadowAnchorError(f"{name} must be a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _guard_keys(mapping: Mapping[str, Any], *, where: str) -> None:
    for key in mapping:
        if key in _ALLOWED_ROW_KEYS_WITH_PRICE:
            continue
        if _PRICE_LEAK.search(str(key)):
            raise ShadowAnchorError(f"SHADOW_ANCHOR_COMPARISON_LEAKAGE_GUARD: {where} carries {key!r}")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def publication_key(canonical_card_id: str, evaluation_date: date, information_cutoff: datetime) -> dict[str, str]:
    return {
        "rule_version": RULE_VERSION,
        "canonical_card_id": str(canonical_card_id),
        "evaluation_date": evaluation_date.isoformat(),
        "information_cutoff": _utc(information_cutoff, name="information_cutoff").isoformat(),
    }


def _partition_by_availability(
    rows: Sequence[Mapping[str, Any]], cutoff: datetime
) -> tuple[list[Mapping[str, Any]], Counter[str]]:
    kept: list[Mapping[str, Any]] = []
    dropped: Counter[str] = Counter()
    for row in rows:
        collected = rules._parse_ts(row.get("collected_at"))
        if collected is None:
            dropped[UNPARSEABLE_AVAILABILITY] += 1
            continue
        if collected > cutoff:
            dropped[NOT_COLLECTED_AT_CUTOFF] += 1
            continue
        raw_ingested = row.get("ingested_at")
        if raw_ingested not in (None, ""):
            ingested = rules._parse_ts(raw_ingested)
            if ingested is None:
                dropped[UNPARSEABLE_AVAILABILITY] += 1
                continue
            if ingested > cutoff:
                dropped[NOT_INGESTED_AT_CUTOFF] += 1
                continue
        kept.append(row)
    return kept, dropped


def build_anchor_publication(
    *,
    canonical_card_id: str,
    card_variant_id: str,
    card_number: Any,
    evidence_rows: Sequence[Mapping[str, Any]],
    evaluation_date: date,
    information_cutoff: datetime,
    generated_at: datetime,
    source_commit: str,
    input_fingerprints: Mapping[str, str],
    prospective: bool = True,
    replay: bool = False,
) -> dict[str, Any]:
    """Construct one immutable anchor publication. Deterministic for fixed inputs.

    ``replay=True`` applies the identical availability gate to historical evidence but labels
    the result ``AS_KNOWN_AT_CUTOFF_REPLAY_NOT_PROSPECTIVE``: it can never be mistaken for a
    genuinely prospective publication.
    """
    cutoff = _utc(information_cutoff, name="information_cutoff")
    generated = _utc(generated_at, name="generated_at")
    if not re.fullmatch(r"[0-9a-f]{7,40}", str(source_commit or "")):
        raise ShadowAnchorError("source_commit must be a hex git SHA")
    if replay and not prospective:
        raise ShadowAnchorError("replay applies the prospective availability gate")
    if prospective:
        if generated < cutoff:
            raise ShadowAnchorError("prospective publication generated before its information cutoff")
        if cutoff < datetime.combine(evaluation_date, time.min, tzinfo=timezone.utc):
            raise ShadowAnchorError("information cutoff precedes the start of the evaluation date")
    for row in evidence_rows:
        _guard_keys(row, where="evidence row")
    _guard_keys(input_fingerprints, where="input_fingerprints")

    if prospective:
        available, unavailable = _partition_by_availability(evidence_rows, cutoff)
        info_cutoff_for_rules: datetime | None = cutoff
    else:
        available, unavailable, info_cutoff_for_rules = list(evidence_rows), Counter(), None

    result = rules.build_card_result(
        available, card_number=card_number, observation_date=evaluation_date,
        information_cutoff=info_cutoff_for_rules,
    )
    by_id = {int(r["provider_listing_id"]): r for r in available if r.get("provider_listing_id") is not None}
    member_ids = sorted(result.get("comp_listing_ids") or [])
    members = []
    for listing_id in member_ids:
        row = by_id[listing_id]
        members.append({
            "provider_card_id": int(row["provider_card_id"]),
            "provider_listing_id": listing_id,
            "price": str(row["price"]),
            "sold_at": str(row["sold_at"])[:10],
            "collected_at": rules._parse_ts(row.get("collected_at")).isoformat(),
            "ingested_at": (rules._parse_ts(row.get("ingested_at")).isoformat() if row.get("ingested_at") else None),
            "title_sha256": sha256_text(str(row.get("title") or "")),
            "grader_at_first_seen": row.get("grader"),
            "graded_at_first_seen": row.get("graded"),
        })
    membership_fp = sha256_text(canonical_json([[m["provider_card_id"], m["provider_listing_id"]] for m in members]))
    evidence_fp = sha256_text(canonical_json(members))
    ingested_max = max((m["ingested_at"] for m in members if m["ingested_at"]), default=None)

    exclusions = Counter(result["exclusion_counts"])
    exclusions.update(unavailable)
    anchored = result["status"] == "ANCHORED"
    key = publication_key(canonical_card_id, evaluation_date, cutoff)
    body: dict[str, Any] = {
        "schema_version": PUBLICATION_SCHEMA_VERSION,
        **key,
        "card_variant_id": str(card_variant_id),
        "status": result["status"],
        "evidence_status": (STATUS_REPLAY if replay else STATUS_PROSPECTIVE) if prospective else STATUS_RETROSPECTIVE,
        "enrichment_policy": ENRICHMENT_POLICY,
        "evidence_cutoff": cutoff.isoformat(),
        "selected_window_days": result["selected_window_days"],
        "eligible_comp_count": result["comp_count"] if anchored else 0,
        "eligible_counts_by_window": result["eligible_counts_by_window"],
        "sold_at_min": result.get("oldest_sold_at"),
        "sold_at_max": result.get("newest_sold_at"),
        "collected_at_max": result.get("collected_at_max"),
        "ingested_at_max": ingested_max,
        "median": result.get("median"),
        "median_usd_2dp": result.get("median_usd_2dp"),
        "q1": result.get("q1"), "q3": result.get("q3"), "iqr": result.get("iqr"),
        "mad": result.get("mad"),
        "distinct_transaction_days": result.get("distinct_sale_days"),
        "membership_fingerprint": membership_fp,
        "evidence_fingerprint": evidence_fp,
        "members": members,
        "exclusion_counts": dict(sorted(exclusions.items())),
        "rows_offered": len(evidence_rows),
        "input_fingerprints": dict(sorted(input_fingerprints.items())),
    }
    content_fp = sha256_text(canonical_json(body))
    return {
        **body,
        "content_fingerprint": content_fp,
        "publication_id": str(uuid.uuid5(_NS, canonical_json(key) + content_fp)),
        # Provenance that must not change the identity of an otherwise identical retry.
        "generated_at": generated.isoformat(),
        "source_commit": str(source_commit),
    }
