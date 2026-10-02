"""Research-only minimal expansion for the frozen Treatment Hierarchy V1 gates.

Targets exactly two independent SIR-vs-Ultra-Rare subject identities in each of
four Sets (two Mega Evolution-era Sets, two Scarlet & Violet-era Sets). Provider
identities are resolved in-memory only. No Supabase or canonical pricing writes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.pricing_pipeline.pkmnprices_client import PkmnPricesAPIError, PkmnPricesClient
from backend.pricing_pipeline.pkmnprices_credentials import load_pkmnprices_credentials
from backend.scripts.research_treatment_panel_recovery_v2 import _history_rows

VERSION = "treatment_gate_expansion_double_ultra_v1"
MARKET_DATE = "2026-09-29"
STRONG_DAYS = 90
MODERATE_DAYS = 30

TARGETS = {
    "Chaos Rising": ("pokemon:pokemon:658", "pokemon:pokemon:573"),
    "Mega Evolution": ("pokemon:pokemon:282", "pokemon:pokemon:448"),
    "Paldean Fates": ("pokemon:pokemon:6", "pokemon:pokemon:282"),
    "Surging Sparks": ("pokemon:pokemon:635", "pokemon:pokemon:25"),
}
ERA_BY_SET = {
    "Chaos Rising": "Mega Evolution",
    "Mega Evolution": "Mega Evolution",
    "Paldean Fates": "Scarlet and Violet",
    "Surging Sparks": "Scarlet and Violet",
}
TREATMENTS = {"Double Rare", "Ultra Rare"}


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _number_key(value: Any) -> str:
    text = str(value or "").strip().casefold()
    if "/" in text:
        text = text.split("/", 1)[0]
    text = text.lstrip("0") or "0"
    return str(int(text)) if text.isdigit() else text


def _provider_name_matches(provider_name: Any, target_name: Any) -> bool:
    provider = str(provider_name or "").strip().casefold()
    target = str(target_name or "").strip().casefold()
    return bool(target) and (provider == target or provider.startswith(target + " - "))


def _exact_name_number_matches(rows: list[dict[str, Any]], *, name: str, number: str) -> list[dict[str, Any]]:
    key = _number_key(number)
    return [
        row for row in rows
        if _provider_name_matches(row.get("name"), name)
        and _number_key(row.get("number")) == key
    ]


def _provider_set_matches(row: dict[str, Any], set_name: str) -> bool:
    observed = str((row.get("set") or {}).get("name") or "").strip().casefold()
    target = str(set_name).strip().casefold()
    return observed == target or observed.endswith(": " + target)


def _printing_variant(printing_type: Any, special_type: Any) -> str | None:
    if special_type:
        return None
    key = str(printing_type or "").strip().casefold().replace("_", "-")
    return {
        "holo": "Holofoil",
        "holofoil": "Holofoil",
        "reverse-holo": "Reverse Holofoil",
        "non-holo": "Normal",
        "normal": "Normal",
    }.get(key)


def _paged(query_factory) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        page = list(query_factory().range(start, start + 999).execute().data or [])
        rows.extend(dict(row) for row in page)
        if len(page) < 1000:
            return rows
        start += 1000


def _subject_keys(db: Any, card_ids: list[str]) -> dict[str, str]:
    links: list[dict[str, Any]] = []
    for start in range(0, len(card_ids), 100):
        links.extend(
            db.table("pokemon_card_collector_entity_links")
            .select("pokemon_canonical_card_id,collector_entity_id,active")
            .in_("pokemon_canonical_card_id", card_ids[start:start + 100])
            .eq("active", True)
            .execute().data or []
        )
    entity_ids = sorted({str(row["collector_entity_id"]) for row in links})
    refs: dict[str, dict[str, Any]] = {}
    for start in range(0, len(entity_ids), 100):
        rows = (
            db.table("pokemon_collector_entity_reference")
            .select("id,entity_type,canonical_key")
            .in_("id", entity_ids[start:start + 100])
            .execute().data or []
        )
        refs.update({str(row["id"]): dict(row) for row in rows})
    grouped: dict[str, list[str]] = defaultdict(list)
    for row in links:
        ref = refs.get(str(row["collector_entity_id"]))
        if ref and ref.get("entity_type") in {"pokemon", "trainer"}:
            grouped[str(row["pokemon_canonical_card_id"])].append(
                f'{ref["entity_type"]}:{ref["canonical_key"]}'
            )
    return {cid: " + ".join(sorted(set(values))) for cid, values in grouped.items() if values}


def build_targets(db: Any, market_date: str) -> dict[str, Any]:
    set_rows = (
        db.table("sets").select("id,name").in_("name", sorted(TARGETS)).execute().data or []
    )
    set_by_name = {str(row["name"]): str(row["id"]) for row in set_rows}
    if set(set_by_name) != set(TARGETS):
        raise RuntimeError(f"target Set resolution incomplete: {sorted(set(TARGETS) - set(set_by_name))}")

    run_rows = _paged(
        lambda: db.table("calculation_runs")
        .select("id,target_id,created_at")
        .eq("market_date", market_date)
        .eq("target_type", "set")
        .in_("target_id", list(set_by_name.values()))
        .order("created_at", desc=True)
    )
    run_by_set: dict[str, str] = {}
    for row in run_rows:
        run_by_set.setdefault(str(row["target_id"]), str(row["id"]))
    if len(run_by_set) != 4:
        raise RuntimeError("simulation authority missing for one or more target Sets")

    cards = _paged(
        lambda: db.table("pokemon_canonical_cards")
        .select("id,set_id,name,number,printed_number,rarity,pokemon_tcg_api_card_id")
        .in_("set_id", list(set_by_name.values()))
        .in_("rarity", sorted(TREATMENTS))
    )
    card_ids = [str(row["id"]) for row in cards]
    subjects = _subject_keys(db, card_ids)

    identities = _paged(
        lambda: db.table("pkmnprices_card_identity_v1")
        .select("provider_card_id,canonical_card_id,match_basis,metadata")
        .in_("canonical_card_id", card_ids)
    )
    identity_by_card = {str(row["canonical_card_id"]): dict(row) for row in identities}

    legacy_api_ids = sorted({
        str(row.get("pokemon_tcg_api_card_id"))
        for row in cards if row.get("pokemon_tcg_api_card_id")
    })
    legacy_rows: list[dict[str, Any]] = []
    for start in range(0, len(legacy_api_ids), 100):
        legacy_rows.extend(
            db.table("cards")
            .select("id,pokemon_tcg_api_id,rarity,card_number")
            .in_("pokemon_tcg_api_id", legacy_api_ids[start:start + 100])
            .execute().data or []
        )
    legacy_by_api = {str(row["pokemon_tcg_api_id"]): dict(row) for row in legacy_rows}

    selected: list[dict[str, Any]] = []
    for row in cards:
        set_name = next(name for name, sid in set_by_name.items() if sid == str(row["set_id"]))
        subject = subjects.get(str(row["id"]))
        if subject not in TARGETS[set_name]:
            continue
        selected.append({**dict(row), "set_name": set_name, "subject_key": subject})

    if len(selected) != 16:
        raise RuntimeError(f"expected 16 target cards, found {len(selected)}")

    inputs: list[dict[str, Any]] = []
    for card in selected:
        run_id = run_by_set[str(card["set_id"])]
        identity = identity_by_card.get(str(card["id"]))
        direct_variant = str((identity or {}).get("metadata", {}).get("card_variant_id") or "")

        legacy = legacy_by_api.get(str(card.get("pokemon_tcg_api_card_id") or ""))
        sim_rows: list[dict[str, Any]] = []
        if legacy:
            sim_rows = list(
                db.table("simulation_input_cards")
                .select("card_variant_id,card_id,card_name,effective_pull_rate")
                .eq("calculation_run_id", run_id)
                .eq("card_id", str(legacy["id"]))
                .execute().data or []
            )
        if len(sim_rows) != 1:
            raise RuntimeError(
                f"simulation variant resolution failed card={card['id']} api={card.get('pokemon_tcg_api_card_id')} rows={len(sim_rows)}"
            )
        variant_id = str(sim_rows[0]["card_variant_id"])
        if direct_variant and direct_variant != variant_id:
            raise RuntimeError(f"frozen identity variant drift card={card['id']}")

        pulls = list(
            db.table("simulation_card_variant_pull_rates")
            .select("modeled_probability,printing_type,special_type,status")
            .eq("calculation_run_id", run_id)
            .eq("card_variant_id", variant_id)
            .execute().data or []
        )
        if len(pulls) != 1 or not pulls[0].get("modeled_probability"):
            raise RuntimeError(f"pull authority missing card={card['id']}")
        provider_variant = _printing_variant(pulls[0].get("printing_type"), pulls[0].get("special_type"))
        if not provider_variant:
            raise RuntimeError(f"provider variant unsupported card={card['id']}")

        inputs.append({
            "canonical_card_id": str(card["id"]),
            "set_id": str(card["set_id"]),
            "set_name": card["set_name"],
            "era_name": ERA_BY_SET[card["set_name"]],
            "subject_key": card["subject_key"],
            "card_name": card["name"],
            "number": str(card["number"]),
            "printed_number": card.get("printed_number"),
            "rarity": card["rarity"],
            "card_variant_id": variant_id,
            "provider_variant": provider_variant,
            "modeled_probability": float(pulls[0]["modeled_probability"]),
            "provider_card_id": None if not identity else int(identity["provider_card_id"]),
            "identity_source": None if not identity else str(identity.get("match_basis") or "cached"),
        })

    return {
        "version": VERSION,
        "market_date": market_date,
        "cards": sorted(inputs, key=lambda x: (x["era_name"], x["set_name"], x["subject_key"], x["rarity"])),
        "fingerprint": _hash(inputs),
    }


def resolve_provider_id(provider: PkmnPricesClient, row: dict[str, Any]) -> tuple[int, str]:
    if row.get("provider_card_id"):
        return int(row["provider_card_id"]), "cached"

    candidates = provider.cards_by_name_number(
        name=row["card_name"], number=row["number"], language="English", per_page=100
    )
    exact = _exact_name_number_matches(candidates, name=row["card_name"], number=row["number"])
    if len(exact) > 1:
        exact = [item for item in exact if _provider_set_matches(item, row["set_name"])]
    if len(exact) != 1:
        raise RuntimeError(
            f"provider identity count={len(exact)} card={row['canonical_card_id']} "
            f"name={row['card_name']} number={row['number']} set={row['set_name']}"
        )
    return int(exact[0]["id"]), "research_exact_name_number_set"


def capture(provider: PkmnPricesClient, target: dict[str, Any], *, period: str, credit_cap: int) -> dict[str, Any]:
    start_credits = provider.credits_charged
    panels: dict[str, Any] = {}
    failures: list[dict[str, Any]] = []

    for row in target["cards"]:
        if provider.credits_charged - start_credits >= credit_cap:
            failures.append({"canonical_card_id": row["canonical_card_id"], "error": "local_credit_cap"})
            break
        try:
            provider_id, source = resolve_provider_id(provider, row)
            payload = provider.price_history_page(
                provider_id,
                period=period,
                condition="Near Mint",
                variant=row["provider_variant"],
                limit=365,
                page=1,
            )
            history = _history_rows(payload)
            panels[row["canonical_card_id"]] = {
                "card": {**row, "provider_card_id": provider_id, "identity_source": source},
                "history": history,
            }
            print(
                f"[treatment-expansion] set={row['set_name']} subject={row['subject_key']} "
                f"rarity={row['rarity']} provider={provider_id} rows={len(history)} "
                f"credits={provider.credits_charged-start_credits}",
                flush=True,
            )
        except PkmnPricesAPIError as exc:
            failures.append({"canonical_card_id": row["canonical_card_id"], "error": f"{exc}"})
            if exc.code == "credit_limit_exceeded":
                break
        except Exception as exc:
            failures.append({
                "canonical_card_id": row["canonical_card_id"],
                "error": f"{type(exc).__name__}: {exc}",
            })

    subject_results: list[dict[str, Any]] = []
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in target["cards"]:
        grouped[(row["set_name"], row["subject_key"])].append(row)

    for (set_name, subject_key), rows in sorted(grouped.items()):
        if len(rows) != 2:
            raise RuntimeError(f"target subject does not have exactly two cards: {set_name} {subject_key}")
        a, b = rows
        pa = panels.get(a["canonical_card_id"])
        pb = panels.get(b["canonical_card_id"])
        shared = 0
        if pa and pb:
            da = {item["date"] for item in pa["history"]}
            db = {item["date"] for item in pb["history"]}
            shared = len(da & db)
        status = (
            "PANEL_READY_STRONG" if shared >= STRONG_DAYS
            else "PANEL_READY_MODERATE" if shared >= MODERATE_DAYS
            else "HISTORY_BLOCKED"
        )
        subject_results.append({
            "era_name": ERA_BY_SET[set_name],
            "set_name": set_name,
            "subject_key": subject_key,
            "shared_dates": shared,
            "status": status,
            "cards": [a["canonical_card_id"], b["canonical_card_id"]],
        })

    set_results: list[dict[str, Any]] = []
    by_set: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in subject_results:
        by_set[result["set_name"]].append(result)
    for set_name, rows in sorted(by_set.items()):
        ready = [row for row in rows if row["status"] in {"PANEL_READY_STRONG", "PANEL_READY_MODERATE"}]
        set_results.append({
            "era_name": ERA_BY_SET[set_name],
            "set_name": set_name,
            "matched_identities": len(rows),
            "ready_identities": len(ready),
            "G1": len(rows) >= 2,
            "G2": len(ready) >= 2,
            "G3": len(ready) >= 2,
            "G4": len({cid for row in ready for cid in row["cards"]}) >= 4,
            "passes_G1_G4": len(ready) >= 2 and len({cid for row in ready for cid in row["cards"]}) >= 4,
        })

    era_results: list[dict[str, Any]] = []
    for era in ("Mega Evolution", "Scarlet and Violet"):
        rows = [row for row in set_results if row["era_name"] == era]
        passing = [row for row in rows if row["passes_G1_G4"]]
        era_results.append({
            "era_name": era,
            "target_sets": len(rows),
            "passing_sets": len(passing),
            "passes_era_progression": len(passing) >= 2,
        })

    cross_era = all(row["passes_era_progression"] for row in era_results)
    return {
        "status": "COMPLETE" if not failures else "PARTIAL",
        "version": VERSION,
        "period": period,
        "target_fingerprint": target["fingerprint"],
        "provider_calls": provider.successful_request_count,
        "request_attempt_count": provider.request_attempt_count,
        "credits_used": provider.credits_charged - start_credits,
        "provider_credit_limit": provider.credits_limit,
        "provider_rate_remaining": provider.rate_remaining,
        "failures": failures,
        "panels": panels,
        "subject_results": subject_results,
        "set_results": set_results,
        "era_results": era_results,
        "cross_era_progression": cross_era,
        "production_writes": 0,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--market-date", default=MARKET_DATE)
    parser.add_argument("--period", default="180d")
    parser.add_argument("--credit-cap", type=int, default=5000)
    parser.add_argument("--capture", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "backend/artifacts/treatment_panel_recovery_v2/gate_expansion.json",
    )
    args = parser.parse_args(argv)

    load_dotenv(ROOT / "backend/.env", override=False)
    from backend.db.clients.supabase_client import supabase

    target = build_targets(supabase, args.market_date)
    result: dict[str, Any] = {
        "status": "PREFLIGHT_OK",
        "target": target,
        "target_card_count": len(target["cards"]),
        "target_subject_count": 8,
        "target_set_count": 4,
        "production_writes": 0,
    }
    if args.capture:
        credentials = load_pkmnprices_credentials(allow_frontend_fallback=False)
        provider = PkmnPricesClient(
            credentials.api_key,
            min_request_interval=0.55,
            timeout=10.0,
            max_retries=0,
        )
        result = {**result, **capture(provider, target, period=args.period, credit_cap=args.credit_cap)}
        result["production_writes"] = 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    public = {k: v for k, v in result.items() if k not in {"target", "panels"}}
    print(json.dumps(public, indent=2, sort_keys=True, default=str))
    return 0 if result["status"] in {"PREFLIGHT_OK", "COMPLETE"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
