"""One-time historical TCGplayer catalog backfill.

The cold-start catalog baseline recorded pre-existing TCGplayer Pokemon catalog
identities as non-runnable ``ignored`` rows so normal discovery would never
report them as newly detected. This service turns those identities into real
source configs, so their cards and sealed products can be scraped for market
coverage.

Nothing here is part of normal new-set discovery or the nightly onboarding
worker: rows are only ever written back as ``ignored`` (still unclaimable) or
``completed``, never as a claimable status.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from backend.scripts.bootstrap_pokemon_set_configs import (
    ERA_SERIES_OVERRIDES,
    camel_to_pascal,
    normalize_set_key,
)
from backend.services.pokemon_set_config_generation_service import (
    _insert_before_closing_brace as insert_before_closing_brace,
    _parse_aliases as parse_aliases,
)
from backend.services.pokemon_tcg_api_set_service import MetadataResolution, resolve_set_metadata
from backend.services.tcgplayer_set_catalog_service import build_priceguide_urls, normalize_name

SOURCE_SYSTEM = "tcgplayer"
BASELINE_STATUS = "ignored"
BASELINE_STEP = "catalog_baseline"
COMPLETED_STATUS = "completed"
COMPLETED_STEP = "historical_scrape_complete"
BACKFILL_METADATA_KEY = "historical_backfill"
CATALOG_ONLY_ERA_FOLDER = "otherEra"

# Statuses the nightly onboarding worker can claim. This backfill must never
# write any of them, or a failed historical row would enter the live queue.
WORKER_CLAIMABLE_STATUSES = frozenset(
    {"detected", "ready", "retry", "running", "waiting", "manual_review"}
)

# Deliberately EMPTY. Populate only with human-confirmed pairs, keyed by the
# TCGplayer provider id, mapping to the authoritative Pokemon TCG API set NAME.
# This is the "explicit mapping" escape hatch for catalogs whose TCGplayer label
# differs from the API label (e.g. TCGplayer "Expedition" vs API "Expedition Base
# Set"). It only redirects which name is looked up — the unique exact-normalized
# match is still required, so a wrong entry cannot silently bind a config.
EXPLICIT_API_NAME_BY_SOURCE_SET_ID: Dict[str, str] = {}

_NON_SET_FILES = {"__init__.py", "baseConfig.py", "setMap.py"}
_DIGITS_RE = re.compile(r"^\d+$")


class BackfillError(RuntimeError):
    """Raised when a historical catalog row cannot be safely processed."""


@dataclass
class ConfigOutcome:
    """One report row for the configs stage (see the CLI report contract)."""

    source_set_id: str
    source_set_name: str
    canonical_key: Optional[str] = None
    era_folder: Optional[str] = None
    api_match_status: str = "not_attempted"
    pokemon_api_set_id: Optional[str] = None
    card_details_url: Optional[str] = None
    sealed_details_url: Optional[str] = None
    collision: bool = False
    config_path: Optional[str] = None
    set_map_path: Optional[str] = None
    readiness: str = "not_generated"
    error: Optional[str] = None
    notes: List[str] = field(default_factory=list)

    def as_report_row(self) -> Dict[str, Any]:
        return {
            "source_set_id": self.source_set_id,
            "source_set_name": self.source_set_name,
            "canonical_key": self.canonical_key,
            "era_folder": self.era_folder,
            "api_match_status": self.api_match_status,
            "pokemon_api_set_id": self.pokemon_api_set_id,
            "card_details_url": self.card_details_url,
            "sealed_details_url": self.sealed_details_url,
            "collision": self.collision,
            "config_path": self.config_path,
            "set_map_path": self.set_map_path,
            "readiness": self.readiness,
            "error": self.error,
            "notes": list(self.notes),
        }


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------
def _metadata(row: Dict[str, Any]) -> Dict[str, Any]:
    metadata = row.get("metadata_json")
    return dict(metadata) if isinstance(metadata, dict) else {}


def backfill_state(row: Dict[str, Any]) -> Dict[str, Any]:
    state = _metadata(row).get(BACKFILL_METADATA_KEY)
    return dict(state) if isinstance(state, dict) else {}


def is_baseline_candidate(row: Dict[str, Any]) -> bool:
    """Exactly the four-part selection contract for historical catalog rows."""
    return (
        str(row.get("source_system") or "") == SOURCE_SYSTEM
        and str(row.get("status") or "") == BASELINE_STATUS
        and str(row.get("current_step") or "") == BASELINE_STEP
        and _metadata(row).get("onboarded") is False
        and bool(str(row.get("source_set_id") or "").strip())
    )


def is_already_completed(row: Dict[str, Any]) -> bool:
    return str(backfill_state(row).get("scrape_status") or "") == "success"


def select_baseline_rows(
    rows: Iterable[Dict[str, Any]],
    *,
    source_set_ids: Sequence[str] = (),
    max_sets: Optional[int] = None,
    resume: bool = False,
) -> List[Dict[str, Any]]:
    requested = {str(value).strip() for value in source_set_ids if str(value).strip()}
    selected: List[Dict[str, Any]] = []
    for row in rows:
        if not is_baseline_candidate(row):
            continue
        if requested and str(row.get("source_set_id")) not in requested:
            continue
        if resume and is_already_completed(row):
            continue
        selected.append(row)
    if max_sets is not None and max_sets > 0:
        selected = selected[:max_sets]
    return selected


# ---------------------------------------------------------------------------
# Deterministic provider URLs
# ---------------------------------------------------------------------------
def catalog_urls(source_set_id: Any) -> Tuple[str, str]:
    """Build the scrape targets straight from the stored provider identity.

    The baseline already resolved and stored this ID; re-resolving it against
    TCGplayer search would risk silently binding a config to a different set.
    """
    raw = str(source_set_id).strip()
    if not _DIGITS_RE.match(raw):
        raise BackfillError(f"source_set_id is not a numeric TCGplayer identity: {source_set_id!r}")
    return build_priceguide_urls(int(raw))


# ---------------------------------------------------------------------------
# Strict Pokemon API match
# ---------------------------------------------------------------------------
def api_lookup_name_for(source_set_id: Any, source_set_name: str) -> str:
    """The name to search the Pokemon API with: a confirmed override, else the provider label."""
    return EXPLICIT_API_NAME_BY_SOURCE_SET_ID.get(str(source_set_id).strip(), source_set_name)


def resolve_api_match(
    source_set_name: str,
    api_rows: Iterable[Dict[str, Any]],
    *,
    expected_api_id: Optional[str] = None,
) -> MetadataResolution:
    """Only a unique, exact normalized-name match is accepted as authoritative."""
    return resolve_set_metadata(source_set_name, api_rows, expected_api_id=expected_api_id)


# ---------------------------------------------------------------------------
# Canonical keys
# ---------------------------------------------------------------------------
def existing_canonical_keys(pokemon_root: Path) -> Set[str]:
    keys: Set[str] = set()
    if not pokemon_root.is_dir():
        return keys
    for era_dir in pokemon_root.iterdir():
        if not era_dir.is_dir() or era_dir.name == "__pycache__":
            continue
        for path in era_dir.glob("*.py"):
            if path.name in _NON_SET_FILES:
                continue
            keys.add(path.stem)
    return keys


def allocate_canonical_key(
    source_set_name: str, source_set_id: Any, taken_keys: Set[str]
) -> Tuple[str, bool]:
    """Deterministic key; collides only into a provider-ID suffix, never a counter."""
    base_key = normalize_set_key(str(source_set_name))
    if base_key not in taken_keys:
        return base_key, False
    return f"{base_key}Tcg{str(source_set_id).strip()}", True


def class_name_for(canonical_key: str) -> str:
    return f"Set{camel_to_pascal(canonical_key)}Config"


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
_COVERAGE_ONLY_BLOCK = (
    "    # Historical catalog identity added for market/card coverage only.\n"
    "    # It is NOT an approved pack-simulation product.\n"
    "    CATALOG_ONLY = True\n"
    "    SUPPORTS_OPENING_SIMULATION = False\n"
    "    USE_MONTE_CARLO_V2 = False\n"
    '    PULL_MODEL_STATUS = "unsupported"\n'
    "    PULL_RATE_MAPPING = {}\n"
)


def render_catalog_only_config(
    class_name: str,
    source_set_name: str,
    source_set_id: str,
    card_details_url: str,
    sealed_details_url: str,
) -> str:
    """No Pokemon API match: nothing is invented, SET_ID stays None."""
    return (
        "from .baseConfig import BaseSetConfig\n\n\n"
        f"class {class_name}(BaseSetConfig):\n"
        f"    SET_NAME = {source_set_name!r}\n"
        "    SET_ABBREVIATION = None\n\n"
        "    # SET_ID means Pokemon API set ID; this catalog has no unique API match.\n"
        "    SET_ID = None\n"
        "    RELEASE_DATE = None\n"
        "    PRINTED_TOTAL = None\n"
        "    TOTAL = None\n"
        "    SYMBOL_IMAGE_URL = None\n"
        "    LOGO_IMAGE_URL = None\n\n"
        "    # Authoritative TCGplayer catalog identity from the cold-start baseline.\n"
        f"    TCGPLAYER_SET_ID = {str(source_set_id)!r}\n"
        f"    TCGPLAYER_SET_NAME = {source_set_name!r}\n\n"
        f"    CARD_DETAILS_URL = {card_details_url!r}\n"
        f"    SEALED_DETAILS_URL = {sealed_details_url!r}\n"
        "    PRICE_ENDPOINTS = {}\n\n"
        f"{_COVERAGE_ONLY_BLOCK}"
    )


def render_api_backed_config(
    class_name: str,
    api_data: Dict[str, Any],
    source_set_name: str,
    source_set_id: str,
    card_details_url: str,
    sealed_details_url: str,
) -> str:
    """Unique Pokemon API match: API metadata is authoritative, provider identity is preserved."""
    images = api_data.get("images") or {}
    return (
        "from .baseConfig import BaseSetConfig\n\n\n"
        f"class {class_name}(BaseSetConfig):\n"
        f"    SET_NAME = {api_data.get('name')!r}\n"
        f"    SET_ABBREVIATION = {api_data.get('ptcgoCode')!r}\n\n"
        f"    SET_ID = {str(api_data.get('id'))!r}\n"
        f"    RELEASE_DATE = {api_data.get('releaseDate')!r}\n"
        f"    PRINTED_TOTAL = {api_data.get('printedTotal')!r}\n"
        f"    TOTAL = {api_data.get('total')!r}\n"
        f"    SYMBOL_IMAGE_URL = {images.get('symbol')!r}\n"
        f"    LOGO_IMAGE_URL = {images.get('logo')!r}\n\n"
        "    # Authoritative TCGplayer catalog identity from the cold-start baseline.\n"
        f"    TCGPLAYER_SET_ID = {str(source_set_id)!r}\n"
        f"    TCGPLAYER_SET_NAME = {source_set_name!r}\n\n"
        f"    CARD_DETAILS_URL = {card_details_url!r}\n"
        f"    SEALED_DETAILS_URL = {sealed_details_url!r}\n"
        "    PRICE_ENDPOINTS = {}\n\n"
        f"{_COVERAGE_ONLY_BLOCK}"
    )


# ---------------------------------------------------------------------------
# Atomic source writes
# ---------------------------------------------------------------------------
def _insert_import(text: str, import_line: str) -> str:
    if re.search(rf"^{re.escape(import_line)}$", text, re.MULTILINE):
        return text
    imports = list(re.finditer(r"^from\s+\..+$", text, re.MULTILINE))
    if imports:
        position = imports[-1].end()
        return text[:position] + "\n" + import_line + text[position:]
    return import_line + "\n" + text


def _render_set_map(
    text: str, canonical_key: str, class_name: str, aliases: Iterable[str]
) -> Tuple[str, List[str]]:
    skipped: List[str] = []
    text = _insert_import(text, f"from .{canonical_key} import {class_name}")
    if not re.search(rf"^\s*['\"]{re.escape(canonical_key)}['\"]\s*:", text, re.MULTILINE):
        text = insert_before_closing_brace(
            text, "SET_CONFIG_MAP", f"    '{canonical_key}' : {class_name},"
        )
    existing = parse_aliases(text)
    for alias in sorted({a for a in aliases if a}):
        owner = existing.get(alias)
        if owner == canonical_key:
            continue
        if owner:
            # Another set already owns this alias; never repoint it.
            skipped.append(alias)
            continue
        text = insert_before_closing_brace(
            text, "SET_ALIAS_MAP", f"    {alias!r}: {canonical_key!r},"
        )
        existing[alias] = canonical_key
    return text, skipped


def write_config_atomically(
    era_dir: Path, canonical_key: str, class_name: str, rendered: str, aliases: Iterable[str]
) -> Tuple[Path, Path, List[str]]:
    """Write the set config and its setMap entry, or leave both files untouched."""
    config_path = era_dir / f"{canonical_key}.py"
    set_map_path = era_dir / "setMap.py"
    if config_path.exists():
        raise BackfillError(f"config already exists and is never overwritten: {config_path}")
    if not set_map_path.exists():
        raise BackfillError(f"setMap.py not found for era: {era_dir.name}")

    original_set_map = set_map_path.read_text(encoding="utf-8")
    updated_set_map, skipped_aliases = _render_set_map(
        original_set_map, canonical_key, class_name, aliases
    )

    # Validate syntax AND that the setMap import line will actually resolve,
    # before either file is retained.
    config_tree = ast.parse(rendered)
    ast.parse(updated_set_map)
    if not any(
        isinstance(node, ast.ClassDef) and node.name == class_name for node in config_tree.body
    ):
        raise BackfillError(
            f"generated config does not define {class_name!r}; the setMap import would fail"
        )

    config_path.write_text(rendered, encoding="utf-8", newline="\n")
    try:
        if updated_set_map != original_set_map:
            set_map_path.write_text(updated_set_map, encoding="utf-8", newline="\n")
    except Exception:
        config_path.unlink(missing_ok=True)
        set_map_path.write_text(original_set_map, encoding="utf-8", newline="\n")
        raise
    return config_path, set_map_path, skipped_aliases


# ---------------------------------------------------------------------------
# Per-row generation
# ---------------------------------------------------------------------------
def _era_folder_for_series(series: str) -> Optional[str]:
    mapped = ERA_SERIES_OVERRIDES.get(series)
    return mapped[0] if mapped else None


def generate_config_for_row(
    row: Dict[str, Any],
    *,
    pokemon_root: Path,
    api_rows: Optional[Iterable[Dict[str, Any]]],
    taken_keys: Set[str],
    commit: bool,
) -> ConfigOutcome:
    """Generate one historical catalog config. ``taken_keys`` is updated in place."""
    source_set_id = str(row.get("source_set_id") or "").strip()
    source_set_name = str(row.get("source_set_name") or "").strip()
    outcome = ConfigOutcome(source_set_id=source_set_id, source_set_name=source_set_name)

    try:
        card_url, sealed_url = catalog_urls(source_set_id)
    except BackfillError as exc:
        outcome.error = str(exc)
        return outcome
    outcome.card_details_url = card_url
    outcome.sealed_details_url = sealed_url

    if not source_set_name:
        outcome.error = "baseline row has no source_set_name to name a config from"
        return outcome

    if api_rows is None:
        # A transient Pokemon API failure must never masquerade as "no match" —
        # that would file an API-backed set into otherEra with no metadata.
        outcome.api_match_status = "lookup_failed"
        outcome.error = "Pokemon TCG API lookup failed; refusing to downgrade to catalog-only"
        return outcome

    lookup_name = api_lookup_name_for(source_set_id, source_set_name)
    if lookup_name != source_set_name:
        outcome.notes.append(f"explicit API name mapping applied: {lookup_name!r}")
    resolution = resolve_api_match(lookup_name, api_rows)
    outcome.api_match_status = resolution.status

    api_data = resolution.set_data if resolution.status == "resolved" else None
    if api_data:
        era_folder = _era_folder_for_series(str(api_data.get("series") or ""))
        if not era_folder:
            outcome.error = (
                f"Pokemon API series {api_data.get('series')!r} has no known era folder"
            )
            return outcome
        outcome.pokemon_api_set_id = str(api_data.get("id"))
    else:
        era_folder = CATALOG_ONLY_ERA_FOLDER

    era_dir = pokemon_root / era_folder
    if not era_dir.is_dir():
        outcome.era_folder = era_folder
        outcome.error = f"era folder does not exist locally: {era_folder}"
        return outcome
    outcome.era_folder = era_folder

    canonical_key, collided = allocate_canonical_key(source_set_name, source_set_id, taken_keys)
    outcome.canonical_key = canonical_key
    outcome.collision = collided
    if collided:
        outcome.notes.append(
            f"canonical name collided with an existing set; suffixed with provider id {source_set_id}"
        )
    if canonical_key in taken_keys:
        outcome.error = (
            f"canonical key {canonical_key!r} already exists; this provider id was already generated"
        )
        return outcome

    class_name = class_name_for(canonical_key)
    if api_data:
        rendered = render_api_backed_config(
            class_name, api_data, source_set_name, source_set_id, card_url, sealed_url
        )
        aliases = {
            canonical_key.lower(),
            normalize_name(source_set_name),
            normalize_name(str(api_data.get("name") or "")),
            str(api_data.get("id") or "").lower(),
        }
        if api_data.get("ptcgoCode"):
            aliases.add(str(api_data["ptcgoCode"]).lower())
    else:
        rendered = render_catalog_only_config(
            class_name, source_set_name, source_set_id, card_url, sealed_url
        )
        aliases = {canonical_key.lower(), normalize_name(source_set_name)}

    outcome.config_path = str((era_dir / f"{canonical_key}.py").as_posix())
    outcome.set_map_path = str((era_dir / "setMap.py").as_posix())

    if not commit:
        outcome.readiness = "would_generate"
        taken_keys.add(canonical_key)
        return outcome

    try:
        config_path, set_map_path, skipped_aliases = write_config_atomically(
            era_dir, canonical_key, class_name, rendered, aliases
        )
    except (BackfillError, SyntaxError, OSError) as exc:
        outcome.error = f"{type(exc).__name__}: {exc}"
        outcome.config_path = None
        outcome.set_map_path = None
        return outcome

    outcome.config_path = str(config_path.as_posix())
    outcome.set_map_path = str(set_map_path.as_posix())
    if skipped_aliases:
        outcome.notes.append(f"aliases already owned elsewhere, left alone: {skipped_aliases}")
    outcome.readiness = "ready_for_daily_scrape"
    taken_keys.add(canonical_key)
    return outcome


# ---------------------------------------------------------------------------
# Baseline job status handling
# ---------------------------------------------------------------------------
def _merged_metadata(row: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    metadata = _metadata(row)  # preserves the original baseline history verbatim
    state = backfill_state(row)
    state.update(updates)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    metadata[BACKFILL_METADATA_KEY] = state
    return metadata


def build_progress_fields(row: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    """Partial work: the row stays ignored so the nightly worker never claims it."""
    metadata = _merged_metadata(row, updates)
    metadata["onboarded"] = False
    return {
        "status": BASELINE_STATUS,
        "current_step": BASELINE_STEP,
        "metadata_json": metadata,
    }


def build_completion_fields(row: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    """Config generated, synced, and scraped: the historical row is finally done."""
    metadata = _merged_metadata(row, updates)
    metadata["onboarded"] = True
    return {
        "status": COMPLETED_STATUS,
        "current_step": COMPLETED_STEP,
        "metadata_json": metadata,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
