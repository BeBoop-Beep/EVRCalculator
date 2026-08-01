from __future__ import annotations

import ast
import importlib.util
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable

from backend.scripts.bootstrap_pokemon_set_configs import (
    ERA_SERIES_OVERRIDES, camel_to_pascal, normalize_set_key,
)
from backend.services.tcgplayer_set_catalog_service import normalize_name

SERIES_TO_ERA = dict(ERA_SERIES_OVERRIDES)


class ConfigGenerationError(ValueError):
    pass


@dataclass(frozen=True)
class GeneratedConfig:
    canonical_key: str
    era_folder: str
    config_path: Path
    set_map_path: Path
    changed_paths: tuple[Path, ...]


def _era_for_series(series: str) -> tuple[str, str]:
    if series not in SERIES_TO_ERA:
        raise ConfigGenerationError(f"unsupported Pokemon API series: {series!r}")
    return SERIES_TO_ERA[series]


def _era_rarities(era_dir: Path) -> list[str]:
    path = era_dir / "baseConfig.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "RARITY_MAPPING" for target in node.targets
        ):
            call = node.value
            mapping_node = call.args[0] if isinstance(call, ast.Call) and call.args else call
            if isinstance(mapping_node, ast.Dict):
                values = [ast.literal_eval(key) for key in mapping_node.keys if key is not None]
                return sorted({str(value) for value in values})
    return ["common", "uncommon", "rare"]


def _render_config(class_name: str, data: Dict[str, Any], card_url: str, sealed_url: str, rarities: Iterable[str]) -> str:
    images = data.get("images") or {}
    mapping = "\n".join(f"        {rarity!r}: 0.0," for rarity in rarities)
    return (
        "from .baseConfig import BaseSetConfig\n\n\n"
        f"class {class_name}(BaseSetConfig):\n"
        f"    SET_NAME = {data['name']!r}\n"
        f"    SET_ABBREVIATION = {data.get('ptcgoCode')!r}\n"
        f"    SET_ID = {str(data['id'])!r}\n"
        f"    RELEASE_DATE = {data.get('releaseDate')!r}\n"
        f"    PRINTED_TOTAL = {data.get('printedTotal')!r}\n"
        f"    TOTAL = {data.get('total')!r}\n"
        f"    SYMBOL_IMAGE_URL = {images.get('symbol')!r}\n"
        f"    LOGO_IMAGE_URL = {images.get('logo')!r}\n"
        f"    CARD_DETAILS_URL = {card_url!r}\n"
        f"    SEALED_DETAILS_URL = {sealed_url!r}\n"
        "    PRICE_ENDPOINTS = {}\n"
        '    PULL_MODEL_STATUS = "pending"\n'
        "    USE_MONTE_CARLO_V2 = False\n"
        "    PULL_RATE_MAPPING = {\n"
        f"{mapping}\n"
        "    }\n"
    )


def _parse_aliases(text: str) -> Dict[str, str]:
    match = re.search(r"SET_ALIAS_MAP\s*=\s*(\{.*?\})", text, re.DOTALL)
    if not match:
        return {}
    try:
        value = ast.literal_eval(match.group(1))
        return {str(key): str(target) for key, target in value.items()}
    except (SyntaxError, ValueError):
        raise ConfigGenerationError("SET_ALIAS_MAP is not a literal mapping")


def _insert_before_closing_brace(text: str, variable: str, line: str) -> str:
    match = re.search(rf"^{variable}\s*=\s*\{{", text, re.MULTILINE)
    if not match:
        raise ConfigGenerationError(f"{variable} not found")
    close = text.find("\n}", match.end())
    if close < 0:
        raise ConfigGenerationError(f"{variable} closing brace not found")
    return text[:close] + "\n" + line + text[close:]


