from __future__ import annotations

import importlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from backend.db.repositories.eras_repository import (
    get_eras_by_tcg_id,
    insert_era,
    update_era_by_id,
)
from backend.db.repositories.sets_repository import (
    get_sets_by_tcg_id,
    insert_set,
    insert_sets,
    update_set_by_id,
)
from backend.db.repositories.tcgs_repository import get_tcg_by_name


logger = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).resolve().parents[2]
POKEMON_CONSTANTS_ROOT = BACKEND_ROOT / "constants" / "tcg" / "pokemon"
DEFAULT_BOOTSTRAP_REPORT_PATH = POKEMON_CONSTANTS_ROOT / "pokemon_set_bootstrap_report.json"
DEFAULT_SYNC_REPORT_PATH = POKEMON_CONSTANTS_ROOT / "pokemon_era_set_sync_report.json"
TCG_NAME_CANDIDATES = ("Pokemon", "Pokémon")


def _clean_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_release_date(value: Any) -> Optional[str]:
    raw = _clean_str(value)
    if not raw:
        return None

    normalized = raw.replace("/", "-")
    try:
        return datetime.strptime(normalized, "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None


def _coalesce_value(source: Any, existing: Any) -> Any:
    if isinstance(source, str):
        source = source.strip() or None
    if source is None:
        return existing
    return source


def _drop_none_values(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if value is not None or isinstance(value, bool)
    }


def _load_era_sort_order() -> Dict[str, int]:
    if not DEFAULT_BOOTSTRAP_REPORT_PATH.exists():
        return {}

    try:
        payload = json.loads(DEFAULT_BOOTSTRAP_REPORT_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("pokemon_era_set_sync: failed to parse bootstrap report %s", DEFAULT_BOOTSTRAP_REPORT_PATH)
        return {}

    era_inventory = payload.get("era_inventory") or []
    sort_map: Dict[str, int] = {}
    for index, row in enumerate(era_inventory, start=1):
        era_folder = _clean_str(row.get("era_folder"))
        if era_folder and era_folder not in sort_map:
            sort_map[era_folder] = index
    return sort_map


def discover_pokemon_era_and_set_metadata() -> Dict[str, List[Dict[str, Any]]]:
    sort_order_map = _load_era_sort_order()
    era_dirs = [
        path
        for path in POKEMON_CONSTANTS_ROOT.iterdir()
        if path.is_dir() and path.name != "__pycache__"
    ]

    def sort_key(path: Path) -> Tuple[int, str]:
        return (sort_order_map.get(path.name, 10_000), path.name.lower())

    eras: List[Dict[str, Any]] = []
    sets: List[Dict[str, Any]] = []

    for position, era_dir in enumerate(sorted(era_dirs, key=sort_key), start=1):
        set_map_module = importlib.import_module(
            f"backend.constants.tcg.pokemon.{era_dir.name}.setMap"
        )
        set_config_map = getattr(set_map_module, "SET_CONFIG_MAP", {})

        era_name: Optional[str] = None
        earliest_release_date: Optional[str] = None

        for canonical_key, config_cls in set_config_map.items():
            set_name = _clean_str(getattr(config_cls, "SET_NAME", None))
            release_date = _parse_release_date(getattr(config_cls, "RELEASE_DATE", None))
            abbreviation = _clean_str(getattr(config_cls, "SET_ABBREVIATION", None))
            pokemon_api_set_id = _clean_str(getattr(config_cls, "SET_ID", None))
            symbol_image_url = _clean_str(getattr(config_cls, "SYMBOL_IMAGE_URL", None))
            logo_image_url = _clean_str(getattr(config_cls, "LOGO_IMAGE_URL", None))
            card_details_url = _clean_str(getattr(config_cls, "CARD_DETAILS_URL", None))
            sealed_details_url = _clean_str(getattr(config_cls, "SEALED_DETAILS_URL", None))
            source_config_path = (
                Path("backend")
                / "constants"
                / "tcg"
                / "pokemon"
                / era_dir.name
                / f"{canonical_key}.py"
            ).as_posix()

            era_name = era_name or _clean_str(getattr(config_cls, "ERA", None))
            if release_date and (earliest_release_date is None or release_date < earliest_release_date):
                earliest_release_date = release_date

            sets.append(
                {
                    "canonical_key": canonical_key,
                    "era_canonical_key": era_dir.name,
                    "era_name": era_name,
                    "name": set_name,
                    "release_date": release_date,
                    "set_type": None,
                    "abbreviation": abbreviation,
                    "set_code": None,
                    "pokemon_api_set_id": pokemon_api_set_id,
                    "symbol_image_url": symbol_image_url,
                    "logo_image_url": logo_image_url,
                    "source_config_path": source_config_path,
                    "card_details_url": card_details_url,
                    "sealed_details_url": sealed_details_url,
                    "has_card_details_url": bool(card_details_url),
                    "has_sealed_details_url": bool(sealed_details_url),
                    "ready_for_daily_scrape": bool(card_details_url or sealed_details_url),
                }
            )

        eras.append(
            {
                "canonical_key": era_dir.name,
                "name": era_name or era_dir.name,
                "release_date": earliest_release_date,
                "sort_order": sort_order_map.get(era_dir.name, position),
                "is_active": True,
            }
        )

    return {"eras": eras, "sets": sets}


def _resolve_tcg_row() -> Dict[str, Any]:
    for candidate in TCG_NAME_CANDIDATES:
        tcg_row = get_tcg_by_name(candidate)
        if tcg_row:
            return tcg_row
    raise RuntimeError(
        f"Could not resolve Pokémon tcg_id from tcgs table using candidates {TCG_NAME_CANDIDATES}"
    )


def _map_rows_by(rows: Iterable[Dict[str, Any]], field_name: str) -> Dict[str, Dict[str, Any]]:
    mapped: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        value = _clean_str(row.get(field_name))
        if value and value not in mapped:
            mapped[value] = row
    return mapped


def _resolve_existing_row(
    by_canonical_key: Dict[str, Dict[str, Any]],
    by_name: Dict[str, Dict[str, Any]],
    canonical_key: Optional[str],
    name: Optional[str],
    entity_type: str,
    conflicts: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    canonical_match = by_canonical_key.get(canonical_key) if canonical_key else None
    name_match = by_name.get(name) if name else None

    if canonical_match and name_match and canonical_match.get("id") != name_match.get("id"):
        conflicts.append(
            {
                "entity_type": entity_type,
                "canonical_key": canonical_key,
                "name": name,
                "canonical_match_id": canonical_match.get("id"),
                "name_match_id": name_match.get("id"),
                "message": "Canonical key and name matched different existing rows.",
            }
        )
        return canonical_match

    return canonical_match or name_match


def _build_era_payload(source: Dict[str, Any], tcg_id: str, existing: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    payload = {
        "tcg_id": tcg_id,
        "name": source["name"],
        "release_date": _coalesce_value(source.get("release_date"), existing.get("release_date") if existing else None),
        "canonical_key": source["canonical_key"],
        "sort_order": source["sort_order"],
        "is_active": source["is_active"],
    }
    return _drop_none_values(payload)


def _build_set_payload(
    source: Dict[str, Any],
    tcg_id: str,
    era_id: str,
    existing: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    merged_card_details_url = _coalesce_value(
        source.get("card_details_url"),
        existing.get("card_details_url") if existing else None,
    )
    merged_sealed_details_url = _coalesce_value(
        source.get("sealed_details_url"),
        existing.get("sealed_details_url") if existing else None,
    )

    payload = {
        "tcg_id": tcg_id,
        "era_id": era_id,
        "name": source["name"],
        "release_date": _coalesce_value(source.get("release_date"), existing.get("release_date") if existing else None),
        "set_type": _coalesce_value(source.get("set_type"), existing.get("set_type") if existing else None),
        "abbreviation": _coalesce_value(source.get("abbreviation"), existing.get("abbreviation") if existing else None),
        "set_code": _coalesce_value(source.get("set_code"), existing.get("set_code") if existing else None),
        "canonical_key": source["canonical_key"],
        "symbol_image_url": _coalesce_value(source.get("symbol_image_url"), existing.get("symbol_image_url") if existing else None),
        "logo_image_url": _coalesce_value(source.get("logo_image_url"), existing.get("logo_image_url") if existing else None),
        "pokemon_api_set_id": _coalesce_value(source.get("pokemon_api_set_id"), existing.get("pokemon_api_set_id") if existing else None),
        "source_config_path": source.get("source_config_path"),
        "has_card_details_url": bool(merged_card_details_url),
        "has_sealed_details_url": bool(merged_sealed_details_url),
        "ready_for_daily_scrape": bool(merged_card_details_url or merged_sealed_details_url),
        "card_details_url": merged_card_details_url,
        "sealed_details_url": merged_sealed_details_url,
    }
    return _drop_none_values(payload)


def _diff_payload(existing: Optional[Dict[str, Any]], desired: Dict[str, Any]) -> Dict[str, Any]:
    if not existing:
        return desired

    changed: Dict[str, Any] = {}
    for key, value in desired.items():
        if existing.get(key) != value:
            changed[key] = value
    return changed


def _summarize_missing_metadata(set_rows: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    rows = list(set_rows)
    return {
        "missing_release_date": sum(1 for row in rows if not row.get("release_date")),
        "missing_abbreviation": sum(1 for row in rows if not row.get("abbreviation")),
        "missing_set_type": sum(1 for row in rows if not row.get("set_type")),
        "missing_set_code": sum(1 for row in rows if not row.get("set_code")),
        "missing_pokemon_api_set_id": sum(1 for row in rows if not row.get("pokemon_api_set_id")),
        "missing_symbol_image_url": sum(1 for row in rows if not row.get("symbol_image_url")),
        "missing_logo_image_url": sum(1 for row in rows if not row.get("logo_image_url")),
        "missing_card_details_url": sum(1 for row in rows if not row.get("card_details_url")),
        "missing_sealed_details_url": sum(1 for row in rows if not row.get("sealed_details_url")),
    }


def _detect_duplicate_keys(rows: Iterable[Dict[str, Any]], field_name: str) -> List[Dict[str, Any]]:
    buckets: Dict[str, List[str]] = {}
    for row in rows:
        key = _clean_str(row.get(field_name))
        row_id = _clean_str(row.get("id")) or "<unknown>"
        if not key:
            continue
        buckets.setdefault(key, []).append(row_id)

    return [
        {"field": field_name, "value": key, "row_ids": row_ids}
        for key, row_ids in buckets.items()
        if len(row_ids) > 1
    ]


def sync_pokemon_era_and_set_metadata(
    apply_changes: bool = False,
    report_path: Optional[Path] = None,
) -> Dict[str, Any]:
    discovered = discover_pokemon_era_and_set_metadata()
    source_eras = discovered["eras"]
    source_sets = discovered["sets"]
    now_iso = datetime.now(timezone.utc).isoformat()
    tcg_row = _resolve_tcg_row()
    tcg_id = tcg_row["id"]

    existing_eras = get_eras_by_tcg_id(tcg_id)
    existing_sets = get_sets_by_tcg_id(tcg_id)
    era_by_canonical = _map_rows_by(existing_eras, "canonical_key")
    era_by_name = _map_rows_by(existing_eras, "name")
    set_by_canonical = _map_rows_by(existing_sets, "canonical_key")
    set_by_name = _map_rows_by(existing_sets, "name")

    conflicts: List[Dict[str, Any]] = []
    era_actions: List[Dict[str, Any]] = []
    set_actions: List[Dict[str, Any]] = []
    synced_era_id_by_canonical: Dict[str, str] = {}
    pending_set_inserts: List[Dict[str, Any]] = []

    for source_era in source_eras:
        existing = _resolve_existing_row(
            era_by_canonical,
            era_by_name,
            source_era.get("canonical_key"),
            source_era.get("name"),
            "era",
            conflicts,
        )
        desired = _build_era_payload(source_era, tcg_id, existing)
        changes = _diff_payload(existing, desired)

        action = "skipped"
        row_id = existing.get("id") if existing else None

        if existing is None:
            action = "inserted"
            insert_payload = dict(desired)
            insert_payload["updated_at"] = now_iso
            if apply_changes:
                inserted_rows = insert_era(insert_payload) or []
                if inserted_rows and isinstance(inserted_rows[0], dict):
                    row_id = inserted_rows[0].get("id")
                    existing = inserted_rows[0]
        elif changes:
            action = "updated"
            update_payload = dict(changes)
            update_payload["updated_at"] = now_iso
            if apply_changes:
                updated_rows = update_era_by_id(existing["id"], update_payload) or []
                if updated_rows and isinstance(updated_rows[0], dict):
                    existing = updated_rows[0]

        if existing:
            row_id = existing.get("id")
        if row_id:
            synced_era_id_by_canonical[source_era["canonical_key"]] = row_id

        era_actions.append(
            {
                "canonical_key": source_era["canonical_key"],
                "name": source_era["name"],
                "action": action,
                "row_id": row_id,
                "changes": sorted(changes.keys()),
            }
        )

        if existing and row_id and source_era["canonical_key"] not in synced_era_id_by_canonical:
            synced_era_id_by_canonical[source_era["canonical_key"]] = row_id

    if apply_changes:
        refreshed_eras = get_eras_by_tcg_id(tcg_id)
        synced_era_id_by_canonical = {
            row.get("canonical_key"): row.get("id")
            for row in refreshed_eras
            if row.get("canonical_key") and row.get("id")
        }

    for source_set in source_sets:
        era_id = synced_era_id_by_canonical.get(source_set["era_canonical_key"])
        if not era_id:
            conflicts.append(
                {
                    "entity_type": "set",
                    "canonical_key": source_set.get("canonical_key"),
                    "name": source_set.get("name"),
                    "message": f"Missing era_id for era canonical key {source_set['era_canonical_key']}",
                }
            )
            set_actions.append(
                {
                    "canonical_key": source_set["canonical_key"],
                    "name": source_set["name"],
                    "action": "skipped",
                    "row_id": None,
                    "changes": [],
                    "reason": "missing_era_id",
                }
            )
            continue

        existing = _resolve_existing_row(
            set_by_canonical,
            set_by_name,
            source_set.get("canonical_key"),
            source_set.get("name"),
            "set",
            conflicts,
        )
        desired = _build_set_payload(source_set, tcg_id, era_id, existing)
        changes = _diff_payload(existing, desired)

        action = "skipped"
        row_id = existing.get("id") if existing else None

        if existing is None:
            action = "inserted"
            insert_payload = dict(desired)
            insert_payload["updated_at"] = now_iso
            if apply_changes:
                pending_set_inserts.append(insert_payload)
        elif changes:
            action = "updated"
            update_payload = dict(changes)
            update_payload["updated_at"] = now_iso
            if apply_changes:
                update_set_by_id(existing["id"], update_payload)

        set_actions.append(
            {
                "canonical_key": source_set["canonical_key"],
                "name": source_set["name"],
                "action": action,
                "row_id": row_id,
                "changes": sorted(changes.keys()),
                "reason": None,
            }
        )

    if apply_changes and pending_set_inserts:
        batch_size = 50
        for start in range(0, len(pending_set_inserts), batch_size):
            insert_sets(pending_set_inserts[start:start + batch_size])

    final_eras = get_eras_by_tcg_id(tcg_id) if apply_changes else existing_eras
    final_sets = get_sets_by_tcg_id(tcg_id) if apply_changes else existing_sets
    final_era_by_canonical = _map_rows_by(final_eras, "canonical_key")
    final_set_by_canonical = _map_rows_by(final_sets, "canonical_key")

    expected_era_keys = {row["canonical_key"] for row in source_eras}
    expected_set_keys = {row["canonical_key"] for row in source_sets}
    missing_era_keys = sorted(expected_era_keys - set(final_era_by_canonical.keys()))
    missing_set_keys = sorted(expected_set_keys - set(final_set_by_canonical.keys()))

    mismatched_set_era_links = []
    for source_set in source_sets:
        final_set = final_set_by_canonical.get(source_set["canonical_key"])
        final_era = final_era_by_canonical.get(source_set["era_canonical_key"])
        if not final_set or not final_era:
            continue
        if final_set.get("era_id") != final_era.get("id"):
            mismatched_set_era_links.append(
                {
                    "canonical_key": source_set["canonical_key"],
                    "name": source_set["name"],
                    "expected_era_id": final_era.get("id"),
                    "actual_era_id": final_set.get("era_id"),
                }
            )

    source_scrape_ready_count = sum(1 for row in source_sets if row.get("ready_for_daily_scrape"))
    final_scrape_ready_count = sum(1 for row in final_sets if row.get("ready_for_daily_scrape"))
    final_card_details_count = sum(1 for row in final_sets if row.get("has_card_details_url"))
    final_sealed_details_count = sum(1 for row in final_sets if row.get("has_sealed_details_url"))
    synced_tcg_ids = sorted({str(row.get("tcg_id")) for row in final_eras + final_sets if row.get("tcg_id")})

    report = {
        "summary": {
            "generated_at_utc": now_iso,
            "apply_changes": apply_changes,
            "tcg_id": tcg_id,
            "eras_discovered": len(source_eras),
            "eras_inserted": sum(1 for row in era_actions if row["action"] == "inserted"),
            "eras_updated": sum(1 for row in era_actions if row["action"] == "updated"),
            "eras_skipped": sum(1 for row in era_actions if row["action"] == "skipped"),
            "sets_discovered": len(source_sets),
            "sets_inserted": sum(1 for row in set_actions if row["action"] == "inserted"),
            "sets_updated": sum(1 for row in set_actions if row["action"] == "updated"),
            "sets_skipped": sum(1 for row in set_actions if row["action"] == "skipped"),
            "total_scrape_ready_sets_from_constants": source_scrape_ready_count,
            "total_scrape_ready_sets_in_db": final_scrape_ready_count,
            "total_sets_with_card_details_urls": final_card_details_count,
            "total_sets_with_sealed_details_urls": final_sealed_details_count,
            "conflict_count": len(conflicts),
        },
        "missing_optional_metadata": _summarize_missing_metadata(source_sets),
        "verification": {
            "missing_era_canonical_keys": missing_era_keys,
            "missing_set_canonical_keys": missing_set_keys,
            "duplicate_era_canonical_keys": _detect_duplicate_keys(final_eras, "canonical_key"),
            "duplicate_set_canonical_keys": _detect_duplicate_keys(final_sets, "canonical_key"),
            "mismatched_set_era_links": mismatched_set_era_links,
            "pokemon_tcg_id_consistent": synced_tcg_ids == [str(tcg_id)],
            "synced_tcg_ids": synced_tcg_ids,
            "scrape_ready_count_matches_constants": final_scrape_ready_count == source_scrape_ready_count,
        },
        "conflicts": conflicts,
        "eras": era_actions,
        "sets": set_actions,
    }

    output_path = report_path or DEFAULT_SYNC_REPORT_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    logger.info("pokemon_era_set_sync: wrote report to %s", output_path)
    return report