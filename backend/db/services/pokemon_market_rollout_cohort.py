from __future__ import annotations

from typing import Any, Sequence

from backend.desirability.public_analytics_policy import is_public_analytics_eligible
from backend.domain.pokemon.market_index import MARKET_INDEX_METHODOLOGY_VERSION

# Historical public Market rollout authority. It remains the source of truth for
# dates before the canonical global-market cutover so already-published history
# is never reinterpreted under a larger future cohort.
ROLLOUT_VIEW = "pokemon_market_public_rollout_root_sets_v1"

# Current canonical Market-domain authorities created by the Set Value / Top-10
# certification work. These are deliberately independent of RIP/opening
# eligibility and are the basis for the one root universe shared by Set Market,
# Raw/Top-10 Market, and the eligible Sealed root universe after the cutover.
MARKET_READY_VIEW = "pokemon_market_set_value_publication_cohort_v1"
MARKET_CERTIFICATION_VIEW = "pokemon_market_root_set_publication_current_certification_v1"
MARKET_INDEX_HISTORY_TABLE = "pokemon_market_index_daily_history"

# Keep the two authority contracts explicit.  The publication cohort owns
# membership/identity; certification owns structural and freshness evidence.
# In particular, do not widen the membership select when a caller needs more
# certification metadata -- production intentionally does not expose those
# columns on MARKET_READY_VIEW.
MARKET_MEMBERSHIP_COLUMNS = (
    "set_id,set_name,canonical_key,era_name,release_date,logo_image_url,"
    "symbol_image_url,market_scope,canonical_market_date,"
    "market_publication_ready,current_certification_status"
)
MARKET_CERTIFICATION_COLUMNS = (
    "set_id,market_scope,canonical_market_date,set_value_certified,"
    "top10_certified,market_scope_certified,price_freshness_certified,"
    "current_market_scope_certified,current_certification_status,"
    "oldest_component_price_date,newest_component_price_date,coverage_pct"
)

# Sep 8 was already published with the staged headline basket. Never rewrite it.
# The next market date resolves the canonical authority and chain-links through
# the common prior cohort.
MARKET_ROOT_AUTHORITY_CUTOVER_DATE = "2026-09-09"

# Sep 10, 2026: a human product decision (FINAL) froze public Market root
# membership as a specific, literal set of 106 root ids, seeded into
# ``pokemon_market_root_authority`` (see the migration of the same name).
# From this date forward, membership is NEVER recomputed from certification
# state (set_value_certified, top10_certified, market_scope_certified,
# market_publication_ready, or any rollout-override CTE); it is read from the
# authority table only. Certification remains available as annotation.
# Sep 9 itself keeps the certification-derived ``_canonical_market_root_cohort``
# behavior unchanged -- it was already published and must not be reinterpreted.
MARKET_ROOT_AUTHORITY_TABLE_CUTOVER_DATE = "2026-09-10"
MARKET_ROOT_AUTHORITY_TABLE = "pokemon_market_root_authority"

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


def _latest_persisted_root_ids(client: Any, *, before_date: str | None) -> set[str]:
    """Root identities in the immediately preceding persisted Raw basket.

    This continuity seed is Market history, not RIP eligibility. It prevents a
    post-cutover authority view from silently deleting a structurally valid root
    merely because same-day freshness policy differs between current and rollout
    rows.
    """
    if not before_date:
        return set()
    rows = list(
        client.table(MARKET_INDEX_HISTORY_TABLE)
        .select("constituents_json,market_date")
        .eq("tcg", "pokemon")
        .eq("methodology_version", MARKET_INDEX_METHODOLOGY_VERSION)
        .eq("index_key", "raw")
        .lt("market_date", str(before_date)[:10])
        .order("market_date", desc=True)
        .limit(1)
        .execute().data or []
    )
    if not rows:
        return set()
    return {
        str(item.get("setId") or item.get("set_id"))
        for item in (rows[0].get("constituents_json") or [])
        if item.get("setId") or item.get("set_id")
    }


