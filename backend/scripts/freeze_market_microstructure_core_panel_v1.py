"""Freeze and audit Core Panel V1 without calling a paid data provider."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from backend.db.clients.supabase_client import create_service_role_client

ROOT = Path(__file__).resolve().parents[2]
F1 = ROOT / "backend/artifacts/index_fair_value/index_fair_value_f1_dataset.json"
OUT = ROOT / "docs/research/index_fair_value/core_panel_v1_manifest.json"
F1_FINGERPRINT = "0e7b04f1119ce525fbe387b50b523ac580aa7a14c758e5d16487a334969825d9"
SEED = 20260929
PER_BAND = 30
BANDS = (
    (-math.inf, 5, "under_5"), (5, 10, "5_to_under_10"),
    (10, 25, "10_to_under_25"), (25, 50, "25_to_under_50"),
    (50, 100, "50_to_under_100"), (100, 250, "100_to_under_250"),
    (250, math.inf, "250_plus"),
)


def _fingerprint(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def _band(price: float) -> str:
    return next(label for low, high, label in BANDS if low <= price < high)


def _paged(factory: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        page = list(factory().range(start, start + 999).execute().data or [])
        rows.extend(page)
        if len(page) < 1000:
            return rows
        start += 1000


def build(db: Any) -> dict[str, Any]:
    source = json.loads(F1.read_text(encoding="utf-8"))
    actual_f1 = source["manifest"]["datasetFingerprint"]
    if actual_f1 != F1_FINGERPRINT:
        raise RuntimeError("CORE_PANEL_F1_FINGERPRINT_DRIFT")
    eligible = [dict(row) for row in source["rows"] if row.get("eligible_v1_strict")]
    variant_ids = sorted({str(row["card_variant_id"]) for row in eligible})
    external: list[dict[str, Any]] = []
    for start in range(0, len(variant_ids), 200):
        chunk = variant_ids[start:start + 200]
        external.extend(_paged(lambda chunk=chunk: db.table("card_variant_external_identities")
            .select("card_variant_id,provider,external_product_id")
            .eq("provider", "tcgplayer").in_("card_variant_id", chunk).order("card_variant_id")))
    product_sets: dict[str, set[str]] = defaultdict(set)
    for row in external:
        value = str(row.get("external_product_id") or "").strip()
        if value:
            product_sets[str(row["card_variant_id"])].add(value)
    products = {key: next(iter(values)) for key, values in product_sets.items() if len(values) == 1}

    identities = _paged(lambda: db.table("pkmnprices_card_identity_v1")
        .select("provider_card_id,canonical_card_id,tcgplayer_product_id,language")
        .eq("language", "English").order("canonical_card_id"))
    provider_by_pair = {
        (str(row["canonical_card_id"]), str(row["tcgplayer_product_id"])): int(row["provider_card_id"])
        for row in identities
    }

    candidates = []
    for row in eligible:
        variant_id = str(row["card_variant_id"])
        if variant_id not in products:
            continue
        price = float(row["target_market_price_usd"])
        candidates.append({**row, "price_band": _band(price),
                           "tcgplayer_product_id": products[variant_id],
                           "sample_key": hashlib.sha256(f"{SEED}:{row['canonical_card_id']}".encode()).hexdigest()})
    selected = []
    for _, _, label in BANDS:
        selected.extend(sorted((row for row in candidates if row["price_band"] == label),
                               key=lambda row: (row["sample_key"], row["canonical_card_id"]))[:PER_BAND])

    rows = []
    for row in selected:
        canonical_id = str(row["canonical_card_id"])
        tcg_id = str(row["tcgplayer_product_id"])
        rows.append({
            "canonical_card_id": canonical_id,
            "card_variant_id": str(row["card_variant_id"]),
            "root_set_id": str(row["root_set_id"]),
            "tcgplayer_product_id": tcg_id,
            "provider_card_id": provider_by_pair.get((canonical_id, tcg_id)),
            "set_id": str(row["set_id"]), "set_name": row["set_name"], "era": row["era"],
            "card_name": row["card_name"], "card_number": row["card_number"],
            "edition": row.get("edition"), "printing_type": row.get("printing_type"),
            "special_type": row.get("special_type"), "price_band": row["price_band"],
            "source_f1_fingerprint": F1_FINGERPRINT, "sample_seed": SEED,
        })
    rows.sort(key=lambda row: (row["price_band"], row["canonical_card_id"], row["card_variant_id"]))
    physical = [(row["canonical_card_id"], row["card_variant_id"]) for row in rows]
    editions = Counter(str(row.get("edition") or "unspecified") for row in rows)
    audit = {
        "row_count": len(rows), "by_price_band": dict(sorted(Counter(row["price_band"] for row in rows).items())),
        "by_root_set": dict(sorted(Counter(row["root_set_id"] for row in rows).items())),
        "by_era": dict(sorted(Counter(row["era"] for row in rows).items())),
        "edition_scopes": dict(sorted(editions.items())),
        "unresolved_provider_identity_count": sum(row["provider_card_id"] is None for row in rows),
        "unresolved_provider_canonical_card_ids": sorted(row["canonical_card_id"] for row in rows if row["provider_card_id"] is None),
        "duplicate_physical_identity_count": len(physical) - len(set(physical)),
    }
    contract = {
        "version": "market_microstructure_core_panel_v1", "research_only": True,
        "source_f1_fingerprint": F1_FINGERPRINT, "sample_seed": SEED,
        "per_band_target": PER_BAND, "provider_requests": 0, "provider_credits_used": 0,
        "production_pricing_authority_changed": False, "rows": rows,
    }
    contract["panel_fingerprint"] = _fingerprint(contract)
    contract["audit"] = audit
    return contract


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    manifest = build(create_service_role_client())
    rendered = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    if args.check:
        if not args.output.exists() or args.output.read_text(encoding="utf-8") != rendered:
            raise RuntimeError("CORE_PANEL_MANIFEST_DRIFT")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(json.dumps({"panel_fingerprint": manifest["panel_fingerprint"], **manifest["audit"],
                      "provider_credits_used": 0}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
