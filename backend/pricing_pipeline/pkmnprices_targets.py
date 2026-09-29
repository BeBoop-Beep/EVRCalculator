"""Target discovery for PkmnPrices sold-evidence collection.

The vintage gap path intentionally derives targets from the same dated edition
history authority used by Set Market.  TCGplayer product identity may come from
an exact variant external identity or, when the approved edition basket points
at an auxiliary catalog variant, from the canonical card's uniquely identified
sibling variant.  Ambiguous product IDs fail closed before provider calls.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping, Sequence


SCOPE_EDITION = {
    "first_edition": "1st-edition",
    "shadowless": "shadowless",
    "unlimited": "unlimited",
}


class TargetResolutionError(RuntimeError):
    pass


def effective_edition(market_scope: str | None, fallback: Any = None) -> str | None:
    return SCOPE_EDITION.get(str(market_scope or ""), str(fallback or "").strip() or None)


def choose_product_id(
    direct_product_ids: Iterable[Any],
    sibling_product_ids: Iterable[Any],
) -> tuple[str, str]:
    direct = {str(value).strip() for value in direct_product_ids if str(value or "").strip()}
    sibling = {str(value).strip() for value in sibling_product_ids if str(value or "").strip()}
    if len(direct) > 1:
        raise TargetResolutionError(f"multiple direct TCGplayer product IDs: {sorted(direct)}")
    if direct:
        value = next(iter(direct))
        if sibling and any(other != value for other in sibling):
            raise TargetResolutionError(
                f"direct TCGplayer product ID {value} conflicts with canonical sibling IDs {sorted(sibling)}"
            )
        return value, "direct_variant_external_identity"
    if len(sibling) != 1:
        raise TargetResolutionError(
            "canonical sibling TCGplayer product identity is "
            + ("missing" if not sibling else f"ambiguous: {sorted(sibling)}")
        )
    return next(iter(sibling)), "canonical_sibling_tcgplayer_product_id"


def merge_variant_candidates(
    target_rows: Sequence[Mapping[str, Any]],
    metadata_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Build candidate physical variants; gap authority rows override generic metadata."""
    by_id: dict[str, dict[str, Any]] = {}
    for row in metadata_rows:
        variant_id = str(row.get("card_variant_id") or row.get("id") or "")
        if not variant_id:
            continue
        by_id[variant_id] = {
            "id": variant_id,
            "edition": str(row.get("edition") or "").strip() or None,
            "printing_type": str(row.get("printing_type") or "").strip() or None,
            "special_type": str(row.get("special_type") or "").strip() or None,
            "identity_basis": row.get("identity_basis") or "canonical_metadata",
        }
    for row in target_rows:
        variant_id = str(row.get("card_variant_id") or "")
        if not variant_id:
            continue
        by_id[variant_id] = {
            "id": variant_id,
            "edition": effective_edition(row.get("market_scope"), row.get("edition")),
            "printing_type": str(row.get("printing_type") or "").strip() or None,
            "special_type": str(row.get("special_type") or "").strip() or None,
            "identity_basis": row.get("identity_basis") or "dated_edition_gap_authority",
        }
    return sorted(by_id.values(), key=lambda row: row["id"])


