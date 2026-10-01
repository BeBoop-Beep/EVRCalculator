"""Research-only PkmnPrices NM history recovery for Treatment matched ladders.

This command NEVER mutates canonical pricing or Collector/Overall authority.
It reads the frozen Round-24 ladder ledger + current identity mappings, fetches
PkmnPrices TCGPlayer Near-Mint history for already-mapped provider cards, and
writes local research artifacts only.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping, Sequence

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.pricing_pipeline.pkmnprices_client import PkmnPricesClient
from backend.pricing_pipeline.pkmnprices_credentials import load_pkmnprices_credentials

ROUND24 = ROOT / "docs/research/treatment_market_prestige_v3_round24/repaired_ladders.json"
DEFAULT_OUT = ROOT / "backend/artifacts/research/treatment_panel_recovery_v2"
DEFAULT_COHORT_DATE = "2026-09-29"
SOURCE_VERSION = "pkmnprices_tcgplayer_nm_history_recovery_v2"

STRONG_MIN_SHARED_DATES = 90
MODERATE_TIER1_MIN_SHARED_DATES = 30


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode("utf-8")
    ).hexdigest()


def _paged(query_factory):
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        page = list(query_factory().range(start, start + 999).execute().data or [])
        rows.extend(dict(row) for row in page)
        if len(page) < 1000:
            return rows
        start += 1000


def _text(value: Any) -> str:
    return str(value or "").strip()


def _norm(value: Any) -> str:
    text = _text(value).casefold()
    for old, new in (
        ("poké", "poke"), ("é", "e"), ("_", " "), ("-", " "),
        ("  ", " "),
    ):
        text = text.replace(old, new)
    return " ".join(text.split())


def provider_variant_identity(value: Any) -> tuple[str | None, str | None, str | None]:
    """Map provider printing text into conservative edition/finish/special axes."""
    text = _norm(value)
    if not text:
        return None, None, None

    edition = None
    if "1st edition" in text or "first edition" in text:
        edition = "first-edition"
    elif "shadowless" in text:
        edition = "shadowless"
    elif "unlimited" in text:
        edition = "unlimited"

    if "reverse" in text and "holo" in text:
        finish = "reverse-holo"
    elif "holo" in text:
        finish = "holo"
    elif text in {"normal", "non holo", "nonholo"} or "normal" in text:
        finish = "non-holo"
    else:
        finish = None

    special = None
    if "master ball" in text or "masterball" in text:
        special = "master-ball"
    elif "poke ball" in text or "pokeball" in text:
        special = "pokeball"
    elif "stamped" in text or "stamp" in text:
        special = "stamped"

    return edition, finish, special


def _local_variant_identity(meta: Mapping[str, Any], set_name: str) -> tuple[str | None, str | None, str | None]:
    edition = _text(meta.get("edition")) or None
    finish = _text(meta.get("printing_type")) or None
    special = _text(meta.get("special_type")) or None
    # Round 24 explicitly treats edition as not-applicable for non-vintage modern
    # environments. Do not force provider rows to carry a null/nonexistent label.
    return edition, finish, special


def provider_row_matches_local(
    provider_variant: Any,
    local_meta: Mapping[str, Any],
    set_name: str,
) -> bool:
    p_edition, p_finish, p_special = provider_variant_identity(provider_variant)
    l_edition, l_finish, l_special = _local_variant_identity(local_meta, set_name)

    if l_finish and p_finish != l_finish:
        return False

    # If the local variant explicitly carries a special treatment, require it.
    if l_special:
        expected = _norm(l_special).replace(" ", "-")
        observed = _norm(p_special).replace(" ", "-")
        if observed != expected:
            # Common provider spelling aliases.
            aliases = {
                "poke-ball": "pokeball",
                "master-ball": "master-ball",
                "journey-together-stamped": "stamped",
            }
            if aliases.get(expected, expected) != aliases.get(observed, observed):
                return False
    elif p_special:
        # Do not let a Master Ball / Poké Ball / stamped row satisfy a plain-holo
        # local identity.
        return False

    if l_edition:
        expected = _norm(l_edition).replace(" ", "-")
        observed = _norm(p_edition).replace(" ", "-")
        if expected != observed:
            return False

    return True


def load_recovery_cohort(client: Any, *, cohort_date: str) -> dict[str, Any]:
    run_rows = _paged(
        lambda: client.table("calculation_runs")
        .select("target_id")
        .eq("market_date", cohort_date)
        .eq("target_type", "set")
    )
    set_ids = sorted({_text(row.get("target_id")) for row in run_rows if row.get("target_id")})
    if not set_ids:
        raise RuntimeError(f"no simulation Set cohort found for {cohort_date}")

    set_rows = _paged(
        lambda: client.table("sets")
        .select("id,name,era_id")
        .in_("id", set_ids)
    )
    era_ids = sorted({_text(row.get("era_id")) for row in set_rows if row.get("era_id")})
    era_rows = _paged(lambda: client.table("eras").select("id,name").in_("id", era_ids))
    eras = {_text(row["id"]): _text(row["name"]) for row in era_rows}
    sets = {
        _text(row["name"]): {
            "set_id": _text(row["id"]),
            "set_name": _text(row["name"]),
            "era_name": eras.get(_text(row.get("era_id"))),
        }
        for row in set_rows
    }

    mappings = _paged(
        lambda: client.table("pkmnprices_card_identity_v1")
        .select("canonical_card_id,provider_card_id,match_basis,tcgplayer_product_id,provider_name,provider_set_id")
    )
    by_card = {_text(row["canonical_card_id"]): row for row in mappings if row.get("canonical_card_id")}

    ladders = json.loads(ROUND24.read_text(encoding="utf-8"))
    in_scope = [
        dict(ladder) for ladder in ladders
        if _text(ladder.get("set")) in sets and _text(ladder.get("round24Status")) == "HISTORY_BLOCKED"
    ]
    fully_mapped = [
        ladder for ladder in in_scope
        if ladder.get("cardIds") and all(_text(card_id) in by_card for card_id in ladder["cardIds"])
    ]

    provider_cards: dict[int, dict[str, Any]] = {}
    for ladder in fully_mapped:
        for card_id in ladder["cardIds"]:
            mapping = by_card[_text(card_id)]
            provider_id = int(mapping["provider_card_id"])
            provider_cards[provider_id] = {
                "provider_card_id": provider_id,
                "canonical_card_id": _text(card_id),
                "match_basis": mapping.get("match_basis"),
                "tcgplayer_product_id": mapping.get("tcgplayer_product_id"),
            }

    return {
        "cohortDate": cohort_date,
        "sets": list(sorted(sets.values(), key=lambda row: row["set_name"])),
        "round24HistoryBlockedInCohort": len(in_scope),
        "fullyMappedLadders": fully_mapped,
        "providerCards": list(sorted(provider_cards.values(), key=lambda row: row["provider_card_id"])),
        "providerIdentityCount": len(provider_cards),
        "cohortFingerprint": canonical_hash({
            "cohortDate": cohort_date,
            "sets": sorted(set_ids),
            "ladders": [
                {
                    "identity": ladder.get("identity"),
                    "set": ladder.get("set"),
                    "tier": ladder.get("tier"),
                    "cardIds": ladder.get("cardIds"),
                    "variantIds": ladder.get("variantIds"),
                }
                for ladder in fully_mapped
            ],
            "providerCards": list(sorted(provider_cards)),
        }),
    }


def fetch_card_history(
    provider: PkmnPricesClient,
    provider_card_id: int,
    *,
    period: str,
    condition: str,
    credit_cap: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page = 1
    while True:
        remaining = credit_cap - provider.credits_charged
        if remaining <= 0:
            break
        limit = max(1, min(365, remaining))
        payload = provider.price_history_page(
            provider_card_id,
            currency="usd",
            period=period,
            condition=condition,
            variant=None,
            limit=limit,
            page=page,
        )
        data = payload.get("data") or []
        if not isinstance(data, list):
            raise RuntimeError("PkmnPrices price history data is not an array")
        for row in data:
            if not isinstance(row, dict):
                continue
            if _norm(row.get("source")) != "tcgplayer":
                continue
            if _norm(row.get("currency")) != "usd":
                continue
            if _norm(row.get("condition")) != _norm(condition):
                continue
            try:
                avg = float(row.get("avg"))
            except (TypeError, ValueError):
                continue
            if avg <= 0:
                continue
            day = _text(row.get("date"))[:10]
            if len(day) != 10:
                continue
            rows.append({
                "date": day,
                "source": "tcgplayer",
                "currency": "USD",
                "condition": condition,
                "variant": _text(row.get("variant")),
                "avg": avg,
                "low": row.get("low"),
                "high": row.get("high"),
            })

        pagination = payload.get("pagination") or {}
        try:
            total_pages = int(pagination.get("total_pages") or page)
        except (TypeError, ValueError):
            total_pages = page
        if page >= total_pages or not data:
            break
        page += 1
    return rows


def evaluate_ladders(cohort: Mapping[str, Any], histories: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, Any]:
    details = []
    status_counts = Counter()
    by_set = Counter()
    by_family = Counter()

    for ladder in cohort["fullyMappedLadders"]:
        metas = {
            _text(row.get("id")): dict(row)
            for row in ladder.get("editionFinishMetadata") or []
            if row.get("id")
        }
        card_ids = [_text(value) for value in ladder.get("cardIds") or []]
        variant_ids = [_text(value) for value in ladder.get("variantIds") or []]
        if not card_ids or not variant_ids:
            continue

        # Round 24 ladders may contain multiple variants of one canonical card or
        # distinct canonical cards. Build each local variant's eligible date set.
        date_sets: list[set[str]] = []
        variant_receipts = []
        for variant_id in variant_ids:
            meta = metas.get(variant_id)
            if meta is None:
                variant_receipts.append({"variantId": variant_id, "status": "LOCAL_METADATA_MISSING"})
                date_sets.append(set())
                continue

            matched_dates: set[str] = set()
            matched_provider_variants: set[str] = set()
            # Associate the local variant with every canonical member only when
            # provider history actually contains a matching printing identity.
            for card_id in card_ids:
                for row in histories.get(card_id, []):
                    if provider_row_matches_local(row.get("variant"), meta, _text(ladder.get("set"))):
                        matched_dates.add(_text(row.get("date")))
                        matched_provider_variants.add(_text(row.get("variant")))

            date_sets.append(matched_dates)
            variant_receipts.append({
                "variantId": variant_id,
                "printingType": meta.get("printing_type"),
                "specialType": meta.get("special_type"),
                "edition": meta.get("edition"),
                "matchedProviderVariants": sorted(matched_provider_variants),
                "dateCount": len(matched_dates),
            })

        shared = set.intersection(*date_sets) if date_sets and all(date_sets) else set()
        n = len(shared)
        tier = int(ladder.get("tier") or 0)
        if n >= STRONG_MIN_SHARED_DATES:
            status = "PANEL_READY_STRONG"
        elif tier == 1 and n >= MODERATE_TIER1_MIN_SHARED_DATES:
            status = "PANEL_READY_MODERATE"
        else:
            status = "HISTORY_BLOCKED"

        status_counts[status] += 1
        by_set[f"{ladder.get('set')}|{status}"] += 1
        family = "|".join(sorted(_text(x) for x in ladder.get("treatments") or []))
        by_family[f"{family}|{status}"] += 1
        details.append({
            "identity": ladder.get("identity"),
            "set": ladder.get("set"),
            "era": ladder.get("era"),
            "tier": tier,
            "treatments": ladder.get("treatments"),
            "cardIds": card_ids,
            "variantIds": variant_ids,
            "round24Status": ladder.get("round24Status"),
            "recoveryStatus": status,
            "sharedDateCount": n,
            "firstSharedDate": min(shared) if shared else None,
            "lastSharedDate": max(shared) if shared else None,
            "variantReceipts": variant_receipts,
        })

    return {
        "statusCounts": dict(status_counts),
        "bySetAndStatus": dict(sorted(by_set.items())),
        "byTreatmentFamilyAndStatus": dict(sorted(by_family.items())),
        "ladders": details,
    }


def build_report(result: Mapping[str, Any]) -> str:
    ev = result["evaluation"]
    lines = [
        "# Treatment Panel Recovery V2 — PkmnPrices NM History",
        "",
        f"- Built at: `{result['builtAt']}`",
        f"- Source: `{SOURCE_VERSION}`",
        f"- Cohort date: `{result['cohort']['cohortDate']}`",
        f"- Cohort fingerprint: `{result['cohort']['cohortFingerprint']}`",
        f"- Already-mapped provider cards queried: **{result['collection']['providerCardsQueried']}**",
        f"- Provider credits used: **{result['collection']['creditsUsed']}** / {result['collection']['creditCap']}",
        f"- Raw NM history rows retained: **{result['collection']['historyRows']}**",
        "",
        "## Frozen Round-24 readiness rerun",
        "",
        f"- PANEL_READY_STRONG: **{ev['statusCounts'].get('PANEL_READY_STRONG', 0)}**",
        f"- PANEL_READY_MODERATE: **{ev['statusCounts'].get('PANEL_READY_MODERATE', 0)}**",
        f"- HISTORY_BLOCKED: **{ev['statusCounts'].get('HISTORY_BLOCKED', 0)}**",
        "",
        "This recovery run does not fit a Treatment estimator and does not mutate production pricing, Collector Appeal, Overall RIP, Rankings, or Set pages.",
        "",
        "## Per-Set",
        "",
    ]
    for key, count in ev["bySetAndStatus"].items():
        lines.append(f"- {key}: {count}")
    return "\n".join(lines) + "\n"


def execute(
    client: Any,
    *,
    collect: bool,
    cohort_date: str,
    period: str,
    condition: str,
    credit_cap: int,
    output_dir: Path,
) -> dict[str, Any]:
    cohort = load_recovery_cohort(client, cohort_date=cohort_date)
    preflight = {
        "status": "PREFLIGHT_OK",
        "sourceVersion": SOURCE_VERSION,
        "providerCallsPlanned": 0 if not collect else None,
        "databaseWrites": 0,
        "canonicalPriceMutation": False,
        "collectorMutation": False,
        "overallRipMutation": False,
        "round24HistoryBlockedInCohort": cohort["round24HistoryBlockedInCohort"],
        "fullyMappedLadders": len(cohort["fullyMappedLadders"]),
        "providerIdentityCount": cohort["providerIdentityCount"],
        "cohortFingerprint": cohort["cohortFingerprint"],
    }
    if not collect:
        return {"preflight": preflight, "cohort": cohort}

    credentials = load_pkmnprices_credentials(allow_frontend_fallback=False)
    provider = PkmnPricesClient(credentials.api_key, min_request_interval=0.60)
    history_by_card: dict[str, list[dict[str, Any]]] = {}
    receipts = []
    provider_by_card = {row["canonical_card_id"]: row for row in cohort["providerCards"]}

    for card in cohort["providerCards"]:
        if provider.credits_charged >= credit_cap:
            break
        rows = fetch_card_history(
            provider,
            int(card["provider_card_id"]),
            period=period,
            condition=condition,
            credit_cap=credit_cap,
        )
        history_by_card[_text(card["canonical_card_id"])] = rows
        receipts.append({
            **card,
            "historyRows": len(rows),
            "variants": sorted({_text(row.get("variant")) for row in rows}),
            "firstDate": min((_text(row.get("date")) for row in rows), default=None),
            "lastDate": max((_text(row.get("date")) for row in rows), default=None),
        })

    evaluation = evaluate_ladders(cohort, history_by_card)
    result = {
        "builtAt": datetime.now(timezone.utc).isoformat(),
        "preflight": preflight,
        "cohort": {
            **cohort,
            # Keep the report artifact compact; full ladder input already exists in
            # the immutable Round-24 source artifact.
            "fullyMappedLadders": [
                {
                    "identity": x.get("identity"), "set": x.get("set"), "era": x.get("era"),
                    "tier": x.get("tier"), "cardIds": x.get("cardIds"), "variantIds": x.get("variantIds"),
                    "treatments": x.get("treatments"), "round24Status": x.get("round24Status"),
                }
                for x in cohort["fullyMappedLadders"]
            ],
        },
        "collection": {
            "period": period,
            "condition": condition,
            "creditCap": credit_cap,
            "creditsUsed": provider.credits_charged,
            "providerRequests": provider.successful_request_count,
            "providerCardsQueried": len(history_by_card),
            "providerCardsPlanned": cohort["providerIdentityCount"],
            "historyRows": sum(len(rows) for rows in history_by_card.values()),
            "receipts": receipts,
        },
        "evaluation": evaluation,
        "productionWrites": 0,
        "canonicalPriceMutation": False,
        "collectorMutation": False,
        "overallRipMutation": False,
    }
    result["resultFingerprint"] = canonical_hash({
        "cohort": result["cohort"],
        "collection": result["collection"],
        "evaluation": result["evaluation"],
    })

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    (output_dir / "history_rows.json").write_text(
        json.dumps(history_by_card, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    (output_dir / "FINAL_REPORT.md").write_text(build_report(result), encoding="utf-8")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--collect", action="store_true")
    parser.add_argument("--cohort-date", default=DEFAULT_COHORT_DATE)
    parser.add_argument("--period", default="180d")
    parser.add_argument("--condition", default="Near Mint")
    parser.add_argument("--credit-cap", type=int, default=20000)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    if args.credit_cap < 1 or args.credit_cap > 20000:
        raise SystemExit("credit-cap must be between 1 and 20000 for this research pilot")

    load_dotenv(ROOT / "backend/.env", override=False)
    from backend.db.clients.supabase_client import supabase

    result = execute(
        supabase,
        collect=bool(args.collect),
        cohort_date=args.cohort_date,
        period=args.period,
        condition=args.condition,
        credit_cap=args.credit_cap,
        output_dir=args.output_dir,
    )
    summary = {
        "mode": "collect" if args.collect else "preflight",
        "status": result.get("preflight", {}).get("status", "COMPLETE"),
        "cohortFingerprint": result.get("preflight", {}).get("cohortFingerprint"),
        "fullyMappedLadders": result.get("preflight", {}).get("fullyMappedLadders"),
        "providerIdentityCount": result.get("preflight", {}).get("providerIdentityCount"),
        "creditsUsed": (result.get("collection") or {}).get("creditsUsed", 0),
        "providerCardsQueried": (result.get("collection") or {}).get("providerCardsQueried", 0),
        "statusCounts": (result.get("evaluation") or {}).get("statusCounts"),
        "databaseWrites": 0,
        "canonicalPriceMutation": False,
        "collectorMutation": False,
        "overallRipMutation": False,
    }
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
