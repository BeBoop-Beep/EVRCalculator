"""Read-only Chilling Reign (swsh6) Supabase card/variant label audit.

This script inspects:
1) Public schema metadata (column names + data types) via Supabase OpenAPI.
2) Set-specific card rows and card-variant rows for Chilling Reign.
3) Distinct values and grouped counts needed to design outcome-to-pool mappings.

It never mutates the database.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import requests

# Keep script runnable from repo root and direct script execution.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from backend.db.clients.supabase_client import SUPABASE_KEY, SUPABASE_URL, supabase  # noqa: E402


TARGET_SET_ID = "swsh6"
TARGET_SET_NAME = "Chilling Reign"

CONFIG_BUCKETS = (
    "full art v",
    "full art trainer",
    "alternate art v",
    "alternate art vmax",
    "rainbow trainer",
    "rainbow vmax",
    "gold secret rare",
)


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    return str(value)


def _counter_to_sorted_dict(counter: Counter) -> Dict[str, int]:
    return {k: int(v) for k, v in sorted(counter.items(), key=lambda item: (-item[1], item[0]))}


def _chunked(values: List[Any], size: int) -> Iterable[List[Any]]:
    for idx in range(0, len(values), size):
        yield values[idx : idx + size]


def _fetch_openapi_document() -> Dict[str, Any]:
    url = SUPABASE_URL.rstrip("/") + "/rest/v1/"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Accept": "application/openapi+json",
    }
    response = requests.get(url, headers=headers, timeout=45)
    response.raise_for_status()
    return response.json()


def _extract_table_schema(openapi_doc: Dict[str, Any], table_name: str) -> Dict[str, Any]:
    definitions = openapi_doc.get("definitions") or {}
    definition = definitions.get(table_name) or {}
    properties = definition.get("properties") or {}
    required = set(definition.get("required") or [])

    columns = []
    for column_name, spec in properties.items():
        column_info = {
            "column_name": column_name,
            "openapi_type": spec.get("type"),
            "openapi_format": spec.get("format"),
            "nullable": column_name not in required,
        }
        if "enum" in spec:
            column_info["enum_values"] = spec.get("enum")
        columns.append(column_info)

    return {
        "table": table_name,
        "column_count": len(columns),
        "columns": sorted(columns, key=lambda row: row["column_name"]),
    }


def _resolve_chilling_reign_set_row() -> Dict[str, Any]:
    by_api_id = (
        supabase.table("sets")
        .select("*")
        .eq("pokemon_api_set_id", TARGET_SET_ID)
        .limit(5)
        .execute()
    )
    rows = by_api_id.data or []
    if rows:
        return rows[0]

    by_name = (
        supabase.table("sets")
        .select("*")
        .ilike("name", TARGET_SET_NAME)
        .limit(5)
        .execute()
    )
    rows = by_name.data or []
    if rows:
        return rows[0]

    raise RuntimeError("Could not resolve Chilling Reign set row by pokemon_api_set_id or set name")


def _fetch_cards_for_set(set_pk: Any) -> List[Dict[str, Any]]:
    result = supabase.table("cards").select("*").eq("set_id", set_pk).execute()
    return result.data or []


def _fetch_card_variants_for_cards(card_ids: List[Any]) -> List[Dict[str, Any]]:
    if not card_ids:
        return []

    rows: List[Dict[str, Any]] = []
    for chunk in _chunked(card_ids, 250):
        result = supabase.table("card_variants").select("*").in_("card_id", chunk).execute()
        rows.extend(result.data or [])
    return rows


def _fetch_latest_market_rows_for_variants(variant_ids: List[Any]) -> List[Dict[str, Any]]:
    if not variant_ids:
        return []

    rows: List[Dict[str, Any]] = []
    for chunk in _chunked(variant_ids, 250):
        result = (
            supabase.table("card_market_usd_latest_by_condition")
            .select("*")
            .in_("variant_id", chunk)
            .execute()
        )
        rows.extend(result.data or [])
    return rows


def _fetch_price_observations_for_variants(variant_ids: List[Any]) -> List[Dict[str, Any]]:
    if not variant_ids:
        return []

    rows: List[Dict[str, Any]] = []
    for chunk in _chunked(variant_ids, 250):
        result = (
            supabase.table("card_variant_price_observations")
            .select("card_variant_id,condition_id,currency,source,captured_at,market_price,low_price,high_price")
            .in_("card_variant_id", chunk)
            .execute()
        )
        rows.extend(result.data or [])
    return rows


def _subtypes_as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except Exception:
            pass
    return [part.strip() for part in text.split(",") if part.strip()]


def _derive_rare_slot_candidate_labels(card: Dict[str, Any], variant: Dict[str, Any]) -> List[str]:
    labels: List[str] = []

    rarity = _normalize_text(card.get("rarity"))
    card_name = str(card.get("name") or "")
    card_name_l = _normalize_text(card_name)
    printing = _normalize_text(variant.get("printing_type"))
    special = _normalize_text(variant.get("special_type"))
    subtypes = [_normalize_text(item) for item in _subtypes_as_list(card.get("subtypes"))]

    if rarity == "rare":
        labels.append("regular rare")
    if "holo" in rarity and "rare" in rarity:
        labels.append("holo rare")

    has_v = "v" in subtypes or card_name_l.endswith(" v") or " v " in f" {card_name_l} "
    has_vmax = "vmax" in subtypes or "vmax" in card_name_l
    is_trainer = "trainer" in subtypes or _normalize_text(card.get("supertype")) == "trainer"
    is_full_art = "full art" in rarity or "ultra rare" in rarity
    is_secret = "secret" in rarity
    is_rainbow = "rainbow" in special or "rainbow" in printing or "rainbow" in card_name_l
    is_gold = "gold" in special or "gold" in printing or "gold" in card_name_l
    is_alt = "alt" in special or "alternate" in special or "alt" in card_name_l

    if has_v and not has_vmax and not is_full_art and not is_alt:
        labels.append("regular pokemon v")
    if has_vmax and not is_full_art and not is_alt and not is_rainbow:
        labels.append("regular vmax")

    if is_full_art and has_v and not has_vmax and not is_alt:
        labels.append("full art v")
    if is_full_art and is_trainer and not is_rainbow:
        labels.append("full art trainer")
    if is_alt and has_v and not has_vmax:
        labels.append("alternate art v")
    if is_alt and has_vmax:
        labels.append("alternate art vmax")
    if is_rainbow and is_trainer:
        labels.append("rainbow trainer")
    if is_rainbow and has_vmax:
        labels.append("rainbow vmax")
    if is_gold or is_secret:
        labels.append("gold/secret rare")

    return sorted(set(labels))


def _bucket_match(config_bucket: str, card: Dict[str, Any], variant: Dict[str, Any]) -> bool:
    labels = _derive_rare_slot_candidate_labels(card, variant)
    normalized_labels = {label.replace("/", " ") for label in labels}
    target = config_bucket.replace("/", " ")

    if target in normalized_labels:
        return True

    # Accept project naming differences between "gold secret rare" and "gold/secret rare".
    if target == "gold secret rare" and "gold secret rare" in normalized_labels:
        return True

    return False


def run_audit(output_path: Path | None) -> Dict[str, Any]:
    openapi_doc = _fetch_openapi_document()
    set_row = _resolve_chilling_reign_set_row()

    set_pk = set_row.get("id")
    cards = _fetch_cards_for_set(set_pk)
    card_ids = [row.get("id") for row in cards if row.get("id") is not None]

    variants = _fetch_card_variants_for_cards(card_ids)
    variant_ids = [row.get("id") for row in variants if row.get("id") is not None]

    latest_market_rows = _fetch_latest_market_rows_for_variants(variant_ids)
    price_observation_rows = _fetch_price_observations_for_variants(variant_ids)

    cards_by_id = {row.get("id"): row for row in cards}

    rarity_counter: Counter = Counter()
    supertype_counter: Counter = Counter()
    subtype_token_counter: Counter = Counter()
    subtype_combo_counter: Counter = Counter()
    rarity_subtype_combo_counter: Counter = Counter()
    card_number_presence_counter: Counter = Counter()
    set_name_counter: Counter = Counter()

    for card in cards:
        rarity = str(card.get("rarity") or "<NULL>")
        rarity_counter[rarity] += 1
        supertype = str(card.get("supertype") or "<NULL>")
        supertype_counter[supertype] += 1
        set_name_counter[str(card.get("set_name") or "<NULL>")] += 1

        subtypes = _subtypes_as_list(card.get("subtypes"))
        subtype_combo = " | ".join(subtypes) if subtypes else "<NONE>"
        subtype_combo_counter[subtype_combo] += 1
        rarity_subtype_combo_counter[f"{rarity} || {subtype_combo}"] += 1
        for subtype in subtypes:
            subtype_token_counter[subtype] += 1

        card_number_presence_counter["present" if card.get("card_number") not in (None, "") else "missing"] += 1

    variant_printing_counter: Counter = Counter()
    variant_special_counter: Counter = Counter()
    variant_edition_counter: Counter = Counter()
    variant_finish_counter: Counter = Counter()
    rarity_variant_counter: Counter = Counter()
    reverse_representation_counter: Counter = Counter()
    candidate_label_counter: Counter = Counter()
    candidate_label_examples: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for variant in variants:
        printing = str(variant.get("printing_type") or "<NULL>")
        special = str(variant.get("special_type") or "<NULL>")
        edition = str(variant.get("edition") or "<NULL>")
        finish = f"{printing} | {special}"

        variant_printing_counter[printing] += 1
        variant_special_counter[special] += 1
        variant_edition_counter[edition] += 1
        variant_finish_counter[finish] += 1

        card = cards_by_id.get(variant.get("card_id"), {})
        rarity = str(card.get("rarity") or "<NULL>")
        rarity_variant_counter[f"{rarity} || {finish}"] += 1

        printing_l = _normalize_text(printing)
        if "reverse" in printing_l:
            reverse_representation_counter[printing] += 1

        labels = _derive_rare_slot_candidate_labels(card, variant)
        if labels:
            for label in labels:
                candidate_label_counter[label] += 1
                if len(candidate_label_examples[label]) < 5:
                    candidate_label_examples[label].append(
                        {
                            "card_name": card.get("name"),
                            "card_number": card.get("card_number"),
                            "rarity": card.get("rarity"),
                            "subtypes": card.get("subtypes"),
                            "printing_type": variant.get("printing_type"),
                            "special_type": variant.get("special_type"),
                            "edition": variant.get("edition"),
                        }
                    )

    db_labels_for_bucket: Dict[str, List[str]] = {}
    for bucket in CONFIG_BUCKETS:
        matched_labels: Counter = Counter()
        for variant in variants:
            card = cards_by_id.get(variant.get("card_id"), {})
            if _bucket_match(bucket, card, variant):
                label_components = [
                    f"rarity={card.get('rarity')}",
                    f"subtypes={card.get('subtypes')}",
                    f"printing_type={variant.get('printing_type')}",
                    f"special_type={variant.get('special_type')}",
                ]
                matched_labels["; ".join(label_components)] += 1
        db_labels_for_bucket[bucket] = [
            f"{label} (count={count})"
            for label, count in sorted(matched_labels.items(), key=lambda item: (-item[1], item[0]))
        ]

    unmatched_config_buckets = [bucket for bucket, labels in db_labels_for_bucket.items() if not labels]

    latest_market_fields = sorted({key for row in latest_market_rows for key in row.keys()})
    price_observation_fields = sorted({key for row in price_observation_rows for key in row.keys()})

    report = {
        "meta": {
            "read_only": True,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "target_set_id": TARGET_SET_ID,
            "target_set_name": TARGET_SET_NAME,
            "cwd": os.getcwd(),
        },
        "resolved_set_row": _to_jsonable(set_row),
        "schema_audit": {
            "source": "supabase_openapi",
            "tables": {
                "cards": _extract_table_schema(openapi_doc, "cards"),
                "card_variants": _extract_table_schema(openapi_doc, "card_variants"),
                "card_variant_price_observations": _extract_table_schema(openapi_doc, "card_variant_price_observations"),
                "card_market_usd_latest_by_condition": _extract_table_schema(openapi_doc, "card_market_usd_latest_by_condition"),
                "simulation_input_cards": _extract_table_schema(openapi_doc, "simulation_input_cards"),
                "simulation_input_cards_with_near_mint_price": _extract_table_schema(
                    openapi_doc,
                    "simulation_input_cards_with_near_mint_price",
                ),
            },
        },
        "counts": {
            "card_rows": len(cards),
            "variant_rows": len(variants),
            "latest_market_rows": len(latest_market_rows),
            "price_observation_rows": len(price_observation_rows),
        },
        "card_level_observed_fields": sorted({key for row in cards for key in row.keys()}),
        "variant_level_observed_fields": sorted({key for row in variants for key in row.keys()}),
        "latest_market_observed_fields": latest_market_fields,
        "price_observation_observed_fields": price_observation_fields,
        "card_level_distinct_values": {
            "rarity_counts": _counter_to_sorted_dict(rarity_counter),
            "supertype_counts": _counter_to_sorted_dict(supertype_counter),
            "subtype_token_counts": _counter_to_sorted_dict(subtype_token_counter),
            "subtype_combo_counts": _counter_to_sorted_dict(subtype_combo_counter),
            "rarity_x_subtype_combo_counts": _counter_to_sorted_dict(rarity_subtype_combo_counter),
            "set_name_counts": _counter_to_sorted_dict(set_name_counter),
            "card_number_presence": _counter_to_sorted_dict(card_number_presence_counter),
        },
        "variant_level_distinct_values": {
            "printing_type_counts": _counter_to_sorted_dict(variant_printing_counter),
            "special_type_counts": _counter_to_sorted_dict(variant_special_counter),
            "edition_counts": _counter_to_sorted_dict(variant_edition_counter),
            "finish_counts": _counter_to_sorted_dict(variant_finish_counter),
            "rarity_x_variant_finish_counts": _counter_to_sorted_dict(rarity_variant_counter),
            "reverse_representation_counts": _counter_to_sorted_dict(reverse_representation_counter),
        },
        "rare_slot_candidate_audit": {
            "candidate_label_counts": _counter_to_sorted_dict(candidate_label_counter),
            "candidate_label_examples": _to_jsonable(candidate_label_examples),
        },
        "config_bucket_comparison": {
            "config_buckets": list(CONFIG_BUCKETS),
            "bucket_to_observed_db_label_shapes": db_labels_for_bucket,
            "unmatched_config_buckets": unmatched_config_buckets,
            "requires_outcome_pool_mapping": bool(unmatched_config_buckets),
            "notes": (
                "Config buckets are normalized labels while DB rows carry multi-field traits. "
                "A config-controlled outcome-to-pool mapping is required when any bucket has no "
                "direct one-to-one DB label match."
            ),
        },
    }

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only Supabase label audit for Chilling Reign (swsh6)")
    parser.add_argument(
        "--output",
        type=str,
        default="logs/audits/chilling_reign_supabase_label_audit_swsh6.json",
        help="Optional JSON output path (default: logs/audits/chilling_reign_supabase_label_audit_swsh6.json)",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print compact JSON summary to stdout",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    output_path = Path(args.output) if args.output else None
    report = run_audit(output_path)

    summary = {
        "set": {
            "id": report["resolved_set_row"].get("id"),
            "name": report["resolved_set_row"].get("name"),
            "pokemon_api_set_id": report["resolved_set_row"].get("pokemon_api_set_id"),
        },
        "counts": report["counts"],
        "rarity_counts": report["card_level_distinct_values"]["rarity_counts"],
        "printing_type_counts": report["variant_level_distinct_values"]["printing_type_counts"],
        "special_type_counts": report["variant_level_distinct_values"]["special_type_counts"],
        "reverse_representation_counts": report["variant_level_distinct_values"]["reverse_representation_counts"],
        "rare_slot_candidate_label_counts": report["rare_slot_candidate_audit"]["candidate_label_counts"],
        "unmatched_config_buckets": report["config_bucket_comparison"]["unmatched_config_buckets"],
        "requires_outcome_pool_mapping": report["config_bucket_comparison"]["requires_outcome_pool_mapping"],
    }

    print(f"[audit] target_set={TARGET_SET_ID} ({TARGET_SET_NAME})")
    print(f"[audit] card_rows={summary['counts']['card_rows']} variant_rows={summary['counts']['variant_rows']}")
    print(f"[audit] wrote_json={output_path.as_posix() if output_path else '<none>'}")
    if args.stdout:
        print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
