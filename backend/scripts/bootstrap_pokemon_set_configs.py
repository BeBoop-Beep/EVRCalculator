import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import requests

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))


API_URL = "https://api.pokemontcg.io/v2/sets"
REPORT_PATH = Path("backend/constants/tcg/pokemon/pokemon_set_bootstrap_report.json")

# Scarlet & Violet is explicitly preserved as the completed reference era.
LOCKED_ERAS = {"scarletAndVioletEra"}

ERA_SERIES_OVERRIDES = {
    "Scarlet & Violet": ("scarletAndVioletEra", "Scarlet and Violet"),
    "Mega Evolution": ("megaEvolutionEra", "Mega Evolution"),
    "Sword & Shield": ("swordAndShieldEra", "Sword and Shield"),
    "Sun & Moon": ("sunAndMoonEra", "Sun and Moon"),
    "XY": ("xyEra", "XY"),
    "Black & White": ("blackAndWhiteEra", "Black and White"),
    "HeartGold & SoulSilver": ("heartGoldAndSoulSilverEra", "HeartGold and SoulSilver"),
    "Platinum": ("platinumEra", "Platinum"),
    "Diamond & Pearl": ("diamondAndPearlEra", "Diamond and Pearl"),
    "EX": ("exEra", "EX"),
    "E-Card": ("eCardEra", "E-Card"),
    "Neo": ("neoEra", "Neo"),
    "Gym": ("gymEra", "Gym"),
    "Base": ("baseWotcEra", "Base/WOTC"),
    "POP": ("popEra", "POP"),
    "NP": ("npEra", "NP"),
    "Other": ("otherEra", "Other"),
}

SKIP_SET_NAMES = {
    "Scarlet and Violet Base Set",
    "Scarlet and Violet 151",
    "Paldea Evolved",
    "Obsidian Flames",
    "Paradox Rift",
    "Paldean Fates",
    "Temporal Forces",
    "Twilight Masquerade",
    "Shrouded Fable",
    "Stellar Crown",
    "Surging Sparks",
    "Prismatic Evolutions",
    "Journey Together",
    "Destined Rivals",
    "Black Bolt",
    "White Flare",
}


def tokenize(value: str) -> List[str]:
    normalized = value.replace("&", " and ").replace("/", " ").replace("-", " ")
    return re.findall(r"[A-Za-z0-9]+", normalized)


def to_camel_case(words: List[str]) -> str:
    if not words:
        return "unknown"
    first = words[0].lower()
    rest = "".join(word[:1].upper() + word[1:] for word in words[1:])
    return f"{first}{rest}"


def camel_to_pascal(name: str) -> str:
    if not name:
        return "Unknown"
    return name[0].upper() + name[1:]


def normalize_set_key(set_name: str) -> str:
    return to_camel_case(tokenize(set_name))


def normalize_era(series: str) -> Tuple[str, str]:
    if series in ERA_SERIES_OVERRIDES:
        return ERA_SERIES_OVERRIDES[series]
    words = tokenize(series)
    era_folder = f"{to_camel_case(words)}Era"
    era_label = " ".join(words) if words else "Unknown"
    return era_folder, era_label


def load_backend_env() -> None:
    if load_dotenv is None:
        return
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
    load_dotenv(env_path, override=False)


def fetch_sets_from_api(api_key: str = "") -> List[Dict]:
    if not api_key:
        raise RuntimeError("Missing POKEMON_TCG_API_KEY environment variable")

    all_sets: List[Dict] = []
    page = 1
    page_size = 250

    while True:
        params = {
            "page": page,
            "pageSize": page_size,
            "orderBy": "releaseDate",
        }
        response = requests.get(
            API_URL,
            params=params,
            headers={
                "Accept": "application/json",
                "X-Api-Key": api_key,
                "User-Agent": "EVRCalculator/1.0",
            },
            timeout=30,
        )
        if response.status_code in {401, 403}:
            raise RuntimeError("Pokemon TCG API request was rejected. Verify POKEMON_TCG_API_KEY.")
        response.raise_for_status()
        payload = response.json()

        data = payload.get("data", [])
        all_sets.extend(data)

        total_count = payload.get("totalCount", len(all_sets))
        if len(all_sets) >= total_count or not data:
            break
        page += 1

    return all_sets


