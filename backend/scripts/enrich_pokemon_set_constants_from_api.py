import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

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
    era_dirs = [path for path in POKEMON_ROOT.iterdir() if path.is_dir() and path.name != "__pycache__"]

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


def enrich_constants(apply_changes: bool, report_path: Path) -> Dict[str, Any]:
    load_backend_env()
    api_key = os.getenv("POKEMON_TCG_API_KEY", "")
    all_sets = fetch_sets_from_api(api_key)
    by_id, by_key, by_name = build_api_indexes(all_sets)
    inventory = build_local_inventory()

    results: List[Dict[str, Any]] = []
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
            results.append(
                {
                    "era": row["era"],
                    "canonical_key": row["key"],
                    "set_name": row["set_name"],
                    "file_path": file_path.as_posix(),
                    "status": "unresolved",
                    "updated_fields": [],
                    "notes": "No API set match found.",
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

    report = {
        "summary": {
            "apply_changes": apply_changes,
            "sets_fetched_from_api": len(all_sets),
            "local_set_files_inspected": len(inventory),
            "files_updated": updated_files if apply_changes else sum(1 for row in results if row["status"] != "unchanged"),
            "fields_filled": updated_fields,
            "unresolved_sets": unresolved,
        },
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