def _load_set_metadata(client: Any, set_ids: Sequence[str]) -> dict[str, dict[str, Any]]:
    ids = sorted({str(value) for value in set_ids if value})
    if not ids:
        return {}
    rows: list[dict[str, Any]] = []
    for offset in range(0, len(ids), 100):
        rows.extend(
            dict(row)
            for row in (
                client.table("sets")
                .select(
                    "id,name,canonical_key,era_id,release_date,logo_image_url,"
                    "symbol_image_url,catalog_only,parent_opening_set_id"
                )
                .in_("id", ids[offset:offset + 100])
                .execute().data or []
            )
        )
    era_ids = sorted({str(row.get("era_id")) for row in rows if row.get("era_id")})
    era_names = {
        str(row.get("id")): str(row.get("name") or "")
        for row in (
            client.table("eras").select("id,name").in_("id", era_ids).execute().data or []
        )
    } if era_ids else {}
    return {
        str(row["id"]): {**row, "era": era_names.get(str(row.get("era_id")))}
        for row in rows
        if row.get("id")
    }


def _canonical_market_root_cohort(
    client: Any, *, market_date: str | None = None,
) -> list[dict[str, Any]]:
    """Post-cutover roots: the full canonical Standard root universe.

    MEMBERSHIP != CERTIFICATION. Every canonical Standard root set belongs to
    this cohort regardless of whether its Set Value / Top-10 certification is
    currently passing, stale or missing price identity — mirroring the same
    separation already enforced for the Pokemon Sets catalog
    (`pokemon_sets_catalog_service.py`) and the canonical set route directory
    (`20260909030411_decouple_pokemon_set_route_directory_from_rip_publication`).
    A set that fails certification simply carries that status forward as
    metadata (`market_publication_ready`, `market_structural_certified`,
    `market_current_certification_status`, price-freshness dates) so the Set
    Value publisher can render it honestly (current/stale/unavailable) instead
    of it silently vanishing from the Market page. Row-DROPPING on
    certification failure must never happen here again.
    """
    day = str(market_date)[:10] if market_date else None
    query = (
        client.table(MARKET_READY_VIEW)
        .select(MARKET_MEMBERSHIP_COLUMNS)
        .eq("market_scope", "standard")
    )
    if day:
        query = query.eq("canonical_market_date", day)
    universe_rows = [dict(row) for row in (query.order("release_date").execute().data or [])]
    universe_ids = {str(row.get("set_id")) for row in universe_rows if row.get("set_id")}
    if not universe_ids:
        raise RuntimeError(f"canonical Market root authority is empty for {day or 'current'}")

    certification_rows: list[dict[str, Any]] = []
    candidate_ids = sorted(universe_ids)
    for offset in range(0, len(candidate_ids), 100):
        cert_query = (
            client.table(MARKET_CERTIFICATION_VIEW)
            .select(MARKET_CERTIFICATION_COLUMNS)
            .eq("market_scope", "standard")
            .in_("set_id", candidate_ids[offset:offset + 100])
        )
        if day:
            cert_query = cert_query.eq("canonical_market_date", day)
        certification_rows.extend(dict(row) for row in (cert_query.execute().data or []))

    cert_by_id = {
        str(row.get("set_id")): row
        for row in certification_rows
        if row.get("set_id")
    }
    metadata_by_id = _load_set_metadata(client, candidate_ids)

    def structurally_certified(set_id: str) -> bool:
        cert = cert_by_id.get(set_id) or {}
        meta = metadata_by_id.get(set_id) or {}
        return (
            cert.get("set_value_certified") is True
            and cert.get("top10_certified") is True
            and cert.get("market_scope_certified") is True
            and meta.get("catalog_only") is not True
            and not meta.get("parent_opening_set_id")
        )

    universe_by_id = {
        str(row["set_id"]): row for row in universe_rows if row.get("set_id")
    }
    return [
        {
            "id": set_id,
            "name": (universe_by_id.get(set_id) or {}).get("set_name")
                    or (metadata_by_id.get(set_id) or {}).get("name"),
            "canonical_key": (universe_by_id.get(set_id) or {}).get("canonical_key")
                             or (metadata_by_id.get(set_id) or {}).get("canonical_key"),
            "era_id": (metadata_by_id.get(set_id) or {}).get("era_id"),
            "era": (universe_by_id.get(set_id) or {}).get("era_name")
                   or (metadata_by_id.get(set_id) or {}).get("era"),
            "release_date": (universe_by_id.get(set_id) or {}).get("release_date")
                            or (metadata_by_id.get(set_id) or {}).get("release_date"),
            "logo_image_url": (universe_by_id.get(set_id) or {}).get("logo_image_url")
                              or (metadata_by_id.get(set_id) or {}).get("logo_image_url"),
            "symbol_image_url": (universe_by_id.get(set_id) or {}).get("symbol_image_url")
                                or (metadata_by_id.get(set_id) or {}).get("symbol_image_url"),
            # Annotation only, never a membership filter from this point forward.
            "market_publication_ready": bool(
                (universe_by_id.get(set_id) or {}).get("market_publication_ready")
            ),
            "market_continuity_carried": False,
            "market_structural_certified": structurally_certified(set_id),
            "market_price_freshness_certified": bool(
                (cert_by_id.get(set_id) or {}).get("price_freshness_certified")
            ),
            "market_current_certification_status": (
                cert_by_id.get(set_id) or {}
            ).get("current_certification_status"),
            "market_oldest_component_price_date": (
                cert_by_id.get(set_id) or {}
            ).get("oldest_component_price_date"),
            "market_newest_component_price_date": (
                cert_by_id.get(set_id) or {}
            ).get("newest_component_price_date"),
            "market_coverage_pct": (cert_by_id.get(set_id) or {}).get("coverage_pct"),
            "canonical_market_date": (
                universe_by_id.get(set_id) or {}
            ).get("canonical_market_date") or (cert_by_id.get(set_id) or {}).get(
                "canonical_market_date"
            ),
        }
        for set_id in sorted(universe_ids)
    ]


