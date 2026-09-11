"""Persistent Phase-3 Market Explorer filter-options snapshot contract."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from typing import Any

TCG = "pokemon"
CONTRACT_KEY = "marketExplorerFilterOptions"
SCHEMA_VERSION = "market-explorer-filter-options-v1"
READ_RPC = "get_pokemon_market_explorer_options_snapshot_v1"
PUBLISH_RPC = "publish_pokemon_market_explorer_options_snapshot_v1"
REQUIRED_SECTIONS = (
    "eras", "sets", "cardRarities", "cardSegments", "pokemon",
    "sealedProductFamilies", "priceSegments", "releaseAgeCohorts", "compatibility",
)


class MarketExplorerOptionsUnavailable(RuntimeError):
    """No valid prepublished options payload is currently available."""


def validate_options_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Market Explorer options payload must be an object")
    missing = [key for key in REQUIRED_SECTIONS if key not in payload]
    if missing:
        raise ValueError(f"Market Explorer options payload is missing: {', '.join(missing)}")
    compatibility = payload.get("compatibility")
    if not isinstance(compatibility, dict) or "cardRaritySetIds" not in compatibility:
        raise ValueError("Market Explorer options require compatibility.cardRaritySetIds")
    return payload


def read_market_explorer_options_snapshot(client: Any) -> dict[str, Any]:
    rows = list((client.rpc(READ_RPC, {
        "p_tcg": TCG, "p_contract_key": CONTRACT_KEY,
    }).execute()).data or [])
    if not rows:
        raise MarketExplorerOptionsUnavailable("Canonical Market Explorer filters are refreshing")
    row = dict(rows[0])
    payload = validate_options_payload(row.get("payload_json"))
    return {**payload, "snapshot": {
        "id": row.get("snapshot_id"), "schemaVersion": row.get("schema_version"),
        "generatedAt": row.get("generated_at"), "sourceAsOf": row.get("source_as_of"),
        "sourceFingerprint": row.get("source_fingerprint"), "payloadBytes": row.get("payload_bytes"),
        "publishedAt": row.get("published_at"), "sourceMetadata": row.get("source_metadata") or {},
    }}


def publish_market_explorer_options_snapshot(client: Any, payload: dict[str, Any], *,
                                             source_as_of: str | None = None) -> dict[str, Any]:
    canonical = validate_options_payload(dict(payload))
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    fingerprint = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    taxonomy_version = (canonical.get("cardRarities") or {}).get("taxonomyVersion")
    try:
        current = read_market_explorer_options_snapshot(client)
    except MarketExplorerOptionsUnavailable:
        current = None
    if (current and current.get("snapshot", {}).get("sourceFingerprint") == fingerprint
            and (current.get("snapshot", {}).get("sourceMetadata") or {}).get(
                "filterTaxonomyVersion") == taxonomy_version):
        return {"published": False, "reason": "unchanged", **current["snapshot"]}
    generated_at = datetime.now(timezone.utc).isoformat()
    as_of = source_as_of or date.today().isoformat()
    result = list((client.rpc(PUBLISH_RPC, {
        "p_tcg": TCG, "p_contract_key": CONTRACT_KEY, "p_schema_version": SCHEMA_VERSION,
        "p_generated_at": generated_at, "p_source_as_of": as_of, "p_payload_json": canonical,
        "p_source_metadata": {"authority": "pokemon_market_explorer_card_current_metadata",
                              "filterTaxonomyVersion": taxonomy_version},
        "p_source_fingerprint": fingerprint,
    }).execute()).data or [])
    if not result:
        raise RuntimeError("Options snapshot publisher returned no receipt")
    return {"published": True, "sourceFingerprint": fingerprint, "generatedAt": generated_at,
            "sourceAsOf": as_of, **dict(result[0])}