def render_base_config(era_label: str) -> str:
    return f'''from types import MappingProxyType

class BaseSetConfig:
    COLLECTION = "TCG"
    TCG = "Pokemon"
    ERA = "{era_label}"

    RARITY_MAPPING = MappingProxyType({{
        "common": "common",
        "uncommon": "uncommon",
        "rare": "rare",
        "holo rare": "hits",
        "rare holo": "hits",
        "ultra rare": "hits",
        "double rare": "hits",
        "illustration rare": "hits",
        "special illustration rare": "hits",
        "secret rare": "hits",
    }})

    GOD_PACK_CONFIG = {{
        "enabled": False,
        "pull_rate": 0,
        "strategy": {{}}
    }}

    DEMI_GOD_PACK_CONFIG = {{
        "enabled": False,
        "pull_rate": 0,
        "strategy": {{}}
    }}

    SLOTS_PER_RARITY = {{
        "common": 4,
        "uncommon": 3,
        "reverse": 2,
        "rare": 1,
    }}

    @classmethod
    def validate(cls):
        required_attrs = ["SET_NAME", "PULL_RATE_MAPPING", "SEALED_DETAILS_URL"]
        for attr in required_attrs:
            if not hasattr(cls, attr):
                raise ValueError(f"{{cls.__name__}} missing required attribute: {{attr}}")

'''


def render_set_config(
    class_name: str,
    set_name: str,
    set_abbreviation,
    set_id: str,
    release_date,
    printed_total,
    total,
    symbol_url,
    logo_url,
) -> str:
    abbr_literal = "None" if not set_abbreviation else repr(set_abbreviation)
    release_literal = "None" if not release_date else repr(release_date)
    printed_literal = "None" if printed_total is None else str(printed_total)
    total_literal = "None" if total is None else str(total)
    symbol_literal = "None" if not symbol_url else repr(symbol_url)
    logo_literal = "None" if not logo_url else repr(logo_url)

    return f'''from .baseConfig import BaseSetConfig

class {class_name}(BaseSetConfig):
    SET_NAME = {set_name!r}
    SET_ABBREVIATION = {abbr_literal}

    SET_ID = {set_id!r}
    RELEASE_DATE = {release_literal}
    PRINTED_TOTAL = {printed_literal}
    TOTAL = {total_literal}
    SYMBOL_IMAGE_URL = {symbol_literal}
    LOGO_IMAGE_URL = {logo_literal}

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {{}}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {{}}
'''


def parse_assignment_value(file_text: str, variable_name: str) -> str:
    match = re.search(rf"^\s*{re.escape(variable_name)}\s*=\s*(.+)$", file_text, flags=re.MULTILINE)
    if not match:
        return ""
    return match.group(1).strip()


def is_truthy_python_literal(raw: str) -> bool:
    if not raw:
        return False
    normalized = raw.strip().rstrip(",")
    if normalized in {"None", "''", '""', "{}"}:
        return False
    return True


def has_expected_class(file_text: str, class_name: str) -> bool:
    return re.search(rf"^\s*class\s+{re.escape(class_name)}\s*\(", file_text, flags=re.MULTILINE) is not None


def append_compat_class(file_path: Path, content: str) -> None:
    with file_path.open("a", encoding="utf-8", newline="\n") as handle:
        if not content.startswith("\n"):
            handle.write("\n")
        handle.write(content)


