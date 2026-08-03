import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.constants.tcg.pokemon import historical_catalog_image_sources as catalog_sources
from backend.scripts.bootstrap_pokemon_set_configs import fetch_sets_from_api, load_backend_env, normalize_set_key


POKEMON_ROOT = Path("backend/constants/tcg/pokemon")
DEFAULT_REPORT_PATH = POKEMON_ROOT / "pokemon_set_api_enrichment_report.json"

FIELD_ORDER = [
    "SET_ID",
    "RELEASE_DATE",
    "PRINTED_TOTAL",
    "TOTAL",
    "SYMBOL_IMAGE_URL",
    "LOGO_IMAGE_URL",
]

LOCAL_KEY_COMPATIBILITY = {
    "scarletAndVioletBase": ["scarletAndViolet"],
    "scarletAndViolet151": ["151"],
}


def parse_assignment_value(file_text: str, variable_name: str) -> Optional[str]:
    match = re.search(rf"^(\s*{re.escape(variable_name)}\s*=\s*)(.+)$", file_text, flags=re.MULTILINE)
    if not match:
        return None
    return match.group(2).strip()


def has_assignment(file_text: str, variable_name: str) -> bool:
    return parse_assignment_value(file_text, variable_name) is not None


def is_missing_literal(raw_value: Optional[str]) -> bool:
    if raw_value is None:
        return True
    normalized = raw_value.strip().rstrip(",")
    return normalized in {"None", "''", '""'}


def render_python_literal(value: Any) -> str:
    if value is None:
        return "None"
    if isinstance(value, str):
        return repr(value)
    return str(value)


def replace_assignment_line(file_text: str, variable_name: str, rendered_value: str) -> Tuple[str, bool]:
    pattern = rf"^(\s*{re.escape(variable_name)}\s*=\s*)(.+)$"
    match = re.search(pattern, file_text, flags=re.MULTILINE)
    if not match:
        return file_text, False

    replacement = f"{match.group(1)}{rendered_value}"
    start, end = match.span()
    return file_text[:start] + replacement + file_text[end:], True


def insert_metadata_block(file_text: str, field_values: Dict[str, Any]) -> Tuple[str, bool]:
    missing_fields = [
        field
        for field in FIELD_ORDER
        if field in field_values and not has_assignment(file_text, field)
    ]
    if not missing_fields:
        return file_text, False

    block_lines = [f"    {field} = {render_python_literal(field_values[field])}" for field in missing_fields]
    block = "\n".join(block_lines) + "\n\n"

    anchor_match = re.search(r"^\s*CARD_DETAILS_URL\s*=.*$", file_text, flags=re.MULTILINE)
    if anchor_match:
        start = anchor_match.start()
        return file_text[:start] + block + file_text[start:], True

    abbreviation_match = re.search(r"^\s*SET_ABBREVIATION\s*=.*$\n?", file_text, flags=re.MULTILINE)
    if abbreviation_match:
        insert_at = abbreviation_match.end()
        suffix = "" if file_text[insert_at:insert_at + 1] == "\n" else "\n"
        return file_text[:insert_at] + suffix + block + file_text[insert_at:], True

    return file_text + "\n" + block, True


def normalize_metadata_spacing(file_text: str) -> str:
    return re.sub(r"\n{3,}(\s*CARD_DETAILS_URL\s*=)", r"\n\n\1", file_text)


def normalize_name(value: Optional[str]) -> str:
    text = (value or "").strip().lower()
    text = text.replace("&", "and")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def build_api_indexes(all_sets: List[Dict[str, Any]]) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    by_id: Dict[str, Dict[str, Any]] = {}
    by_key: Dict[str, Dict[str, Any]] = {}
    by_name: Dict[str, Dict[str, Any]] = {}

    for row in all_sets:
        set_id = str(row.get("id") or "").strip()
        set_name = str(row.get("name") or "").strip()
        if set_id:
            by_id[set_id] = row
        if set_name:
            by_name[normalize_name(set_name)] = row
            by_key[normalize_set_key(set_name)] = row

    return by_id, by_key, by_name