def generate_one_set_config(
    checkout_root: Path, metadata: Dict[str, Any], *,
    card_details_url: str, sealed_details_url: str,
) -> GeneratedConfig:
    era_folder, _ = _era_for_series(str(metadata.get("series") or ""))
    canonical_key = normalize_set_key(str(metadata["name"]))
    class_name = f"Set{camel_to_pascal(canonical_key)}Config"
    era_dir = checkout_root / "backend/constants/tcg/pokemon" / era_folder
    if not era_dir.is_dir():
        raise ConfigGenerationError(f"era folder does not exist: {era_folder}")
    config_path = era_dir / f"{canonical_key}.py"
    set_map_path = era_dir / "setMap.py"
    rendered = _render_config(
        class_name, metadata, card_details_url, sealed_details_url, _era_rarities(era_dir)
    )
    changed: list[Path] = []
    if config_path.exists() and config_path.read_text(encoding="utf-8") != rendered:
        raise ConfigGenerationError(f"target config already exists with different content: {config_path}")

    text = set_map_path.read_text(encoding="utf-8")
    original = text
    import_line = f"from .{canonical_key} import {class_name}"
    if not re.search(rf"^{re.escape(import_line)}$", text, re.MULTILINE):
        imports = list(re.finditer(r"^from\s+.+$", text, re.MULTILINE))
        position = imports[-1].end() if imports else 0
        text = text[:position] + "\n" + import_line + text[position:]
    map_entry = f"    {canonical_key!r} : {class_name},"
    if not re.search(rf"^\s*['\"]{re.escape(canonical_key)}['\"]\s*:", text, re.MULTILINE):
        text = _insert_before_closing_brace(text, "SET_CONFIG_MAP", map_entry)

    aliases = {
        canonical_key, normalize_name(str(metadata["name"])), str(metadata["id"]).lower(),
    }
    if metadata.get("ptcgoCode"):
        aliases.add(str(metadata["ptcgoCode"]).lower())
    existing_aliases = _parse_aliases(text)
    for alias in sorted(aliases):
        owner = existing_aliases.get(alias)
        if owner and owner != canonical_key:
            raise ConfigGenerationError(f"alias collision: {alias!r} already maps to {owner!r}")
        if not owner:
            text = _insert_before_closing_brace(
                text, "SET_ALIAS_MAP", f"    {alias!r}: {canonical_key!r},"
            )
            existing_aliases[alias] = canonical_key
    # All collision and structural validation finishes before either file is written.
    if not config_path.exists():
        config_path.write_text(rendered, encoding="utf-8")
        changed.append(config_path)
    if text != original:
        set_map_path.write_text(text, encoding="utf-8")
        changed.append(set_map_path)
    return GeneratedConfig(
        canonical_key, era_folder, config_path, set_map_path, tuple(changed)
    )


def apply_approved_pull_model(
    checkout_root: Path, era_folder: str, canonical_key: str, manifest: Dict[str, Any],
    rarity_census: Dict[str, int],
) -> Path:
    """Persist the complete approved model, keeping base pools distinct from hit odds."""
    path = checkout_root / "backend/constants/tcg/pokemon" / era_folder / f"{canonical_key}.py"
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    assignments: Dict[str, ast.Assign] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assignments[target.id] = node
    required = ("PULL_RATE_MAPPING", "PULL_MODEL_STATUS", "USE_MONTE_CARLO_V2")
    if any(name not in assignments for name in required):
        raise ConfigGenerationError("target config lacks pending pull-model assignments")
    base_aliases = {
        "common": {"common"}, "uncommon": {"uncommon"}, "rare": {"rare", "regular rare"},
    }
    normalized_census = {
        " ".join(str(key).strip().lower().replace("_", " ").split()): int(value)
        for key, value in rarity_census.items()
    }
    base_counts: Dict[str, int] = {}
    for target, aliases in base_aliases.items():
        matches = [(key, count) for key, count in normalized_census.items() if key in aliases]
        if len(matches) != 1 or matches[0][1] <= 0:
            raise ConfigGenerationError(f"ambiguous or missing base rarity census for {target}: {matches}")
        base_counts[target] = matches[0][1]
    hit_denominators = {
        " ".join(str(key).strip().lower().replace("_", " ").split()): float(value)
        for key, value in manifest["rarity_denominators"].items()
    }
    forbidden = set(base_aliases) | {"regular rare"}
    collision = sorted(forbidden & set(hit_denominators))
    if collision:
        raise ConfigGenerationError(
            f"manifest must not supply base card-pool denominators: {collision}"
        )
    pull_mapping = {**base_counts, **hit_denominators}
    slots = manifest["slot_assumptions"]
    reverse_slots = slots.get("reverse_slot_probabilities")
    rare_slot = slots.get("rare_slot_probability") or slots.get("rare_slot_probabilities")
    overrides = manifest.get("pack_state_overrides")
    if not isinstance(reverse_slots, dict) or not isinstance(rare_slot, dict):
        raise ConfigGenerationError("approved reverse and rare slot mappings are required")
    if not isinstance(overrides, dict):
        raise ConfigGenerationError("approved pack_state_overrides object is required")
    replacements = {
        "PULL_RATE_MAPPING": "    PULL_RATE_MAPPING = " + repr(pull_mapping),
        "PULL_MODEL_STATUS": '    PULL_MODEL_STATUS = "approved"',
        "USE_MONTE_CARLO_V2": "    USE_MONTE_CARLO_V2 = True",
    }
    lines = text.splitlines()
    nodes = sorted((assignments[name] for name in required), key=lambda node: node.lineno, reverse=True)
    for node in nodes:
        name = next(
            target.id for target in node.targets if isinstance(target, ast.Name) and target.id in replacements
        )
        lines[node.lineno - 1:node.end_lineno] = [replacements[name]]
    insertion = [
        "    REVERSE_SLOT_PROBABILITIES = " + repr(reverse_slots),
        "    RARE_SLOT_PROBABILITY = " + repr(rare_slot),
        "",
        "    @classmethod",
        "    def get_pack_state_overrides(cls):",
        "        return " + repr(overrides),
    ]
    # Generated pending configs have no model-defining slot fields or override method.
    lines.extend(insertion)
    updated = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
    ast.parse(updated)
    path.write_text(updated, encoding="utf-8")
    return path
