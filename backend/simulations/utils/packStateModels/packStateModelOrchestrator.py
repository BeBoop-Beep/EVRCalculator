from __future__ import annotations

import re
from copy import deepcopy
from typing import Callable, Dict, Optional

from . import eraPackStateBuilders


def normalize_era_key(era_name: str) -> str:
    normalized = str(era_name or "").strip().lower()
    normalized = normalized.replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized


def resolve_era_builder(era_key: str) -> Optional[Callable]:
    """Resolve era builder from the dedicated builder namespace only."""
    builder_name = f"build_{era_key}_pack_state_model"
    builder = getattr(eraPackStateBuilders, builder_name, None)
    if callable(builder):
        return builder
    return None


def resolve_pack_state_model(config) -> Dict[str, object]:
    """Resolve pack-state model in precedence order.

    1. config.get_pack_state_model()
    2. config.PACK_STATE_MODEL
    3. dynamic era builder by normalized config.ERA
    4. base fallback only when ERA is blank/unspecified
    """
    custom_getter = getattr(config, "get_pack_state_model", None)
    if callable(custom_getter):
        model = custom_getter()
        if model:
            return deepcopy(model)

    explicit_model = getattr(config, "PACK_STATE_MODEL", None)
    if isinstance(explicit_model, dict) and explicit_model:
        return deepcopy(explicit_model)

    era_name = getattr(config, "ERA", "")
    era_key = normalize_era_key(era_name)

    builder = resolve_era_builder(era_key)
    if callable(builder):
        return builder(config)

    if not era_key:
        return eraPackStateBuilders.build_base_pack_state_model(config)

    raise ValueError(
        f"No pack-state model builder registered for ERA='{era_name}' "
        f"(normalized='{era_key}'). "
        "Provide config.get_pack_state_model(), config.PACK_STATE_MODEL, "
        "or expose a correctly named builder in eraPackStateBuilders."
    )