def resolve_api_row(local_key: str, set_name: str, set_id: Optional[str], by_id: Dict[str, Dict[str, Any]], by_key: Dict[str, Dict[str, Any]], by_name: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if set_id and set_id in by_id:
        return by_id[set_id]

    exact_name_match = by_name.get(normalize_name(set_name))
    if exact_name_match:
        return exact_name_match

    if local_key in by_key:
        return by_key[local_key]

    for compat_key in LOCAL_KEY_COMPATIBILITY.get(local_key, []):
        if compat_key in by_key:
            return by_key[compat_key]

    normalized_local_name_key = normalize_set_key(set_name)
    if normalized_local_name_key in by_key:
        return by_key[normalized_local_name_key]

    return None


def build_local_inventory() -> List[Dict[str, Any]]:
    inventory: List[Dict[str, Any]] = []
    # Not every directory under the Pokemon root is an era: scrape_job_reports/
    # holds generated JSON and has no setMap.py to import.
    era_dirs = [
        path
        for path in POKEMON_ROOT.iterdir()
        if path.is_dir()
        and path.name != "__pycache__"
        and (path / "setMap.py").is_file()
    ]

    for era_dir in sorted(era_dirs, key=lambda path: path.name.lower()):
        module_name = f"backend.constants.tcg.pokemon.{era_dir.name}.setMap"
        module = __import__(module_name, fromlist=["SET_CONFIG_MAP"])
        set_config_map = getattr(module, "SET_CONFIG_MAP", {})
        for local_key, config_cls in set_config_map.items():
            file_path = Path("backend/constants/tcg/pokemon") / era_dir.name / f"{local_key}.py"
            inventory.append(
                {
                    "era": era_dir.name,
                    "key": local_key,
                    "file_path": file_path,
                    "set_name": getattr(config_cls, "SET_NAME", None),
                    "set_id": getattr(config_cls, "SET_ID", None),
                }
            )

    return inventory


def parse_string_literal(file_text: str, variable_name: str) -> Optional[str]:
    raw = parse_assignment_value(file_text, variable_name)
    if raw is None:
        return None
    stripped = raw.strip().rstrip(",")
    if stripped in {"None", ""}:
        return None
    return stripped.strip("'\"") or None


def build_catalog_review(
    *,
    canonical_key: str,
    config_text: str,
    api_by_id: Dict[str, Dict[str, Any]],
    internal_card_count: Optional[int],
) -> Dict[str, Any]:
    """Review one historical TCGplayer-only catalog for reviewed image sources.

    This proposes IMAGE SOURCES only. It never returns a set identity, because a
    reviewed API set is frequently already owned by another local set.
    """
    mapping = catalog_sources.resolve(canonical_key=canonical_key)

    if mapping is not None:
        tcgplayer_set_id = mapping.tcgplayer_set_id
        tcgplayer_set_name = mapping.tcgplayer_set_name
        api_set_ids = list(mapping.api_set_ids)
        match_strategy = mapping.strategy
        mapping_kind = mapping.match_kind
        expected_api_card_count = sum(
            int((api_by_id.get(api_id) or {}).get("total") or 0) for api_id in api_set_ids
        )
        missing_api_ids = [api_id for api_id in api_set_ids if api_id not in api_by_id]

        if missing_api_ids:
            accepted = False
            reason = (
                f"rejected: reviewed image-source id(s) {missing_api_ids} are not in the "
                "current Pokemon API catalog"
            )
        elif internal_card_count is not None and internal_card_count != mapping.reviewed_internal_card_count:
            accepted = False
            reason = (
                "rejected: internal card-count drift since review "
                f"(reviewed {mapping.reviewed_internal_card_count}, live {internal_card_count}); "
                "re-verify before syncing images"
            )
        else:
            accepted = True
            reason = f"accepted: {mapping.evidence}"
    else:
        tcgplayer_set_id = parse_string_literal(config_text, "TCGPLAYER_SET_ID")
        tcgplayer_set_name = parse_string_literal(config_text, "TCGPLAYER_SET_NAME")
        api_set_ids = []
        match_strategy = "none"
        mapping_kind = catalog_sources.NO_EQUIVALENT
        expected_api_card_count = 0
        accepted = False
        refusal = catalog_sources.refusal_reason(canonical_key)
        reason = (
            f"rejected: {refusal}"
            if refusal
            else (
                "rejected: no Pokemon API set covers this TCGplayer catalog; it stays "
                "TCGplayer-only with no image source"
            )
        )

    return {
        "canonical_key": canonical_key,
        "tcgplayer_set_id": tcgplayer_set_id,
        "tcgplayer_set_name": tcgplayer_set_name,
        "proposed_api_image_source_ids": api_set_ids,
        "match_strategy": match_strategy,
        "mapping_kind": mapping_kind,
        "expected_internal_card_count": internal_card_count,
        "expected_api_card_count": expected_api_card_count,
        "accepted": accepted,
        "reason": reason,
    }


def summarize_catalog_reviews(reviews: List[Dict[str, Any]]) -> Dict[str, int]:
    summary = {
        catalog_sources.ONE_TO_ONE: 0,
        catalog_sources.PARENT_OR_MULTI: 0,
        catalog_sources.NO_EQUIVALENT: 0,
        "accepted_image_source_mappings": 0,
        "rejected_or_unmapped": 0,
    }
    for review in reviews:
        summary[review["mapping_kind"]] = summary.get(review["mapping_kind"], 0) + 1
        if review["accepted"]:
            summary["accepted_image_source_mappings"] += 1
        else:
            summary["rejected_or_unmapped"] += 1
    return summary


def load_internal_card_counts(canonical_keys: List[str]) -> Dict[str, Optional[int]]:
    """Live per-set card counts, used to detect drift since the mapping review.

    Best effort: the enrichment dry run must still produce a report when the
    database is unreachable, so failures degrade to unknown counts.
    """
    counts: Dict[str, Optional[int]] = {key: None for key in canonical_keys}
    if not canonical_keys:
        return counts
    try:
        from backend.db.clients.supabase_client import supabase

        set_rows = (
            supabase.table("sets").select("id,canonical_key")
            .in_("canonical_key", canonical_keys).execute()
        ).data or []
        for set_row in set_rows:
            key = set_row.get("canonical_key")
            if not key:
                continue
            response = (
                supabase.table("cards").select("id", count="exact")
                .eq("set_id", set_row["id"]).limit(1).execute()
            )
            counts[key] = response.count
    except Exception as exc:  # noqa: BLE001 - report generation must not depend on the DB
        print(f"[enrich] internal card counts unavailable ({exc}); reporting them as null")
    return counts


def enrich_constants(apply_changes: bool, report_path: Path) -> Dict[str, Any]:
    load_backend_env()
    api_key = os.getenv("POKEMON_TCG_API_KEY", "")
    all_sets = fetch_sets_from_api(api_key)
    by_id, by_key, by_name = build_api_indexes(all_sets)
    inventory = build_local_inventory()

    results: List[Dict[str, Any]] = []
    unresolved_rows: List[Dict[str, Any]] = []
    updated_files = 0
    updated_fields = 0
    unresolved = 0

    for row in inventory:
        file_path = Path(row["file_path"])
        file_text = file_path.read_text(encoding="utf-8")
        api_row = resolve_api_row(
            local_key=row["key"],
            set_name=row["set_name"],
            set_id=row.get("set_id"),
            by_id=by_id,
            by_key=by_key,
            by_name=by_name,
        )

        if not api_row:
            unresolved += 1
            unresolved_rows.append(
                {
                    "era": row["era"],
                    "canonical_key": row["key"],
                    "set_name": row["set_name"],
                    "file_path": file_path.as_posix(),
                    "config_text": file_text,
                }
            )
            continue

        images = api_row.get("images") or {}
        candidate_values = {
            "SET_ID": api_row.get("id"),
            "RELEASE_DATE": api_row.get("releaseDate"),
            "SET_ABBREVIATION": api_row.get("ptcgoCode"),
            "PRINTED_TOTAL": api_row.get("printedTotal"),
            "TOTAL": api_row.get("total"),
            "SYMBOL_IMAGE_URL": images.get("symbol"),
            "LOGO_IMAGE_URL": images.get("logo"),
        }

        patched_text = file_text
        changed_fields: List[str] = []
        formatting_changed = False

        fields_to_insert = {
            field_name: field_value
            for field_name, field_value in candidate_values.items()
            if not has_assignment(patched_text, field_name) and field_value not in (None, "")
        }
        if fields_to_insert:
            patched_text, inserted = insert_metadata_block(patched_text, fields_to_insert)
            if inserted:
                changed_fields.extend(
                    [field_name for field_name in FIELD_ORDER if field_name in fields_to_insert]
                )

        for field_name, field_value in candidate_values.items():
            current_raw = parse_assignment_value(patched_text, field_name)
            if not is_missing_literal(current_raw):
                continue
            if field_value in (None, ""):
                continue
            if field_name in fields_to_insert:
                continue

            rendered_value = render_python_literal(field_value)
            patched_text, changed = replace_assignment_line(patched_text, field_name, rendered_value)

            if changed:
                changed_fields.append(field_name)

        normalized_text = normalize_metadata_spacing(patched_text)
        formatting_changed = normalized_text != patched_text
        patched_text = normalized_text

        status = "updated" if changed_fields else "formatted" if formatting_changed else "unchanged"

        if apply_changes and patched_text != file_text:
            file_path.write_text(patched_text, encoding="utf-8", newline="\n")
            updated_files += 1

        updated_fields += len(changed_fields)
        results.append(
            {
                "era": row["era"],
                "canonical_key": row["key"],
                "set_name": row["set_name"],
                "file_path": file_path.as_posix(),
                "status": status,
                "updated_fields": changed_fields,
                "api_set_id": api_row.get("id"),
                "notes": "spacing normalized" if formatting_changed and not changed_fields else "",
            }
        )

    # Historical TCGplayer-only catalogs cannot be resolved by name: they have no
    # Pokemon API set of their own. Report reviewed IMAGE SOURCES for them instead
    # of a bare "no match found", and never turn a source into an identity.
    internal_card_counts = load_internal_card_counts([row["canonical_key"] for row in unresolved_rows])
    catalog_reviews: List[Dict[str, Any]] = []
    for row in unresolved_rows:
        review = build_catalog_review(
            canonical_key=row["canonical_key"],
            config_text=row["config_text"],
            api_by_id=by_id,
            internal_card_count=internal_card_counts.get(row["canonical_key"]),
        )
        catalog_reviews.append(review)
        results.append(
            {
                "era": row["era"],
                "canonical_key": row["canonical_key"],
                "set_name": row["set_name"],
                "file_path": row["file_path"],
                "status": "unresolved",
                "updated_fields": [],
                "notes": "No API set identity; see historical_catalog_review.",
                "historical_catalog_review": review,
            }
        )

    catalog_summary = summarize_catalog_reviews(catalog_reviews)

    report = {
        "summary": {
            "apply_changes": apply_changes,
            "sets_fetched_from_api": len(all_sets),
            "local_set_files_inspected": len(inventory),
            "files_updated": updated_files if apply_changes else sum(1 for row in results if row["status"] != "unchanged"),
            "fields_filled": updated_fields,
            "unresolved_sets": unresolved,
            "historical_catalog_reviews": catalog_summary,
        },
        "historical_catalog_review": catalog_reviews,
        "results": results,
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill missing Pokemon set constant metadata from the Pokemon TCG API")
    parser.add_argument("--apply", action="store_true", help="Write missing metadata into constant files")
    parser.add_argument("--report-path", default=str(DEFAULT_REPORT_PATH), help="Path for the enrichment report JSON")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report = enrich_constants(apply_changes=bool(args.apply), report_path=Path(args.report_path))
    print(json.dumps(report["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())