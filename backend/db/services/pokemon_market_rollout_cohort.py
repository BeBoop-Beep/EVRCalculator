from __future__ import annotations

from typing import Any, Sequence

from backend.desirability.public_analytics_policy import is_public_analytics_eligible

# Historical public Market rollout authority. It remains the source of truth for
# dates before the canonical global-market cutover so already-published history
# is never reinterpreted under a larger future cohort.
ROLLOUT_VIEW = "pokemon_market_public_rollout_root_sets_v1"

# Current canonical Market-domain authorities created by the Set Value / Top-10
# certification work. These are deliberately independent of RIP/opening
# eligibility and are the one root universe for Set Market, Raw/Top-10 Market,
# and the eligible Sealed root universe after the controlled cutover.
MARKET_READY_VIEW = "pokemon_market_set_value_publication_cohort_v1"
MARKET_CERTIFICATION_VIEW = "pokemon_market_root_set_publication_current_certification_v1"

# Sep 8 was already published with the staged 39-root basket. Never rewrite it.
# The next market date uses the canonical 106-root authority and chain-links
# through the common prior cohort.
MARKET_ROOT_AUTHORITY_CUTOVER_DATE = "2026-09-09"

_CORE_SET_COLUMNS = (
    "id,canonical_key,name,era_id,release_date,logo_image_url,symbol_image_url,"
    "supports_opening_simulation,parent_opening_set_id"
)


def _core_market_sets(client: Any) -> list[dict[str, Any]]:
    """Legacy pre-cutover core only; never the post-cutover Market authority."""
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
        # staged rollout migration yet. Historical core behavior remains intact.
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


def _legacy_market_root_cohort(client: Any, *, market_date: str | None = None) -> list[dict[str, Any]]:
    """Reconstruct the staged historical cohort exactly as it was published."""
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


def _canonical_market_root_cohort(
    client: Any, *, market_date: str | None = None,
) -> list[dict[str, Any]]:
    """Canonical post-cutover roots, gated on Standard + Top-10 structure.

    ``market_publication_ready`` intentionally permits a carried-forward last
    trustworthy observation. Same-day price freshness remains visible
    provenance, but it does not redefine the canonical root universe.
    """
    query = (
        client.table(MARKET_READY_VIEW)
        .select(
            "set_id,set_name,canonical_key,era_id,era_name,release_date,"
            "logo_image_url,symbol_image_url,market_scope,canonical_market_date,"
            "market_publication_ready,current_certification_status"
        )
        .eq("market_scope", "standard")
        .eq("market_publication_ready", True)
    )
    if market_date:
        query = query.eq("canonical_market_date", str(market_date)[:10])
    ready_rows = [dict(row) for row in (query.order("release_date").execute().data or [])]
    ready_ids = sorted({str(row.get("set_id")) for row in ready_rows if row.get("set_id")})
    if not ready_ids:
        day = str(market_date)[:10] if market_date else "current"
        raise RuntimeError(f"canonical Market root authority is empty for {day}")

    certification_rows: list[dict[str, Any]] = []
    for offset in range(0, len(ready_ids), 100):
        batch = ready_ids[offset:offset + 100]
        cert_query = (
            client.table(MARKET_CERTIFICATION_VIEW)
            .select(
                "set_id,market_scope,canonical_market_date,set_value_certified,"
                "top10_certified,market_scope_certified,price_freshness_certified,"
                "current_market_scope_certified,current_certification_status"
            )
            .eq("market_scope", "standard")
            .in_("set_id", batch)
        )
        if market_date:
            cert_query = cert_query.eq("canonical_market_date", str(market_date)[:10])
        certification_rows.extend(dict(row) for row in (cert_query.execute().data or []))

    cert_by_id = {
        str(row.get("set_id")): row
        for row in certification_rows
        if row.get("set_id")
    }
    structurally_blocked = sorted(
        set_id
        for set_id in ready_ids
        if set_id not in cert_by_id
        or cert_by_id[set_id].get("set_value_certified") is not True
        or cert_by_id[set_id].get("top10_certified") is not True
        or cert_by_id[set_id].get("market_scope_certified") is not True
    )
    if structurally_blocked:
        raise RuntimeError(
            "canonical Market authority failed Standard + Top-10 certification "
            f"for {len(structurally_blocked)} root(s): {structurally_blocked[:5]}"
        )

    by_id = {str(row["set_id"]): row for row in ready_rows if row.get("set_id")}
    return sorted(
        [
            {
                "id": set_id,
                "name": by_id[set_id].get("set_name"),
                "canonical_key": by_id[set_id].get("canonical_key"),
                "era_id": by_id[set_id].get("era_id"),
                "era": by_id[set_id].get("era_name"),
                "release_date": by_id[set_id].get("release_date"),
                "logo_image_url": by_id[set_id].get("logo_image_url"),
                "symbol_image_url": by_id[set_id].get("symbol_image_url"),
                "market_publication_ready": True,
                "market_structural_certified": True,
                "market_price_freshness_certified": bool(
                    cert_by_id[set_id].get("price_freshness_certified")
                ),
                "market_current_certification_status": cert_by_id[set_id].get(
                    "current_certification_status"
                ),
                "canonical_market_date": by_id[set_id].get("canonical_market_date"),
            }
            for set_id in ready_ids
        ],
        key=lambda row: str(row.get("id") or ""),
    )


def resolve_market_root_cohort(client: Any, *, market_date: str | None = None) -> list[dict[str, Any]]:
    """One global Market root universe with an immutable historical boundary.

    Dates before 2026-09-09 reconstruct the exact staged basket that was
    actually published. The cutover date and every date after it resolve from
    the canonical Market-domain Set Value + Top-10 authority, never from
    ``supports_opening_simulation`` or RIP/public-analytics eligibility.
    """
    if market_date and str(market_date)[:10] < MARKET_ROOT_AUTHORITY_CUTOVER_DATE:
        return _legacy_market_root_cohort(client, market_date=market_date)
    return _canonical_market_root_cohort(client, market_date=market_date)


def rollout_transition_set_ids(client: Any, market_date: str) -> set[str]:
    """Legacy explicitly activated roots; membership transitions are also
    detected directly by the daily index builder at the persisted-row seam."""
    day = str(market_date)[:10]
    if day >= MARKET_ROOT_AUTHORITY_CUTOVER_DATE:
        return set()
    return {
        str(row["id"])
        for row in _rollout_market_sets(client, market_date=day)
        if str(row.get("market_rollout_activated_date") or "")[:10] == day
    }


def expand_raw_card_member_set_ids(client: Any, root_set_ids: Sequence[str]) -> list[str]:
    """Expand roots to child subsets that count toward their parent Set Value.

    Raw Card Market must see Trainer Galleries, Shiny Vaults, Galarian Gallery,
    Classic Collection, etc. Sealed Market continues to use root ids only.
    """
    roots = sorted({str(value) for value in root_set_ids if value})
    if not roots:
        return []
    rows: list[dict[str, Any]] = []
    for offset in range(0, len(roots), 100):
        batch = roots[offset:offset + 100]
        rows.extend(
            list(
                client.table("sets")
                .select("id,parent_opening_set_id,counts_toward_parent_set_value,catalog_only")
                .in_("parent_opening_set_id", batch)
                .execute().data or []
            )
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