def _authority_member_ids(client: Any, day: str) -> list[str]:
    """Membership-only read of the frozen authority table for market date ``day``.

    Deliberately selects only ``set_id`` plus the temporal columns needed to
    evaluate point-in-time membership -- no metadata/certification/era/logo
    joins. This is the lightweight query the quality resolver needs; it must
    never be widened to the heavyweight shape used by
    ``_authority_market_root_cohort``.
    """
    rows = list(
        client.table(MARKET_ROOT_AUTHORITY_TABLE)
        .select("set_id,activated_market_date,deactivated_market_date,enabled")
        .eq("enabled", True)
        .lte("activated_market_date", day)
        .execute().data or []
    )
    ids: set[str] = set()
    for row in rows:
        deactivated = row.get("deactivated_market_date")
        if deactivated and str(deactivated)[:10] <= day:
            continue
        if row.get("set_id"):
            ids.add(str(row["set_id"]))
    return sorted(ids)


def _authority_market_root_cohort(
    client: Any, *, market_date: str | None = None,
) -> list[dict[str, Any]]:
    """Sep 10+ roots: membership from the frozen authority table only.

    MEMBERSHIP != CERTIFICATION, same contract as ``_canonical_market_root_cohort``,
    except the membership id list itself comes from
    ``pokemon_market_root_authority`` instead of the certification-sensitive
    ``MARKET_READY_VIEW``. Certification/metadata are joined purely as
    annotation and never add or remove a member.
    """
    day = str(market_date)[:10] if market_date else MARKET_ROOT_AUTHORITY_TABLE_CUTOVER_DATE
    universe_ids = set(_authority_member_ids(client, day))
    if not universe_ids:
        raise RuntimeError(f"pokemon_market_root_authority has no active members for {day}")

    candidate_ids = sorted(universe_ids)
    universe_rows: list[dict[str, Any]] = []
    for offset in range(0, len(candidate_ids), 100):
        query = (
            client.table(MARKET_READY_VIEW)
            .select(MARKET_MEMBERSHIP_COLUMNS)
            .in_("set_id", candidate_ids[offset:offset + 100])
        )
        if day:
            query = query.eq("canonical_market_date", day)
        universe_rows.extend(dict(row) for row in (query.execute().data or []))

    certification_rows: list[dict[str, Any]] = []
    for offset in range(0, len(candidate_ids), 100):
        cert_query = (
            client.table(MARKET_CERTIFICATION_VIEW)
            .select(MARKET_CERTIFICATION_COLUMNS)
            .eq("market_scope", "standard")
            .in_("set_id", candidate_ids[offset:offset + 100])
        )
        if day:
            cert_query = cert_query.eq("canonical_market_date", day)
        certification_rows.extend(dict(row) for row in (cert_query.execute().data or []))

    cert_by_id = {
        str(row.get("set_id")): row
        for row in certification_rows
        if row.get("set_id")
    }
    metadata_by_id = _load_set_metadata(client, candidate_ids)
    universe_by_id = {
        str(row["set_id"]): row for row in universe_rows if row.get("set_id")
    }

    def structurally_certified(set_id: str) -> bool:
        cert = cert_by_id.get(set_id) or {}
        meta = metadata_by_id.get(set_id) or {}
        return (
            cert.get("set_value_certified") is True
            and cert.get("top10_certified") is True
            and cert.get("market_scope_certified") is True
            and meta.get("catalog_only") is not True
            and not meta.get("parent_opening_set_id")
        )

    return [
        {
            "id": set_id,
            "name": (universe_by_id.get(set_id) or {}).get("set_name")
                    or (metadata_by_id.get(set_id) or {}).get("name"),
            "canonical_key": (universe_by_id.get(set_id) or {}).get("canonical_key")
                             or (metadata_by_id.get(set_id) or {}).get("canonical_key"),
            "era_id": (metadata_by_id.get(set_id) or {}).get("era_id"),
            "era": (universe_by_id.get(set_id) or {}).get("era_name")
                   or (metadata_by_id.get(set_id) or {}).get("era"),
            "release_date": (universe_by_id.get(set_id) or {}).get("release_date")
                            or (metadata_by_id.get(set_id) or {}).get("release_date"),
            "logo_image_url": (universe_by_id.get(set_id) or {}).get("logo_image_url")
                              or (metadata_by_id.get(set_id) or {}).get("logo_image_url"),
            "symbol_image_url": (universe_by_id.get(set_id) or {}).get("symbol_image_url")
                                or (metadata_by_id.get(set_id) or {}).get("symbol_image_url"),
            # Annotation only. A stale/missing/failed certification NEVER
            # removes a set that the frozen authority table says is a member.
            "market_publication_ready": bool(
                (universe_by_id.get(set_id) or {}).get("market_publication_ready")
            ),
            "market_continuity_carried": False,
            "market_structural_certified": structurally_certified(set_id),
            "market_price_freshness_certified": bool(
                (cert_by_id.get(set_id) or {}).get("price_freshness_certified")
            ),
            "market_current_certification_status": (
                cert_by_id.get(set_id) or {}
            ).get("current_certification_status"),
            "market_oldest_component_price_date": (
                cert_by_id.get(set_id) or {}
            ).get("oldest_component_price_date"),
            "market_newest_component_price_date": (
                cert_by_id.get(set_id) or {}
            ).get("newest_component_price_date"),
            "market_coverage_pct": (cert_by_id.get(set_id) or {}).get("coverage_pct"),
            "canonical_market_date": (
                universe_by_id.get(set_id) or {}
            ).get("canonical_market_date") or (cert_by_id.get(set_id) or {}).get(
                "canonical_market_date"
            ),
            "market_root_authority_source": "pokemon_market_root_authority",
        }
        for set_id in sorted(universe_ids)
    ]