def build_alias_map(set_records: List[Dict]) -> Dict[str, str]:
    aliases: Dict[str, str] = {}
    for record in set_records:
        key = record["key"]
        aliases[key.lower()] = key

        set_name = str(record.get("set_name") or "").strip().lower()
        if set_name:
            aliases[set_name] = key

        abbreviation = str(record.get("set_abbreviation") or "").strip().lower()
        if abbreviation:
            aliases[abbreviation] = key

        set_id = str(record.get("set_id") or "").strip().lower()
        if set_id:
            aliases[set_id] = key

    return dict(sorted(aliases.items(), key=lambda item: item[0]))


def render_set_map(set_records: List[Dict]) -> str:
    imports = []
    map_entries = []

    for record in set_records:
        key = record["key"]
        class_name = record["class_name"]
        imports.append(f"from .{key} import {class_name}")
        map_entries.append(f"    '{key}' : {class_name},")

    alias_map = build_alias_map(set_records)
    alias_entries = [f'    "{alias}": "{canonical}",' for alias, canonical in alias_map.items()]

    lines = []
    lines.extend(imports)
    lines.append("")
    lines.append("")
    lines.append("SET_CONFIG_MAP = {")
    lines.extend(map_entries)
    lines.append("}")
    lines.append("")
    lines.append("SET_ALIAS_MAP = {")
    lines.extend(alias_entries)
    lines.append("}")
    lines.append("")

    return "\n".join(lines)


def ensure_era_scaffold(era_dir: Path, era_label: str) -> Dict[str, bool]:
    created = {
        "era_dir": False,
        "init": False,
        "base_config": False,
    }

    if not era_dir.exists():
        era_dir.mkdir(parents=True, exist_ok=True)
        created["era_dir"] = True

    init_file = era_dir / "__init__.py"
    if not init_file.exists():
        init_file.write_text("", encoding="utf-8", newline="\n")
        created["init"] = True

    base_config = era_dir / "baseConfig.py"
    if not base_config.exists():
        base_config.write_text(render_base_config(era_label), encoding="utf-8", newline="\n")
        created["base_config"] = True

    return created


