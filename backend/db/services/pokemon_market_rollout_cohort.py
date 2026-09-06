from __future__ import annotations

from typing import Any, Iterable, Sequence

from backend.desirability.public_analytics_policy import is_public_analytics_eligible

ROLLOUT_VIEW = "pokemon_market_rollout_root_sets_v1"

_CORE_SET_COLUMNS = (
    "id,canonical_key,name,era_id,release_date,logo_image_url,symbol_image_url,"
    "supports_opening_simulation,parent_opening_set_id"
)


def _core_market_sets(client: Any) -> list[dict[str, Any]]:
    rows = list(client.table("sets").select(_CORE_SET_COLUMNS).execute().data or [])
    return [
        dict(row)
        for row in rows
        if row.get("supports_opening_simulation") is True
        and is_public_analytics_eligible(row)
        and not row.get("parent_opening_set_id")
    ]


def _rollout_market_sets(client: Any, *, market_date: str | None = None) -> list[dict[str, Any]]:
    try:
        query = client.table(ROLLOUT_VIEW).select(
            "set_id,set_name,canonical_key,era_id,era_name,release_date,"
            "logo_image_url,symbol_image_url,activated_market_date,coverage_pct"
        )
        if market_date:
            query = query.lte("activated_market_date", str(market_date)[:10])
        rows = list(query.execute().data or [])
    except Exception:
        # Compatibility for tests/environments that have not installed the
        # staged rollout migration yet. Core Market behavior remains unchanged.
        return []

    return [
        {
            "id": row.get("set_id"),
            "name": row.get("set_name"),
            "canonical_key": row.get("canonical_key"),
            "era_id": row.get("era_id"),
            "era": row.get("era_name"),
            "release_date": row.get("release_date"),
            "logo_image_url": row.get("logo_image_url"),
            "symbol_image_url": row.get("symbol_image_url"),
            "market_rollout_activated_date": row.get("activated_market_date"),
            "market_rollout_coverage_pct": row.get("coverage_pct"),
        }
        for row in rows
        if row.get("set_id")
    ]


def resolve_market_root_cohort(client: Any, *, market_date: str | None = None) -> list[dict[str, Any]]:
    """Core public Market roots plus explicitly activated historical-era roots.

    Existing public/RIP eligibility remains the core cohort. The rollout table
    can add older eras without changing RIP eligibility. If a rollout set was
    already in the core cohort, rollout metadata is attached to the same root
    rather than producing a duplicate.
    """
    core = _core_market_sets(client)
    rollout = _rollout_market_sets(client, market_date=market_date)
    merged = {str(row["id"]): dict(row) for row in core if row.get("id")}
    for row in rollout:
        set_id = str(row["id"])
        merged[set_id] = {**merged.get(set_id, {}), **row}

    rows = list(merged.values())
    if market_date:
        day = str(market_date)[:10]
        rows = [
            row for row in rows
            if not row.get("release_date") or str(row.get("release_date"))[:10] <= day
        ]

    era_ids = sorted({str(row.get("era_id")) for row in rows if row.get("era_id")})
    era_names: dict[str, str] = {}
    if era_ids:
        era_names = {
            str(row.get("id")): str(row.get("name") or "")
            for row in (client.table("eras").select("id,name").in_("id", era_ids).execute().data or [])
        }
    return sorted(
        [
            {**row, "era": row.get("era") or era_names.get(str(row.get("era_id")))}
            for row in rows
        ],
        key=lambda row: str(row.get("id") or ""),
    )


def rollout_transition_set_ids(client: Any, market_date: str) -> set[str]:
    """Root sets whose staged era activates exactly on ``market_date``."""
    return {
        str(row["id"])
        for row in _rollout_market_sets(client, market_date=market_date)
        if str(row.get("market_rollout_activated_date") or "")[:10] == str(market_date)[:10]
    }


def expand_raw_card_member_set_ids(client: Any, root_set_ids: Sequence[str]) -> list[str]:
    """Expand roots to child subsets that count toward their parent Set Value.

    Raw Card Market must see Trainer Galleries, Shiny Vaults, Galarian Gallery,
    Classic Collection, etc. Sealed Market continues to use root ids only.
    """
    roots = sorted({str(value) for value in root_set_ids if value})
    if not roots:
        return []
    rows = list(
        client.table("sets")
        .select("id,parent_opening_set_id,counts_toward_parent_set_value,catalog_only")
        .or_(
            "id.in.(" + ",".join(roots) + "),parent_opening_set_id.in.(" + ",".join(roots) + ")"
        )
        .execute().data or []
    )
    result = set(roots)
    for row in rows:
        parent_id = str(row.get("parent_opening_set_id") or "")
        if (
            parent_id in roots
            and row.get("counts_toward_parent_set_value") is True
            and row.get("catalog_only") is not True
            and row.get("id")
        ):
            result.add(str(row["id"]))
    return sorted(result)
