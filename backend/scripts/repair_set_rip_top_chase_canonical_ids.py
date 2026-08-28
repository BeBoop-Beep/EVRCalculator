"""Repair current Set RIP Top Chase canonical IDs without rerunning simulations.

Dry-run is the default. Pass --apply only after reviewing the complete audit.
"""
from __future__ import annotations

import argparse
import copy

from backend.db.clients.supabase_client import create_service_role_client


def _one(rows, label):
    if len(rows) != 1:
        raise RuntimeError(f"{label}: expected one row, found {len(rows)}")
    return rows[0]


def resolve_canonical_id(client, legacy_card_id):
    legacy = _one(
        client.table("cards").select("id,set_id,pokemon_tcg_api_id").eq("id", legacy_card_id).limit(2).execute().data or [],
        f"legacy card {legacy_card_id}",
    )
    set_id, api_id = legacy.get("set_id"), legacy.get("pokemon_tcg_api_id")
    if not set_id or not api_id:
        raise RuntimeError(f"legacy card {legacy_card_id}: missing set/API identity")
    canonical = _one(
        client.table("pokemon_canonical_cards").select("id,set_id,pokemon_tcg_api_card_id")
        .eq("set_id", set_id).eq("pokemon_tcg_api_card_id", api_id).limit(2).execute().data or [],
        f"canonical card {set_id}/{api_id}",
    )
    return canonical["id"], set_id, api_id


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    client = create_service_role_client()
    rows = client.table("pokemon_set_page_snapshot_latest").select("set_id,rip_bootstrap_json").execute().data or []
    audit = []
    for row in rows:
        bootstrap = row.get("rip_bootstrap_json") or {}
        chase = ((bootstrap.get("ripDecision") or {}).get("topChase") or {})
        legacy_id = chase.get("cardId")
        if not legacy_id:
            continue
        canonical_id, mapped_set_id, api_id = resolve_canonical_id(client, legacy_id)
        if str(mapped_set_id) != str(row.get("set_id")):
            raise RuntimeError(f"{row.get('set_id')}: mapped card belongs to {mapped_set_id}")
        audit.append((row, legacy_id, canonical_id, api_id))

    for row, legacy_id, canonical_id, api_id in audit:
        print(row["set_id"], legacy_id, api_id, "->", canonical_id)
    print(f"mapped={len(audit)} apply={args.apply}")
    if not args.apply:
        return
    for row, _legacy_id, canonical_id, _api_id in audit:
        current = _one(
            client.table("pokemon_set_page_snapshot_latest").select("payload_json,rip_bootstrap_json")
            .eq("set_id", row["set_id"]).limit(1).execute().data or [],
            f"snapshot {row['set_id']}",
        )
        payload, bootstrap = copy.deepcopy(current["payload_json"]), copy.deepcopy(current["rip_bootstrap_json"])
        payload_chase = payload["ripDecision"]["topChase"]
        bootstrap_chase = bootstrap["ripDecision"]["topChase"]
        if payload_chase.get("cardId") != bootstrap_chase.get("cardId") or payload_chase.get("cardVariantId") != bootstrap_chase.get("cardVariantId"):
            raise RuntimeError(f"{row.get('set_id')}: payload/bootstrap Top Chase mismatch")
        payload["ripDecision"]["topChase"]["canonicalCardId"] = canonical_id
        bootstrap["ripDecision"]["topChase"]["canonicalCardId"] = canonical_id
        client.table("pokemon_set_page_snapshot_latest").update({
            "payload_json": payload,
            "rip_bootstrap_json": bootstrap,
        }).eq("set_id", row["set_id"]).execute()
    print(f"updated={len(audit)}")


if __name__ == "__main__":
    main()