def collect_existing_set_files(era_dir: Path) -> List[Path]:
    files = []
    for file_path in era_dir.glob("*.py"):
        if file_path.name in {"__init__.py", "baseConfig.py", "setMap.py"}:
            continue
        files.append(file_path)
    return sorted(files, key=lambda p: p.name.lower())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bootstrap Pokemon era/set constants from Pokemon TCG API metadata")
    parser.add_argument("--apply", action="store_true", help="Write generated files. Omit for dry-run.")
    parser.add_argument("--include-scarlet-violet", action="store_true", help="Allow write operations for scarletAndVioletEra.")
    parser.add_argument("--api-key", default=os.getenv("POKEMON_TCG_API_KEY", ""), help="Pokemon TCG API key (optional).")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    dry_run = not args.apply
    load_backend_env()
    api_key = args.api_key or os.getenv("POKEMON_TCG_API_KEY", "")

    backend_root = Path(__file__).resolve().parents[1]
    pokemon_root = backend_root / "constants" / "tcg" / "pokemon"
    pokemon_root.mkdir(parents=True, exist_ok=True)

    print(f"[BOOTSTRAP] dry_run={dry_run}")
    all_sets = fetch_sets_from_api(api_key)
    print(f"[BOOTSTRAP] fetched sets from API: {len(all_sets)}")

    existing_era_dirs_before = sorted(
        [p.name for p in pokemon_root.iterdir() if p.is_dir() and p.name != "__pycache__"]
    )

    series_groups: Dict[str, List[Dict]] = {}
    for item in all_sets:
        series = item.get("series") or "Other"
        series_groups.setdefault(series, []).append(item)

    era_inventory = []
    set_report = []
    conflicts = []

    total_existing_local_set_files = 0
    total_new_set_stubs_generated = 0
    total_set_maps_touched = 0
    completed_incomplete_eras = []
    created_eras = []

    for series, sets in sorted(series_groups.items(), key=lambda pair: pair[0].lower()):
        era_folder, era_label = normalize_era(series)
        era_dir = pokemon_root / era_folder

        era_exists_before = era_dir.exists()
        set_files_before = collect_existing_set_files(era_dir) if era_exists_before else []
        total_existing_local_set_files += len(set_files_before)

        should_skip_locked = era_folder in LOCKED_ERAS and not args.include_scarlet_violet

        era_created = {"era_dir": False, "init": False, "base_config": False}
        if not should_skip_locked and not dry_run:
            era_created = ensure_era_scaffold(era_dir, era_label)

        if era_created["era_dir"]:
            created_eras.append(era_folder)

        era_set_records: List[Dict] = []
        existing_keys = set()
        key_collision_counts: Dict[str, int] = {}

        for set_data in sorted(sets, key=lambda row: (row.get("releaseDate") or "", row.get("name") or "")):
            set_name = str(set_data.get("name") or "").strip()
            if not set_name:
                continue

            if era_folder == "scarletAndVioletEra" and set_name in SKIP_SET_NAMES and not args.include_scarlet_violet:
                continue

            set_id = str(set_data.get("id") or "").strip()
            key = normalize_set_key(set_name)
            base_key = key

            while key in existing_keys:
                key_collision_counts.setdefault(base_key, 1)
                key_collision_counts[base_key] += 1
                key = f"{base_key}{key_collision_counts[base_key]}"

            existing_keys.add(key)

            class_name = f"Set{camel_to_pascal(key)}Config"
            set_file = era_dir / f"{key}.py"
            existed_before = set_file.exists()
            generated_now = False
            preexisting_partial_work = existed_before
            notes = []

            set_abbreviation = set_data.get("ptcgoCode")
            images = set_data.get("images") or {}
            symbol_url = images.get("symbol")
            logo_url = images.get("logo")

            rendered_config = render_set_config(
                class_name=class_name,
                set_name=set_name,
                set_abbreviation=set_abbreviation,
                set_id=set_id,
                release_date=set_data.get("releaseDate"),
                printed_total=set_data.get("printedTotal"),
                total=set_data.get("total"),
                symbol_url=symbol_url,
                logo_url=logo_url,
            )

            if should_skip_locked:
                notes.append("Skipped write for locked reference era.")
            elif dry_run:
                generated_now = not existed_before
                if generated_now:
                    notes.append("Would generate set config.")
            else:
                if not set_file.parent.exists():
                    set_file.parent.mkdir(parents=True, exist_ok=True)

                if existed_before:
                    original_text = set_file.read_text(encoding="utf-8")
                    if not has_expected_class(original_text, class_name):
                        compat_block = (
                            f"\n\n# TODO: Added by bootstrap for import compatibility; existing content preserved.\n"
                            f"class {class_name}(BaseSetConfig):\n"
                            f"    SET_NAME = {set_name!r}\n"
                            f"    SET_ABBREVIATION = {repr(set_abbreviation) if set_abbreviation else 'None'}\n\n"
                            f"    SET_ID = {set_id!r}\n"
                            f"    RELEASE_DATE = {repr(set_data.get('releaseDate')) if set_data.get('releaseDate') else 'None'}\n"
                            f"    PRINTED_TOTAL = {str(set_data.get('printedTotal')) if set_data.get('printedTotal') is not None else 'None'}\n"
                            f"    TOTAL = {str(set_data.get('total')) if set_data.get('total') is not None else 'None'}\n"
                            f"    SYMBOL_IMAGE_URL = {repr(symbol_url) if symbol_url else 'None'}\n"
                            f"    LOGO_IMAGE_URL = {repr(logo_url) if logo_url else 'None'}\n\n"
                            f"    CARD_DETAILS_URL = None\n"
                            f"    SEALED_DETAILS_URL = None\n"
                            f"    PRICE_ENDPOINTS = {{}}\n"
                            f"    PULL_RATE_MAPPING = {{}}\n"
                        )
                        append_compat_class(set_file, compat_block)
                        generated_now = True
                        conflicts.append(
                            {
                                "era": era_folder,
                                "set_key": key,
                                "file": str(set_file.relative_to(backend_root.parent)).replace("\\", "/"),
                                "reason": "Expected class missing in existing file; appended compatibility class and preserved original content.",
                            }
                        )
                        notes.append("Existing file preserved; compatibility class appended.")
                else:
                    set_file.write_text(rendered_config, encoding="utf-8", newline="\n")
                    generated_now = True
                    total_new_set_stubs_generated += 1
                    notes.append("Generated missing set config stub.")

            set_text = ""
            if set_file.exists():
                set_text = set_file.read_text(encoding="utf-8")

            card_raw = parse_assignment_value(set_text, "CARD_DETAILS_URL")
            sealed_raw = parse_assignment_value(set_text, "SEALED_DETAILS_URL")
            price_raw = parse_assignment_value(set_text, "PRICE_ENDPOINTS")

            has_card_details_url = is_truthy_python_literal(card_raw)
            has_sealed_details_url = is_truthy_python_literal(sealed_raw)
            has_price_endpoints = is_truthy_python_literal(price_raw)
            ready_for_daily_scrape = has_card_details_url or has_sealed_details_url

            record = {
                "era_name": era_label,
                "era_folder": era_folder,
                "canonical_key": key,
                "set_name": set_name,
                "release_date": set_data.get("releaseDate"),
                "local_config_file_path": str(set_file.relative_to(backend_root.parent)).replace("\\", "/"),
                "exists_locally": set_file.exists(),
                "generated_now": generated_now,
                "preexisting_partial_work": preexisting_partial_work,
                "has_card_details_url": has_card_details_url,
                "has_sealed_details_url": has_sealed_details_url,
                "has_price_endpoints": has_price_endpoints,
                "ready_for_daily_scrape": ready_for_daily_scrape,
                "notes": " ".join(notes) if notes else "",
                "set_id": set_id,
                "set_abbreviation": set_abbreviation,
                "class_name": class_name,
                "key": key,
            }

            era_set_records.append(record)
            set_report.append({k: v for k, v in record.items() if k not in {"class_name", "key", "set_id", "set_abbreviation"}})

        if not should_skip_locked:
            set_map_file = era_dir / "setMap.py"
            existing_set_files_after = collect_existing_set_files(era_dir) if era_dir.exists() else []

            # Ensure every local set file has a matching class name pattern for import safety.
            normalized_records = []
            for file_path in existing_set_files_after:
                file_key = file_path.stem
                expected_class_name = f"Set{camel_to_pascal(file_key)}Config"
                file_text = file_path.read_text(encoding="utf-8") if file_path.exists() else ""

                if not has_expected_class(file_text, expected_class_name):
                    matching = next((r for r in era_set_records if r["key"] == file_key), None)
                    set_name = matching["set_name"] if matching else file_key
                    set_abbreviation = matching.get("set_abbreviation") if matching else None
                    set_id = matching.get("set_id") if matching else file_key
                    release_date = matching.get("release_date") if matching else None

                    if not dry_run and file_path.exists():
                        compat_block = (
                            f"\n\n# TODO: Added by bootstrap for import compatibility; existing content preserved.\n"
                            f"class {expected_class_name}(BaseSetConfig):\n"
                            f"    SET_NAME = {set_name!r}\n"
                            f"    SET_ABBREVIATION = {repr(set_abbreviation) if set_abbreviation else 'None'}\n\n"
                            f"    SET_ID = {set_id!r}\n"
                            f"    RELEASE_DATE = {repr(release_date) if release_date else 'None'}\n"
                            f"    PRINTED_TOTAL = None\n"
                            f"    TOTAL = None\n"
                            f"    SYMBOL_IMAGE_URL = None\n"
                            f"    LOGO_IMAGE_URL = None\n\n"
                            f"    CARD_DETAILS_URL = None\n"
                            f"    SEALED_DETAILS_URL = None\n"
                            f"    PRICE_ENDPOINTS = {{}}\n"
                            f"    PULL_RATE_MAPPING = {{}}\n"
                        )
                        append_compat_class(file_path, compat_block)
                        conflicts.append(
                            {
                                "era": era_folder,
                                "set_key": file_key,
                                "file": str(file_path.relative_to(backend_root.parent)).replace("\\", "/"),
                                "reason": "Expected class missing; appended compatibility class for setMap imports.",
                            }
                        )

                normalized = next((r for r in era_set_records if r["key"] == file_key), None)
                normalized_records.append(
                    {
                        "key": file_key,
                        "class_name": expected_class_name,
                        "set_name": normalized["set_name"] if normalized else file_key,
                        "set_abbreviation": normalized["set_abbreviation"] if normalized else None,
                        "set_id": normalized["set_id"] if normalized else file_key,
                    }
                )

            rendered_set_map = render_set_map(sorted(normalized_records, key=lambda row: row["key"].lower()))
            set_map_exists_before = set_map_file.exists()
            set_map_needs_update = True
            if set_map_exists_before:
                current_set_map = set_map_file.read_text(encoding="utf-8")
                set_map_needs_update = current_set_map != rendered_set_map

            if not dry_run and set_map_needs_update:
                set_map_file.write_text(rendered_set_map, encoding="utf-8", newline="\n")
                total_set_maps_touched += 1
            elif dry_run and set_map_needs_update:
                total_set_maps_touched += 1

        set_files_after = collect_existing_set_files(era_dir) if era_dir.exists() else []
        if era_exists_before and not should_skip_locked and len(set_files_after) > len(set_files_before):
            completed_incomplete_eras.append(era_folder)

        era_inventory.append(
            {
                "era_name": era_label,
                "era_folder": era_folder,
                "exists_before": era_exists_before,
                "created_now": era_created["era_dir"],
                "locked_reference": should_skip_locked,
                "set_count_api": len(sets),
                "local_set_files_before": len(set_files_before),
                "local_set_files_after": len(set_files_after),
                "status": (
                    "locked_reference"
                    if should_skip_locked
                    else "created" if era_created["era_dir"] else "updated"
                ),
            }
        )

    ready_sets = [row for row in set_report if row["ready_for_daily_scrape"]]
    missing_target_sets = [row for row in set_report if not row["ready_for_daily_scrape"]]

    existing_era_dirs_after = sorted(
        [p.name for p in pokemon_root.iterdir() if p.is_dir() and p.name != "__pycache__"]
    )

    summary = {
        "generated_at_utc": dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z"),
        "dry_run": dry_run,
        "source": "Pokemon TCG API v2 sets endpoint",
        "eras_discovered": len(era_inventory),
        "era_folders_existing_before": existing_era_dirs_before,
        "era_folders_existing_after": existing_era_dirs_after,
        "era_folders_created": sorted(set(created_eras)),
        "incomplete_eras_completed": sorted(set(completed_incomplete_eras)),
        "sets_discovered_total": len(all_sets),
        "existing_local_set_files_before": total_existing_local_set_files,
        "new_set_stubs_generated": total_new_set_stubs_generated,
        "set_maps_created_or_updated": total_set_maps_touched,
        "scrape_ready_set_count": len(ready_sets),
        "missing_tcgplayer_target_count": len(missing_target_sets),
        "conflicts_preserved_count": len(conflicts),
    }

    report_payload = {
        "summary": summary,
        "era_inventory": era_inventory,
        "sets": set_report,
        "scrape_ready_sets": ready_sets,
        "missing_tcgplayer_targets": missing_target_sets,
        "conflicts_preserved": conflicts,
    }

    output_path = backend_root.parent / REPORT_PATH
    if not dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report_payload, indent=2), encoding="utf-8", newline="\n")

    print(json.dumps(summary, indent=2))
    print(f"[BOOTSTRAP] report_path={output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