def _paged(query_factory: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        page = list(query_factory().range(start, start + 999).execute().data or [])
        rows.extend(page)
        if len(page) < 1000:
            return rows
        start += 1000


def latest_approved_market_date(client: Any) -> str:
    rows = list(
        client.table("pokemon_market_date_quality")
        .select("market_date,status")
        .eq("tcg", "pokemon")
        .in_("status", ["READY", "LEGACY_VERIFIED"])
        .order("market_date", desc=True)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows:
        raise TargetResolutionError("no approved Pokémon market date")
    return str(rows[0]["market_date"])[:10]


def discover_vintage_gap_rows(client: Any, market_date: str) -> list[dict[str, Any]]:
    roots = _paged(
        lambda: client.table("pokemon_edition_split_root_sets_v2")
        .select("set_id")
        .order("set_id")
    )
    gaps: dict[str, dict[str, Any]] = {}
    for root in roots:
        root_id = str(root.get("set_id") or "")
        if not root_id:
            continue
        rows = list(
            client.rpc(
                "get_pokemon_edition_history_card_prices_as_of_v2",
                {
                    "p_root_set_id": root_id,
                    "p_market_date": market_date,
                    "p_raw_oracle": False,
                },
            ).execute().data
            or []
        )
        for row in rows:
            variant_id = str(row.get("card_variant_id") or "")
            if not variant_id or row.get("market_price") is not None:
                continue
            key = f"{variant_id}|{row.get('market_scope') or ''}"
            gaps[key] = {
                **dict(row),
                "root_set_id": root_id,
                "card_variant_id": variant_id,
                "canonical_card_id": str(row.get("canonical_card_id") or ""),
            }
    return sorted(
        gaps.values(),
        key=lambda row: (
            row["root_set_id"],
            str(row.get("market_scope") or ""),
            row["canonical_card_id"],
            row["card_variant_id"],
        ),
    )


def resolve_targets(
    client: Any,
    gap_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if not gap_rows:
        return []
    variant_ids = sorted({str(row["card_variant_id"]) for row in gap_rows})
    canonical_ids = sorted({str(row["canonical_card_id"]) for row in gap_rows if row.get("canonical_card_id")})
    if not canonical_ids:
        raise TargetResolutionError("gap rows have no canonical card identities")

    variants = _paged(
        lambda: client.table("card_variants")
        .select("id,card_id,edition,printing_type,special_type")
        .in_("id", variant_ids)
        .order("id")
    )
    variant_by = {str(row["id"]): row for row in variants}
    if set(variant_ids) != set(variant_by):
        missing = sorted(set(variant_ids) - set(variant_by))
        raise TargetResolutionError(f"gap variants missing from card_variants: {missing}")

    metadata = _paged(
        lambda: client.table("pokemon_market_explorer_card_current_metadata")
        .select("canonical_card_id,card_variant_id,set_id,edition,printing_type,special_type,identity_basis")
        .in_("canonical_card_id", canonical_ids)
        .order("canonical_card_id")
        .order("card_variant_id")
    )
    metadata_by_canonical: dict[str, list[dict[str, Any]]] = defaultdict(list)
    variant_to_canonical: dict[str, str] = {}
    for row in metadata:
        cid = str(row.get("canonical_card_id") or "")
        vid = str(row.get("card_variant_id") or "")
        if cid:
            metadata_by_canonical[cid].append(dict(row))
        if cid and vid:
            variant_to_canonical[vid] = cid

    candidate_variant_ids = sorted(
        set(variant_ids)
        | {str(row.get("card_variant_id")) for row in metadata if row.get("card_variant_id")}
    )
    external = _paged(
        lambda: client.table("card_variant_external_identities")
        .select("card_variant_id,provider,external_product_id,external_variant_key,external_catalog_key")
        .eq("provider", "tcgplayer")
        .in_("card_variant_id", candidate_variant_ids)
        .order("card_variant_id")
    )
    external_by_variant: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in external:
        external_by_variant[str(row["card_variant_id"])].append(dict(row))

    cards = _paged(
        lambda: client.table("pokemon_canonical_cards")
        .select("id,set_id,name,number,printed_number,rarity")
        .in_("id", canonical_ids)
        .order("id")
    )
    card_by = {str(row["id"]): dict(row) for row in cards}
    if set(canonical_ids) != set(card_by):
        missing = sorted(set(canonical_ids) - set(card_by))
        raise TargetResolutionError(f"canonical cards missing: {missing}")

    set_ids = sorted({str(row.get("set_id") or "") for row in cards if row.get("set_id")})
    sets = _paged(
        lambda: client.table("sets")
        .select("id,name,canonical_key")
        .in_("id", set_ids)
        .order("id")
    )
    set_by = {str(row["id"]): dict(row) for row in sets}

    by_canonical: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in gap_rows:
        row = dict(raw)
        vid = str(row["card_variant_id"])
        cid = str(row.get("canonical_card_id") or variant_to_canonical.get(vid) or "")
        if not cid:
            raise TargetResolutionError(f"no canonical card for gap variant {vid}")
        row["canonical_card_id"] = cid
        variant = variant_by[vid]
        row["edition"] = variant.get("edition")
        row["printing_type"] = variant.get("printing_type")
        row["special_type"] = variant.get("special_type")
        by_canonical[cid].append(row)

    resolved: list[dict[str, Any]] = []
    for cid, rows in sorted(by_canonical.items()):
        direct_ids = [
            identity.get("external_product_id")
            for row in rows
            for identity in external_by_variant.get(str(row["card_variant_id"]), [])
        ]
        sibling_variants = [
            str(row.get("card_variant_id"))
            for row in metadata_by_canonical.get(cid, [])
            if row.get("card_variant_id")
        ]
        sibling_ids = [
            identity.get("external_product_id")
            for vid in sibling_variants
            for identity in external_by_variant.get(vid, [])
        ]
        product_id, product_basis = choose_product_id(direct_ids, sibling_ids)
        candidates = merge_variant_candidates(rows, metadata_by_canonical.get(cid, []))
        card = card_by[cid]
        resolved.append(
            {
                "canonical_card_id": cid,
                "card_name": card.get("name"),
                "card_number": card.get("printed_number") or card.get("number"),
                "set_id": str(card.get("set_id") or ""),
                "set_name": (set_by.get(str(card.get("set_id") or "")) or {}).get("name"),
                "set_key": (set_by.get(str(card.get("set_id") or "")) or {}).get("canonical_key"),
                "tcgplayer_product_id": product_id,
                "product_identity_basis": product_basis,
                "gap_variants": [
                    {
                        "card_variant_id": str(row["card_variant_id"]),
                        "market_scope": row.get("market_scope"),
                        "effective_edition": effective_edition(row.get("market_scope"), row.get("edition")),
                        "printing_type": row.get("printing_type"),
                    }
                    for row in sorted(rows, key=lambda item: (str(item.get("market_scope")), str(item.get("card_variant_id"))))
                ],
                "variant_candidates": candidates,
            }
        )
    return resolved
