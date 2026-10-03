"""Prospective FV-S3 shadow publisher.

Research-only. No provider calls. The ordering is the contract:

1. capture the information cutoff;
2. read only cached identity + persisted sold evidence;
3. build and append EVERY frozen sold-clearing anchor;
4. only after step 3 succeeds, read TCGplayer comparison prices;
5. append separate component observations and horizon-0 outcomes.

No blended Fair Value is produced and no public/canonical pricing surface is touched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.scripts import index_fair_value_shadow_anchor_v1 as anchor_mod  # noqa: E402
from backend.scripts import index_fair_value_shadow_evaluation_v1 as evaluation  # noqa: E402
from backend.scripts import index_fair_value_shadow_ledger_v1 as ledger_mod  # noqa: E402
from backend.scripts import run_index_fair_value_sold_clearing_anchor_v1 as s2  # noqa: E402

PHOENIX = ZoneInfo("America/Phoenix")
PUBLISHER_VERSION = "fv_s3_prospective_shadow_publisher_v1"
PRICE_SOURCE = "TCGPlayer"


class ProspectiveShadowError(RuntimeError):
    pass


def parse_information_cutoff(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("information cutoff must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("information cutoff must include a timezone")
    return parsed.astimezone(timezone.utc)


def _chunks(values: list[str], size: int = 50) -> Iterable[list[str]]:
    for i in range(0, len(values), size):
        yield values[i:i + size]


def _fingerprint(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _paged(factory: Any, page: int = 1000) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        batch = list(factory().range(start, start + page - 1).execute().data or [])
        rows.extend(dict(r) for r in batch)
        if len(batch) < page:
            return rows
        start += page


def resolve_daily_information_cutoff(
    db: Any,
    *,
    requested_cutoff: datetime,
    evaluation_date: date,
    panel: Mapping[str, Any],
) -> tuple[datetime, str]:
    """Enforce one prospective information cutoff per evaluation date.

    A publisher can fail after some card publications are appended. Retrying must resume
    that same cohort, not create a second cutoff for the day. This also preserves the
    already-established Oct-2 prospective cohort rather than duplicating it when daily
    automation begins later the same day.
    """
    rows = _paged(lambda: db.table("fair_value_shadow_anchor_publications_v1")
        .select("canonical_card_id,information_cutoff,evidence_status")
        .eq("evaluation_date", evaluation_date.isoformat())
        .eq("evidence_status", anchor_mod.STATUS_PROSPECTIVE)
        .order("canonical_card_id"))
    if not rows:
        return requested_cutoff, "REQUESTED_NEW_DAILY_CUTOFF"

    panel_ids = {str(r["canonical_card_id"]) for r in panel["rows"]}
    observed_ids = {str(r.get("canonical_card_id") or "") for r in rows}
    foreign = sorted(observed_ids - panel_ids)
    if foreign:
        raise ProspectiveShadowError(
            f"EXISTING_DAILY_COHORT_OUTSIDE_PANEL count={len(foreign)}"
        )

    cutoffs: set[datetime] = set()
    for row in rows:
        raw = row.get("information_cutoff")
        if raw in (None, ""):
            raise ProspectiveShadowError("EXISTING_DAILY_COHORT_CUTOFF_MISSING")
        try:
            parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError as exc:
            raise ProspectiveShadowError("EXISTING_DAILY_COHORT_CUTOFF_INVALID") from exc
        if parsed.tzinfo is None:
            raise ProspectiveShadowError("EXISTING_DAILY_COHORT_CUTOFF_NAIVE")
        cutoffs.add(parsed.astimezone(timezone.utc))

    if len(cutoffs) != 1:
        raise ProspectiveShadowError(
            f"MULTIPLE_EXISTING_DAILY_CUTOFFS count={len(cutoffs)}"
        )
    existing = next(iter(cutoffs))
    if existing.astimezone(PHOENIX).date() != evaluation_date:
        raise ProspectiveShadowError("EXISTING_DAILY_CUTOFF_DATE_MISMATCH")
    return existing, "REUSED_EXISTING_DAILY_CUTOFF"


def fetch_anchor_inputs(db: Any, panel: Mapping[str, Any]) -> tuple[dict[str, int], dict[str, list[dict[str, Any]]]]:
    """ANCHOR PHASE ONLY. This function must never read a price table."""
    canonical_ids = sorted(str(r["canonical_card_id"]) for r in panel["rows"])
    identities: list[dict[str, Any]] = []
    for chunk in _chunks(canonical_ids):
        identities.extend(_paged(lambda c=chunk: db.table("pkmnprices_card_identity_v1")
            .select("provider_card_id,canonical_card_id,language,tcgplayer_product_id")
            .in_("canonical_card_id", c).eq("language", "English").order("canonical_card_id").order("provider_card_id")))

    grouped_ids: dict[str, list[int]] = defaultdict(list)
    for row in identities:
        grouped_ids[str(row["canonical_card_id"])].append(int(row["provider_card_id"]))
    provider_by_card: dict[str, int] = {}
    for cid in canonical_ids:
        ids = sorted(set(grouped_ids.get(cid, [])))
        if len(ids) != 1:
            raise ProspectiveShadowError(f"EXACT_IDENTITY_CARDINALITY cid={cid} count={len(ids)}")
        provider_by_card[cid] = ids[0]

    evidence_by_card: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for cid in canonical_ids:
        pid = provider_by_card[cid]
        rows = _paged(lambda c=cid: db.table("pkmnprices_ebay_sold_evidence_v1")
            .select(s2.EVIDENCE_COLUMNS).eq("canonical_card_id", c)
            .order("provider_card_id").order("provider_listing_id"))
        mismatched = [r for r in rows if int(r["provider_card_id"]) != pid]
        if mismatched:
            raise ProspectiveShadowError(f"PROVIDER_IDENTITY_MISMATCH cid={cid} rows={len(mismatched)}")
        evidence_by_card[cid] = rows
    return provider_by_card, evidence_by_card


def build_publications(
    *,
    panel: Mapping[str, Any],
    provider_by_card: Mapping[str, int],
    evidence_by_card: Mapping[str, list[dict[str, Any]]],
    evaluation_date: date,
    information_cutoff: datetime,
    generated_at: datetime,
    source_commit: str,
) -> list[dict[str, Any]]:
    publications: list[dict[str, Any]] = []
    for target in sorted(panel["rows"], key=lambda r: str(r["canonical_card_id"])):
        cid = str(target["canonical_card_id"])
        rows = list(evidence_by_card[cid])
        # Freeze the publisher input to evidence that was actually knowable at the
        # information cutoff. Rows collected/ingested later must not change a retry's
        # rows_offered/input fingerprint/content fingerprint for the same fixed cutoff.
        available_rows, _ = anchor_mod._partition_by_availability(rows, information_cutoff)
        input_fingerprints = {
            "panel_manifest": str(panel["panel_fingerprint"]),
            "identity_mapping": _fingerprint([cid, provider_by_card[cid]]),
            "evidence_rowset": _fingerprint(available_rows),
        }
        publications.append(anchor_mod.build_anchor_publication(
            canonical_card_id=cid,
            card_variant_id=str(target["card_variant_id"]),
            card_number=target["card_number"],
            evidence_rows=available_rows,
            evaluation_date=evaluation_date,
            information_cutoff=information_cutoff,
            generated_at=generated_at,
            source_commit=source_commit,
            input_fingerprints=input_fingerprints,
            prospective=True,
        ))
    return publications


def fetch_market_comparisons(
    db: Any,
    panel: Mapping[str, Any],
    *,
    evaluation_date: date,
) -> dict[str, dict[str, Any] | None]:
    """EVALUATION PHASE ONLY. Must be called only after all anchors are appended."""
    canonical_ids = sorted(str(r["canonical_card_id"]) for r in panel["rows"])
    latest: list[dict[str, Any]] = []
    for chunk in _chunks(canonical_ids):
        latest.extend(_paged(lambda c=chunk: db.table("pokemon_canonical_card_market_prices_latest")
            .select("canonical_card_id,card_variant_id,condition_id,market_price,captured_at,source")
            .in_("canonical_card_id", c).order("canonical_card_id")))
    latest_by = {str(r["canonical_card_id"]): r for r in latest}

    panel_by = {str(r["canonical_card_id"]): r for r in panel["rows"]}
    variant_ids = sorted({
        str(row["card_variant_id"]) for cid, row in latest_by.items()
        if cid in panel_by and str(row.get("card_variant_id")) == str(panel_by[cid]["card_variant_id"])
        and row.get("condition_id")
    })
    observations: list[dict[str, Any]] = []
    for chunk in _chunks(variant_ids):
        observations.extend(_paged(lambda c=chunk: db.table("card_variant_price_observations")
            .select("card_variant_id,condition_id,market_price,captured_at,source,currency")
            .in_("card_variant_id", c).eq("captured_at", evaluation_date.isoformat())
            .eq("source", PRICE_SOURCE).order("card_variant_id").order("condition_id")))
    obs_by = {(str(r["card_variant_id"]), str(r["condition_id"])): r for r in observations}

    out: dict[str, dict[str, Any] | None] = {}
    for cid in canonical_ids:
        target = panel_by[cid]
        authority = latest_by.get(cid)
        if not authority or str(authority.get("card_variant_id")) != str(target["card_variant_id"]):
            out[cid] = None
            continue
        obs = obs_by.get((str(target["card_variant_id"]), str(authority.get("condition_id"))))
        if not obs or obs.get("market_price") in (None, "") or str(obs.get("currency")) != "USD":
            out[cid] = None
            continue
        out[cid] = {
            "market_price_usd": float(obs["market_price"]),
            "market_price_date": str(obs["captured_at"])[:10],
            "source": obs.get("source"),
        }
    return out


def publish(
    *,
    db: Any,
    ledger: Any,
    source_commit: str,
    now: datetime | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{7,40}", source_commit):
        raise ProspectiveShadowError("source_commit must be a hex git SHA")
    cutoff_input = now or datetime.now(timezone.utc)
    if cutoff_input.tzinfo is None:
        raise ProspectiveShadowError("information cutoff must be timezone-aware")
    requested_cutoff = cutoff_input.astimezone(timezone.utc)
    generated_at = datetime.now(timezone.utc)
    if generated_at < requested_cutoff:
        raise ProspectiveShadowError("INFORMATION_CUTOFF_IN_FUTURE")
    evaluation_date = requested_cutoff.astimezone(PHOENIX).date()
    panel = s2.load_panel()
    cutoff, cutoff_resolution = resolve_daily_information_cutoff(
        db,
        requested_cutoff=requested_cutoff,
        evaluation_date=evaluation_date,
        panel=panel,
    )

    provider_by_card, evidence_by_card = fetch_anchor_inputs(db, panel)
    publications = build_publications(
        panel=panel,
        provider_by_card=provider_by_card,
        evidence_by_card=evidence_by_card,
        evaluation_date=evaluation_date,
        information_cutoff=cutoff,
        generated_at=generated_at,
        source_commit=source_commit,
    )

    anchor_statuses: dict[str, int] = defaultdict(int)
    if dry_run:
        shadow_ledger: Any = ledger_mod.InMemoryShadowLedger()
    else:
        shadow_ledger = ledger
    for pub in publications:
        anchor_statuses[shadow_ledger.append_publication(pub)] += 1

    # CRITICAL anti-leakage boundary: no price table is read before every anchor append succeeds.
    market = fetch_market_comparisons(db, panel, evaluation_date=evaluation_date)

    component_statuses: dict[str, int] = defaultdict(int)
    outcome_statuses: dict[str, int] = defaultdict(int)
    anchored = 0
    market_available = 0
    for pub in publications:
        cid = str(pub["canonical_card_id"])
        m = market.get(cid)
        component = evaluation.build_component_observation(
            pub, market=m, structural=None, scarcity=None, appeal=None,
        )
        component_statuses[shadow_ledger.append_component(component)] += 1
        comparison = {
            "horizon_days": 0,
            "comparison_date": evaluation_date.isoformat(),
            "market_price_usd": (m or {}).get("market_price_usd"),
            "source": (m or {}).get("source"),
        }
        outcome = evaluation.build_evaluation_outcome(pub, comparison, today=evaluation_date)
        outcome_statuses[shadow_ledger.append_outcome(outcome)] += 1
        anchored += pub["status"] == "ANCHORED"
        market_available += m is not None

    return {
        "publisher_version": PUBLISHER_VERSION,
        "mode": "DRY_RUN_NOT_A_PUBLICATION" if dry_run else "PROSPECTIVE_SHADOW_PUBLICATION",
        "evaluation_date": evaluation_date.isoformat(),
        "information_cutoff": cutoff.isoformat(),
        "requested_information_cutoff": requested_cutoff.isoformat(),
        "cutoff_resolution": cutoff_resolution,
        "source_commit": source_commit,
        "panel_count": len(publications),
        "anchored": anchored,
        "insufficient_comps": len(publications) - anchored,
        "market_available_h0": market_available,
        "anchor_write_statuses": dict(anchor_statuses),
        "component_write_statuses": dict(component_statuses),
        "outcome_write_statuses": dict(outcome_statuses),
        "provider_calls": 0,
        "provider_credits_used": 0,
        "blended_values_produced": 0,
        "public_price_writes": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--commit", action="store_true")
    parser.add_argument("--source-commit", required=True)
    parser.add_argument(
        "--information-cutoff",
        type=parse_information_cutoff,
        default=None,
        help="Fixed ISO-8601 information cutoff; makes retries for a daily publication deterministic.",
    )
    args = parser.parse_args(argv)

    from backend.db.clients.supabase_client import create_service_role_client

    db = create_service_role_client()
    ledger = ledger_mod.SupabaseShadowLedger(db)
    result = publish(
        db=db,
        ledger=ledger,
        source_commit=args.source_commit,
        now=args.information_cutoff,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