def resolve_market_root_cohort(client: Any, *, market_date: str | None = None) -> list[dict[str, Any]]:
    """One global Market root universe with an immutable historical boundary.

    Dates before 2026-09-09 reconstruct the exact staged basket that was
    actually published. 2026-09-09 resolves from canonical Market
    certification plus structurally valid prior-basket continuity, exactly as
    it was originally published -- this behavior is frozen and must not
    change. 2026-09-10 onward resolves membership from the frozen
    ``pokemon_market_root_authority`` table only; certification is annotation.
    """
    day = str(market_date)[:10] if market_date else None
    if day and day < MARKET_ROOT_AUTHORITY_CUTOVER_DATE:
        return _legacy_market_root_cohort(client, market_date=market_date)
    if day and day >= MARKET_ROOT_AUTHORITY_TABLE_CUTOVER_DATE:
        return _authority_market_root_cohort(client, market_date=market_date)
    return _canonical_market_root_cohort(client, market_date=market_date)


def resolve_market_root_ids(client: Any, *, market_date: str | None = None) -> list[str]:
    """Lightweight, membership-only resolver -- no metadata/certification joins.

    For 2026-09-10 onward this reads ONLY ``set_id`` from the frozen authority
    table, which is exactly the shape ``evaluate_market_date_quality`` needs
    and avoids the heavyweight metadata+certification+era joins performed by
    ``resolve_market_root_cohort``/``_canonical_market_root_cohort`` (the
    production statement-timeout risk this pass exists to remove). Earlier
    dates fall back to the full resolver, which is already the lightest
    membership path available for that history (a persisted-row lookup wins
    first in ``market_date_quality.cohort_set_ids_for_date``, so this fallback
    is rarely exercised pre-cutover).
    """
    day = str(market_date)[:10] if market_date else None
    if day and day >= MARKET_ROOT_AUTHORITY_TABLE_CUTOVER_DATE:
        return _authority_member_ids(client, day)
    return sorted(
        str(row["id"])
        for row in resolve_market_root_cohort(client, market_date=market_date)
        if row.get("id")
    )


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
