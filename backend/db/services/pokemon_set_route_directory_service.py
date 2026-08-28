"""Lightweight routing authority for Pokemon set-detail routes.

This deliberately reads narrow relational columns from the canonical RIP view;
it never reads or trims the multi-megabyte Rankings publication JSON.
"""

from typing import Any, Dict

from backend.db.clients.supabase_client import service_read_client


ROUTE_DIRECTORY_COLUMNS = (
    "set_id,set_name,canonical_key,run_at,pack_score,relative_pack_score,"
    "pack_rank,pack_tier,ranked_set_count,pack_score_is_placeholder"
)


def get_pokemon_set_route_directory_payload(limit: int = 150) -> Dict[str, Any]:
    resolved_limit = max(1, min(int(limit or 150), 200))
    try:
        projected = list(
            service_read_client.rpc(
                "get_pokemon_set_route_directory", {"p_limit": resolved_limit}
            ).execute().data
            or []
        )
    except Exception:
        projected = []
    if projected:
        targets = [
            {
                "target_type": "set",
                "target_id": str(row.get("target_id") or ""),
                "setId": str(row.get("target_id") or ""),
                "name": row.get("name"),
                "canonical_key": row.get("canonical_key"),
                "slug": row.get("canonical_key"),
                "release_date": row.get("release_date"),
                "pokemon_api_set_id": row.get("pokemon_api_set_id"),
                "logo_image_url": row.get("logo_image_url"),
                "symbol_image_url": row.get("symbol_image_url"),
                "hero_image_url": row.get("hero_image_url"),
                "era": row.get("era"),
                "pack_score": row.get("pack_score"),
                "relative_pack_score": row.get("relative_pack_score"),
                "pack_rank": row.get("pack_rank"),
                "pack_tier": row.get("pack_tier"),
                "ranked_set_count": row.get("ranked_set_count"),
            }
            for row in projected
        ]
        return {
            "targets": targets,
            "default_target": targets[0] if targets else None,
            "meta": {
                "source": "get_pokemon_set_route_directory",
                "contract": "pokemon-set-route-directory-v1",
                "count": len(targets),
            },
        }

    # Deployment-safe fallback while the additive RPC migration rolls out.
    rows = list(
        (
            service_read_client.table("explore_rip_statistics_latest")
            .select(ROUTE_DIRECTORY_COLUMNS)
            .limit(resolved_limit)
            .execute()
        ).data
        or []
    )
    rows.sort(
        key=lambda row: (
            1 if row.get("pack_score_is_placeholder") else 0,
            -(float(row["pack_score"]) if row.get("pack_score") is not None else float("-inf")),
            str(row.get("run_at") or ""),
        )
    )
    set_ids = [str(row["set_id"]) for row in rows if row.get("set_id")]
    identity_by_id = {}
    if set_ids:
        identities = list(
            (
                service_read_client.table("sets")
                .select(
                    "id,name,canonical_key,release_date,pokemon_api_set_id,era_id,"
                    "logo_image_url,symbol_image_url,hero_image_url"
                )
                .in_("id", set_ids)
                .execute()
            ).data
            or []
        )
        era_ids = sorted({str(row["era_id"]) for row in identities if row.get("era_id")})
        eras_by_id = {}
        if era_ids:
            eras = list(
                service_read_client.table("eras")
                .select("id,name,canonical_key,sort_order")
                .in_("id", era_ids)
                .execute()
                .data
                or []
            )
            eras_by_id = {str(row["id"]): row for row in eras}
        identity_by_id = {str(row["id"]): {**row, "era": eras_by_id.get(str(row.get("era_id")))} for row in identities}

    targets = []
    for row in rows:
        set_id = str(row.get("set_id") or "")
        identity = identity_by_id.get(set_id, {})
        target = {
            "target_type": "set",
            "target_id": set_id,
            "setId": set_id,
            "name": identity.get("name") or row.get("set_name"),
            "canonical_key": identity.get("canonical_key") or row.get("canonical_key"),
            "release_date": identity.get("release_date"),
            "pokemon_api_set_id": identity.get("pokemon_api_set_id"),
            "logo_image_url": identity.get("logo_image_url"),
            "symbol_image_url": identity.get("symbol_image_url"),
            "hero_image_url": identity.get("hero_image_url"),
            "slug": identity.get("canonical_key") or row.get("canonical_key"),
            "era": (identity.get("era") or {}).get("name"),
            "pack_score": row.get("pack_score"),
            "relative_pack_score": row.get("relative_pack_score"),
            "pack_rank": row.get("pack_rank"),
            "pack_tier": row.get("pack_tier"),
            "ranked_set_count": row.get("ranked_set_count"),
        }
        targets.append(target)

    return {
        "targets": targets,
        "default_target": targets[0] if targets else None,
        "meta": {
            "source": "explore_rip_statistics_latest+sets+eras",
            "contract": "pokemon-set-route-directory-v1",
            "count": len(targets),
        },
    }
