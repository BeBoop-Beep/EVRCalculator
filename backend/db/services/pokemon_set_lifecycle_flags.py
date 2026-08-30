"""Single definition of Pokémon set lifecycle-flag semantics.

Kept deliberately dependency-free so the metadata sync service, the migration
backfill generator, and the runtime preflight all resolve flags identically. If
these rules ever diverge across callers, database metadata can get ahead of the
deployed runtime again — which is the 2026-08-03 failure mode.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


def _clean_url(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def supports_opening_simulation(config_cls: Any, *, catalog_only: Optional[bool] = None) -> bool:
    """Whether the opening-simulation runner would actually execute this set.

    Resolution order:

    1. An explicit ``SUPPORTS_OPENING_SIMULATION`` declaration wins.
    2. Otherwise derive it from the SAME runtime criterion ``run_all_v2_sets.py``
       uses to build its batch (``USE_MONTE_CARLO_V2``), so the flag can never
       claim a capability the runner does not have.
    3. Otherwise false.
    4. ``catalog_only`` always implies false, overriding even an explicit true.

    The previous default was ``not catalog_only``, which marked every ordinary
    non-catalog historical set as simulation-supported even though the runner
    would never execute it — 172 production rows against a far smaller real V2
    set list. Capability must be derived from the runner, not from the absence of
    a catalog flag.
    """
    resolved_catalog_only = (
        bool(getattr(config_cls, "CATALOG_ONLY", False)) if catalog_only is None else bool(catalog_only)
    )
    if resolved_catalog_only:
        return False

    declared = getattr(config_cls, "SUPPORTS_OPENING_SIMULATION", None)
    if declared is not None:
        return bool(declared)

    return bool(getattr(config_cls, "USE_MONTE_CARLO_V2", False))


def resolve_config_lifecycle_flags(config_cls: Any) -> Dict[str, Any]:
    """Resolve lifecycle flags for one ``SET_CONFIG_MAP`` config class."""
    catalog_only = bool(getattr(config_cls, "CATALOG_ONLY", False))
    supports_opening_simulation_flag = supports_opening_simulation(
        config_cls, catalog_only=catalog_only
    )
    card_details_url = _clean_url(getattr(config_cls, "CARD_DETAILS_URL", None))
    sealed_details_url = _clean_url(getattr(config_cls, "SEALED_DETAILS_URL", None))

    return {
        "parent_canonical_key": _clean_url(getattr(config_cls, "PARENT_OPENING_SET_KEY", None)),
        "is_subset": bool(getattr(config_cls, "IS_SUBSET", False)),
        "subset_type": _clean_url(getattr(config_cls, "SUBSET_TYPE", None)),
        "counts_toward_parent_set_value": bool(
            getattr(config_cls, "COUNTS_TOWARD_PARENT_SET_VALUE", False)
        ),
        "counts_toward_parent_opening": bool(
            getattr(config_cls, "COUNTS_TOWARD_PARENT_OPENING", False)
        ),
        "catalog_only": catalog_only,
        "supports_opening_simulation": supports_opening_simulation_flag,
        "card_details_url": card_details_url,
        "sealed_details_url": sealed_details_url,
        "has_card_details_url": bool(card_details_url),
        "has_sealed_details_url": bool(sealed_details_url),
        "ready_for_daily_scrape": is_daily_scrape_ready(
            card_details_url=card_details_url,
            catalog_only=catalog_only,
        ),
    }


def is_daily_scrape_ready(
    *,
    card_details_url: Optional[str],
    catalog_only: bool,
) -> bool:
    """The corrected daily card-price cohort rule.

    A card details URL is REQUIRED: both the cohort and the completeness check
    (``pokemon_scrape_missing_sets``) are defined over card observations, so a
    sealed-URL-only set could never satisfy completeness and would permanently
    wedge the batch as ``incomplete``.

    Catalog-only sets are excluded: they remain in the database and remain usable
    for manual/onboarding and historical catalog backfills, but must never gate
    public daily publication.
    """
    return bool(_clean_url(card_details_url)) and not bool(catalog_only)


def normalize_details_url(value: Any) -> Optional[str]:
    """Normalize a details URL for runtime-vs-database comparison.

    Intentionally conservative: trims surrounding whitespace and a single trailing
    slash, and lowercases scheme/host only. Query strings and path case are
    preserved because TCGplayer paths are case-sensitive.
    """
    text = _clean_url(value)
    if not text:
        return None

    without_trailing_slash = text[:-1] if text.endswith("/") and len(text) > 1 else text

    for scheme in ("https://", "http://"):
        if without_trailing_slash.lower().startswith(scheme):
            remainder = without_trailing_slash[len(scheme):]
            host, sep, path = remainder.partition("/")
            return f"{scheme}{host.lower()}{sep}{path}"

    return without_trailing_slash
