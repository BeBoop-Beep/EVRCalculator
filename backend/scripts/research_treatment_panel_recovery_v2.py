"""Research-only PkmnPrices NM history recovery for Treatment Hierarchy V1.

Reads the frozen Round-23 matched-treatment ladder universe plus a small frozen
pilot, resolves exact PkmnPrices identities in memory, fetches exact Near-Mint
TCGPlayer history by printing variant, and writes local research artifacts only.

It NEVER writes Supabase rows and NEVER mutates canonical pricing, Collector
Appeal, Overall RIP, Rankings, or Set pages.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping, Sequence

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ROUND23_LADDERS = ROOT / "docs/research/treatment_market_prestige_v3_round23/matched_ladders.json"
DEFAULT_MANIFEST = ROOT / "docs/research/collector_appeal/treatment_panel_recovery_v2/pilot_manifest.json"
DEFAULT_OUTPUT = ROOT / "backend/artifacts/treatment_panel_recovery_v2"
MODEL = "treatment_panel_recovery_v2_pkmnprices_nm"
CONDITION = "Near Mint"
CURRENCY = "usd"
HISTORY_PERIOD = "180d"
HISTORY_DAYS = 180
STRONG_MIN_SHARED_DATES = 90
MODERATE_TIER1_MIN_SHARED_DATES = 30
MODERATE_CONTROLLED_MIN_SHARED_DATES = 90

LOW_RARITIES = {"common", "uncommon", "rare"}
PRINTING_TO_PROVIDER = {
    "non-holo": "Normal",
    "normal": "Normal",
    "holo": "Holofoil",
    "reverse-holo": "Reverse Holofoil",
    "reverse_holo": "Reverse Holofoil",
}


def stable_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode()
    ).hexdigest()


def _chunks(values: Sequence[Any], size: int = 100) -> Iterable[Sequence[Any]]:
    for start in range(0, len(values), size):
        yield values[start:start + size]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def family_key(values: Sequence[str]) -> str:
    return " <> ".join(sorted(str(x) for x in values))


def resolve_sample(manifest: Mapping[str, Any], ladders: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    index = {}
    for ladder in ladders:
        index[
            (
                str(ladder.get("set")),
                family_key(ladder.get("treatments") or []),
                str(ladder.get("identity")),
            )
        ] = dict(ladder)
    resolved = []
    missing = []
    for item in manifest["sample"]:
        key = (str(item["set"]), str(item["family"]), str(item["identity"]))
        ladder = index.get(key)
        if not ladder:
            missing.append(key)
            continue
        resolved.append(
            {
                **dict(item),
                "tier": int(ladder["tier"]),
                "treatments": list(ladder["treatments"]),
                "cardIds": list(ladder["cardIds"]),
                "variantIds": list(ladder["variantIds"]),
            }
        )
    if missing:
        raise RuntimeError(f"frozen pilot identities missing from Round-23 ladder authority: {missing}")
    if len(resolved) != int(manifest["expected"]["identities"]):
        raise RuntimeError("pilot identity count drift")
    unique_cards = sorted({card for row in resolved for card in row["cardIds"]})
    if len(unique_cards) != int(manifest["expected"]["uniqueCards"]):
        raise RuntimeError("pilot unique-card count drift")
    return resolved


def provider_variant_name(
    printing_type: str | None,
    *,
    edition: str | None = None,
    special_type: str | None = None,
) -> str:
    if special_type:
        raise RuntimeError(f"special treatment needs explicit provider mapping: {special_type}")
    key = str(printing_type or "").strip().casefold().replace("_", "-")
    base = PRINTING_TO_PROVIDER.get(key)
    if not base:
        raise RuntimeError(f"unsupported printing_type for history: {printing_type!r}")
    ed = str(edition or "").strip().casefold()
    if ed in {"", "none", "unlimited"}:
        return base
    if ed in {"1st", "1st edition", "first edition", "first_edition"}:
        return f"1st Edition {base}"
    if ed == "shadowless":
        return f"Shadowless {base}"
    raise RuntimeError(f"unsupported edition for provider history: {edition!r}")


def choose_variant(card: Mapping[str, Any], variants: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    options = [dict(v) for v in variants if str(v.get("canonical_card_id")) == str(card["id"])]
    if not options:
        raise RuntimeError(f"no frozen ladder variant maps to canonical card {card['id']}")
    rarity = str(card.get("rarity") or "").strip().casefold().replace(" ", "_")
    plain = [v for v in options if not v.get("special_type")]
    if plain:
        options = plain
    preferred = (
        ["non-holo", "normal", "holo", "reverse-holo"]
        if rarity in LOW_RARITIES
        else ["holo", "non-holo", "normal", "reverse-holo"]
    )
    for printing in preferred:
        matches = [
            v
            for v in options
            if str(v.get("printing_type") or "").casefold().replace("_", "-") == printing
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise RuntimeError(f"ambiguous {printing} ladder variants for canonical card {card['id']}")
    if len(options) == 1:
        return options[0]
    raise RuntimeError(f"unable to choose one treatment variant for canonical card {card['id']}")


def validate_history_rows(rows: Sequence[Mapping[str, Any]], *, variant: str) -> list[dict[str, Any]]:
    by_date: dict[str, dict[str, Any]] = {}
    for raw in rows:
        row = dict(raw)
        if str(row.get("source") or "").casefold() != "tcgplayer":
            raise RuntimeError("history row source drift")
        if str(row.get("currency") or "").upper() != "USD":
            raise RuntimeError("history row currency drift")
        if str(row.get("condition") or "") != CONDITION:
            raise RuntimeError("history row condition drift")
        if str(row.get("variant") or "") != variant:
            raise RuntimeError(
                f"history row variant drift expected={variant!r} got={row.get('variant')!r}"
            )
        day = str(row.get("date") or "")[:10]
        try:
            datetime.fromisoformat(day)
            avg = float(row["avg"])
        except (TypeError, ValueError, KeyError) as exc:
            raise RuntimeError("invalid history row") from exc
        if not math.isfinite(avg) or avg <= 0:
            raise RuntimeError("history avg must be finite and positive")
        if day in by_date:
            raise RuntimeError(f"duplicate exact NM history date {day}")
        by_date[day] = {
            "date": day,
            "avg": avg,
            "low": None if row.get("low") is None else float(row["low"]),
            "high": None if row.get("high") is None else float(row["high"]),
            "source": "tcgplayer",
            "currency": "USD",
            "condition": CONDITION,
            "variant": variant,
        }
    return [by_date[key] for key in sorted(by_date)]


def panel_status(tier: int, shared_dates: int) -> str:
    if tier == 1 and shared_dates >= STRONG_MIN_SHARED_DATES:
        return "PANEL_READY_STRONG"
    if tier == 1 and shared_dates >= MODERATE_TIER1_MIN_SHARED_DATES:
        return "PANEL_READY_MODERATE"
    if tier in {2, 3} and shared_dates >= MODERATE_CONTROLLED_MIN_SHARED_DATES:
        return "PANEL_READY_MODERATE"
    return "HISTORY_BLOCKED"


def build_panel_readiness(
    sample: Sequence[Mapping[str, Any]],
    history_by_card: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    identities = []
    for row in sample:
        card_dates = [
            {str(x["date"]) for x in history_by_card.get(str(card_id), [])}
            for card_id in row["cardIds"]
        ]
        shared = set.intersection(*card_dates) if card_dates and all(card_dates) else set()
        identities.append(
            {
                "family": row["family"],
                "set": row["set"],
                "era": row["era"],
                "identity": row["identity"],
                "tier": row["tier"],
                "cardIds": row["cardIds"],
                "sharedDateCount": len(shared),
                "firstSharedDate": min(shared) if shared else None,
                "lastSharedDate": max(shared) if shared else None,
                "status": panel_status(int(row["tier"]), len(shared)),
            }
        )
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in identities:
        groups[(item["era"], item["family"], item["set"])].append(item)

    set_groups = []
    for (era, family, set_name), items in sorted(groups.items()):
        ready = [x for x in items if x["status"].startswith("PANEL_READY")]
        set_groups.append(
            {
                "era": era,
                "family": family,
                "set": set_name,
                "identityCount": len(items),
                "readyIdentityCount": len(ready),
                "passesG1G4PanelPrerequisite": len(ready) >= 2,
            }
        )

    era_family: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in set_groups:
        if row["passesG1G4PanelPrerequisite"]:
            era_family[(row["era"], row["family"])].append(row)
    era_gates = [
        {
            "era": era,
            "family": family,
            "passingSets": sorted(x["set"] for x in items),
            "passingSetCount": len(items),
            "eraHierarchyGatePass": len(items) >= 2,
        }
        for (era, family), items in sorted(era_family.items())
    ]
    return {
        "identities": identities,
        "setGroups": set_groups,
        "eraFamilyGates": era_gates,
        "anyEraHierarchyGatePass": any(x["eraHierarchyGatePass"] for x in era_gates),
    }


def _variant_rows(client: Any, variant_ids: Sequence[str]) -> list[dict[str, Any]]:
    raw = []
    for chunk in _chunks(sorted(set(variant_ids))):
        raw.extend(
            client.table("card_variants")
            .select("id,card_id,printing_type,special_type,edition,pokemon_tcg_api_id")
            .in_("id", list(chunk))
            .execute()
            .data
            or []
        )
    card_ids = sorted({str(x["card_id"]) for x in raw})
    legacy: dict[str, str] = {}
    for chunk in _chunks(card_ids):
        rows = (
            client.table("cards")
            .select("id,pokemon_tcg_api_id")
            .in_("id", list(chunk))
            .execute()
            .data
            or []
        )
        for row in rows:
            legacy[str(row["id"])] = str(row.get("pokemon_tcg_api_id") or "")
    api_ids = sorted(
        {
            str(x.get("pokemon_tcg_api_id") or legacy.get(str(x["card_id"])) or "")
            for x in raw
            if x
        }
        - {""}
    )
    canonical: dict[str, str] = {}
    for chunk in _chunks(api_ids):
        rows = (
            client.table("pokemon_canonical_cards")
            .select("id,pokemon_tcg_api_card_id")
            .in_("pokemon_tcg_api_card_id", list(chunk))
            .execute()
            .data
            or []
        )
        for row in rows:
            canonical[str(row["pokemon_tcg_api_card_id"])] = str(row["id"])
    result = []
    for row in raw:
        api_id = str(row.get("pokemon_tcg_api_id") or legacy.get(str(row["card_id"])) or "")
        result.append(
            {
                **dict(row),
                "canonical_card_id": canonical.get(api_id),
                "pokemon_tcg_api_id_resolved": api_id or None,
            }
        )
    return result


def _canonical_cards(client: Any, card_ids: Sequence[str]) -> dict[str, dict[str, Any]]:
    rows = []
    for chunk in _chunks(sorted(set(card_ids))):
        rows.extend(
            client.table("pokemon_canonical_cards")
            .select(
                "id,name,number,printed_number,rarity,set_id,source_payload,pokemon_tcg_api_card_id"
            )
            .in_("id", list(chunk))
            .execute()
            .data
            or []
        )
    set_ids = sorted({str(x["set_id"]) for x in rows})
    sets = {}
    for chunk in _chunks(set_ids):
        for row in (
            client.table("sets")
            .select("id,name,era_id")
            .in_("id", list(chunk))
            .execute()
            .data
            or []
        ):
            sets[str(row["id"])] = dict(row)
    return {
        str(row["id"]): {
            **dict(row),
            "set_name": sets.get(str(row["set_id"]), {}).get("name"),
            "era_id": sets.get(str(row["set_id"]), {}).get("era_id"),
        }
        for row in rows
    }


def _cached_identities(client: Any, card_ids: Sequence[str]) -> dict[str, dict[str, Any]]:
    rows = []
    for chunk in _chunks(sorted(set(card_ids))):
        rows.extend(
            client.table("pkmnprices_card_identity_v1")
            .select(
                "provider_card_id,canonical_card_id,tcgplayer_product_id,"
                "match_basis,provider_name,provider_set_id"
            )
            .in_("canonical_card_id", list(chunk))
            .execute()
            .data
            or []
        )
    return {str(x["canonical_card_id"]): dict(x) for x in rows}


def _external_tcgplayer_ids(client: Any, variant_ids: Sequence[str]) -> dict[str, list[str]]:
    rows = []
    for chunk in _chunks(sorted(set(variant_ids))):
        rows.extend(
            client.table("card_variant_external_identities")
            .select("card_variant_id,external_product_id,provider")
            .in_("card_variant_id", list(chunk))
            .eq("provider", "tcgplayer")
            .execute()
            .data
            or []
        )
    out: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        out[str(row["card_variant_id"])].append(str(row["external_product_id"]))
    return {key: sorted(set(values)) for key, values in out.items()}


def _active_b5_runs(client: Any) -> list[dict[str, Any]]:
    """Return only genuinely current B5 runs, not orphaned RUNNING receipts.

    A killed B5 process can leave its row RUNNING forever.  A later invocation
    of the same selector version supersedes that receipt.  The OS-level
    /tmp/pkmnprices-api.lock in the workflow remains the final concurrency
    authority; this DB check is an additional fail-closed signal.
    """
    rows = (
        client.table("pkmnprices_sold_runs_v1")
        .select("run_id,status,started_at,finished_at,selector_version,credits_used,metadata")
        .order("started_at", desc=True)
        .limit(50)
        .execute()
        .data
        or []
    )
    latest_by_selector: dict[str, dict[str, Any]] = {}
    for raw in rows:
        row = dict(raw)
        selector = str(row.get("selector_version") or "")
        if not selector.startswith("bucket_b5_"):
            continue
        latest_by_selector.setdefault(selector, row)
    return [
        row
        for row in latest_by_selector.values()
        if row.get("status") == "RUNNING" and not row.get("finished_at")
    ]


def _build_targets(
    client: Any, sample: Sequence[Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    card_ids = sorted({str(card) for row in sample for card in row["cardIds"]})
    variant_ids = sorted({str(variant) for row in sample for variant in row["variantIds"]})
    cards = _canonical_cards(client, card_ids)
    variants = _variant_rows(client, variant_ids)
    by_card: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for variant in variants:
        if variant.get("canonical_card_id"):
            by_card[str(variant["canonical_card_id"])].append(variant)
    cached = _cached_identities(client, card_ids)
    external = _external_tcgplayer_ids(client, variant_ids)
    targets = []
    failures = []
    for cid in card_ids:
        card = cards.get(cid)
        if not card:
            failures.append({"canonicalCardId": cid, "reason": "CANONICAL_CARD_MISSING"})
            continue
        try:
            selected = choose_variant(card, by_card.get(cid, []))
            provider_variant = provider_variant_name(
                selected.get("printing_type"),
                edition=selected.get("edition"),
                special_type=selected.get("special_type"),
            )
        except Exception as exc:
            failures.append({"canonicalCardId": cid, "reason": f"{type(exc).__name__}: {exc}"})
            continue
        identity = cached.get(cid)
        product_ids = external.get(str(selected["id"]), [])
        strategy = (
            "cached"
            if identity
            else "exact_tcgplayer_product_id"
            if len(product_ids) == 1
            else "exact_set_name_card_name_number"
        )
        payload = dict(card.get("source_payload") or {})
        source_set = dict(payload.get("set") or {})
        targets.append(
            {
                "canonical_card_id": cid,
                "card_name": card.get("name"),
                "number": str(card.get("number") or card.get("printed_number") or ""),
                "rarity": card.get("rarity"),
                "set_name": card.get("set_name"),
                "selected_variant_id": str(selected["id"]),
                "printing_type": selected.get("printing_type"),
                "special_type": selected.get("special_type"),
                "edition": selected.get("edition"),
                "provider_variant": provider_variant,
                "cached_identity": identity,
                "identity_strategy": strategy,
                "tcgplayer_product_id": (
                    str(identity.get("tcgplayer_product_id") or "")
                    if identity
                    else product_ids[0]
                    if len(product_ids) == 1
                    else None
                ),
                "provider_search_name": str(card.get("name") or ""),
                "provider_search_number": str(
                    card.get("number") or card.get("printed_number") or ""
                ),
                "provider_search_set_name": str(
                    source_set.get("name") or card.get("set_name") or ""
                ),
            }
        )
    return targets, {
        "cardCount": len(card_ids),
        "targetCount": len(targets),
        "targetBuildFailures": failures,
        "cachedIdentityCount": sum(bool(x["cached_identity"]) for x in targets),
        "identityLookupNeeded": sum(not bool(x["cached_identity"]) for x in targets),
    }


def _exact_name_number_matches(
    rows: Sequence[Mapping[str, Any]], *, name: str, number: str
) -> list[dict[str, Any]]:
    norm_name = str(name).strip().casefold()
    norm_number = str(number).strip().casefold()
    return [
        dict(row)
        for row in rows
        if str(row.get("name") or "").strip().casefold() == norm_name
        and str(row.get("number") or "").strip().casefold() == norm_number
    ]


def _resolve_provider_identity(
    provider: Any, target: Mapping[str, Any], set_cache: dict[str, int | None]
) -> dict[str, Any]:
    cached = target.get("cached_identity")
    if cached:
        return dict(cached)
    strategy = target["identity_strategy"]
    if strategy == "exact_tcgplayer_product_id":
        rows = provider.cards_by_tcgplayer_id(
            target["tcgplayer_product_id"], language="English", per_page=5
        )
        exact = [
            dict(row)
            for row in rows
            if str(row.get("tcg_player_id") or "") == str(target["tcgplayer_product_id"])
        ]
    elif strategy == "exact_set_name_card_name_number":
        rows = provider.cards_by_name_number(
            name=target["provider_search_name"],
            number=target["provider_search_number"],
            language="English",
            per_page=100,
        )
        exact = _exact_name_number_matches(
            rows,
            name=target["provider_search_name"],
            number=target["provider_search_number"],
        )
        if len(exact) > 1:
            set_name = str(target["provider_search_set_name"])
            key = set_name.casefold()
            if key not in set_cache:
                set_rows = provider.sets_by_name(set_name, language="English", per_page=100)
                exact_sets = [
                    row
                    for row in set_rows
                    if str(row.get("name") or "").strip().casefold() == key
                    and str(row.get("language") or "English").casefold() == "english"
                ]
                set_cache[key] = int(exact_sets[0]["id"]) if len(exact_sets) == 1 else None
            sid = set_cache[key]
            if sid is not None:
                exact = [
                    row
                    for row in exact
                    if str((row.get("set") or {}).get("id") or "") == str(sid)
                ]
    else:
        raise RuntimeError(f"unsupported identity strategy: {strategy}")
    if len(exact) != 1:
        raise RuntimeError(f"provider identity count {len(exact)}")
    row = exact[0]
    return {
        "provider_card_id": int(row["id"]),
        "canonical_card_id": target["canonical_card_id"],
        "tcgplayer_product_id": str(
            row.get("tcg_player_id") or target.get("tcgplayer_product_id") or ""
        ),
        "match_basis": "research_" + strategy,
        "provider_name": row.get("name"),
        "provider_set_id": str((row.get("set") or {}).get("id") or ""),
    }


def _provider_variant_check(
    provider: Any, provider_card_id: int, expected_variant: str
) -> dict[str, Any]:
    payload = provider.card(provider_card_id, currency=CURRENCY)
    prices = list(payload.get("prices") or [])
    variants = sorted(
        {
            str(row.get("variant"))
            for row in prices
            if str(row.get("source") or "").casefold() == "tcgplayer"
            and str(row.get("currency") or "").upper() == "USD"
            and str(row.get("condition") or "") == CONDITION
            and row.get("variant")
        }
    )
    if expected_variant not in variants:
        raise RuntimeError(
            f"expected provider NM variant {expected_variant!r} unavailable; observed={variants}"
        )
    return {
        "providerCardId": provider_card_id,
        "observedNmVariants": variants,
        "selectedVariant": expected_variant,
    }


def _history_page(provider: Any, provider_card_id: int, variant: str) -> list[dict[str, Any]]:
    payload = provider.price_history_page(
        provider_card_id,
        currency=CURRENCY,
        period=HISTORY_PERIOD,
        condition=CONDITION,
        variant=variant,
        limit=365,
        page=1,
    )
    pagination = dict(payload.get("pagination") or {})
    if int(pagination.get("total_pages") or 1) > 1:
        raise RuntimeError("exact filtered history unexpectedly exceeds one 365-row page")
    return validate_history_rows(list(payload.get("data") or []), variant=variant)


def preflight(client: Any, manifest: Mapping[str, Any]) -> dict[str, Any]:
    sample = resolve_sample(manifest, load_json(ROUND23_LADDERS))
    targets, target_meta = _build_targets(client, sample)
    max_history = len(targets) * HISTORY_DAYS
    return {
        "mode": "preflight",
        "model": MODEL,
        "manifestFingerprint": stable_hash(manifest),
        "sampleFingerprint": stable_hash(sample),
        "sampleIdentityCount": len(sample),
        "families": sorted({x["family"] for x in sample}),
        "sets": sorted({x["set"] for x in sample}),
        "targetMeta": target_meta,
        "maxHistoryRowsCredits": max_history,
        "configuredCreditCap": int(manifest["provider"]["creditCap"]),
        "activeB5Runs": _active_b5_runs(client),
        "providerCalls": 0,
        "databaseWrites": 0,
        "canonicalPriceMutation": False,
        "collectorMutation": False,
        "overallRipMutation": False,
        "_sample": sample,
        "_targets": targets,
    }


def collect(client: Any, manifest: Mapping[str, Any], *, output_dir: Path) -> dict[str, Any]:
    plan = preflight(client, manifest)
    if plan["activeB5Runs"]:
        return {
            **{key: value for key, value in plan.items() if not key.startswith("_")},
            "status": "DEFERRED_B5_ACTIVE",
            "providerCalls": 0,
            "databaseWrites": 0,
        }

    from backend.pricing_pipeline.pkmnprices_client import PkmnPricesClient
    from backend.pricing_pipeline.pkmnprices_credentials import load_pkmnprices_credentials

    creds = load_pkmnprices_credentials(allow_frontend_fallback=False)
    provider = PkmnPricesClient(creds.api_key, min_request_interval=0.55)
    credit_cap = int(manifest["provider"]["creditCap"])
    histories: dict[str, list[dict[str, Any]]] = {}
    receipts = []
    set_cache: dict[str, int | None] = {}

    for target in plan["_targets"]:
        if provider.credits_charged >= credit_cap:
            receipts.append(
                {"canonicalCardId": target["canonical_card_id"], "status": "BLOCKED_CREDIT_CAP"}
            )
            continue
        before = provider.credits_charged
        try:
            identity = _resolve_provider_identity(provider, target, set_cache)
            variant_check = _provider_variant_check(
                provider, int(identity["provider_card_id"]), str(target["provider_variant"])
            )
            history = _history_page(
                provider, int(identity["provider_card_id"]), str(target["provider_variant"])
            )
            if provider.credits_charged > credit_cap:
                raise RuntimeError("research credit cap exceeded")
            histories[target["canonical_card_id"]] = history
            receipts.append(
                {
                    "canonicalCardId": target["canonical_card_id"],
                    "status": "COLLECTED",
                    "providerCardId": identity["provider_card_id"],
                    "matchBasis": identity["match_basis"],
                    "variantCheck": variant_check,
                    "historyRows": len(history),
                    "credits": provider.credits_charged - before,
                }
            )
        except Exception as exc:
            receipts.append(
                {
                    "canonicalCardId": target["canonical_card_id"],
                    "status": "BLOCKED",
                    "error": f"{type(exc).__name__}: {exc}",
                    "credits": provider.credits_charged - before,
                }
            )

    readiness = build_panel_readiness(plan["_sample"], histories)
    output_dir.mkdir(parents=True, exist_ok=True)
    public_plan = {key: value for key, value in plan.items() if not key.startswith("_")}
    artifact = {
        "status": "COLLECTED",
        "collectedAt": datetime.now(timezone.utc).isoformat(),
        **public_plan,
        "providerCalls": provider.successful_request_count,
        "providerRequestAttempts": provider.request_attempt_count,
        "providerCreditsUsed": provider.credits_charged,
        "databaseWrites": 0,
        "receipts": receipts,
        "panelReadiness": readiness,
        "historyCardCount": len(histories),
        "historyRowCount": sum(len(value) for value in histories.values()),
    }
    (output_dir / "summary.json").write_text(
        json.dumps(artifact, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    (output_dir / "history.json").write_text(
        json.dumps(histories, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    (output_dir / "panel_readiness.json").write_text(
        json.dumps(readiness, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    return artifact


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--collect", action="store_true")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    load_dotenv(ROOT / "backend/.env", override=False)
    from backend.db.clients.supabase_client import create_service_role_client

    client = create_service_role_client()
    manifest = load_json(args.manifest)
    result = (
        preflight(client, manifest)
        if args.preflight
        else collect(client, manifest, output_dir=args.output_dir)
    )
    public = {key: value for key, value in result.items() if not key.startswith("_")}
    if args.json:
        print(json.dumps(public, indent=2, ensure_ascii=False, default=str))
    else:
        print(public)
    return 3 if public.get("status") == "DEFERRED_B5_ACTIVE" else 0


if __name__ == "__main__":
    raise SystemExit(main())
