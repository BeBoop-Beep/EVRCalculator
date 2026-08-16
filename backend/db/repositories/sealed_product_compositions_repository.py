"""Persistence and reads for Stage 2 sealed-product compositions.

Reads return rows shaped for ``parse_composition_row``: the header with its pack
and guaranteed-card children attached. Writes are idempotent on
``(sealed_product_id, composition_version)`` - the same identity the table's
unique constraint enforces - so re-running composition ingestion updates the row
it already wrote instead of accumulating a second version of the same research.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from ..clients.supabase_client import supabase

COMPOSITIONS_TABLE = "sealed_product_compositions"
PACK_COMPONENTS_TABLE = "sealed_product_composition_pack_components"
CARD_COMPONENTS_TABLE = "sealed_product_composition_card_components"

COMPOSITION_UNIQUE_KEY = "sealed_product_id,composition_version"

STATUS_VERIFIED = "verified"

_HEADER_FIELDS = (
    "id,sealed_product_id,composition_version,status,source_type,source_reference,"
    "verified_at,notes,created_at,updated_at"
)


def _attach_children(headers: Sequence[Dict[str, Any]], client: Any) -> List[Dict[str, Any]]:
    """Attach pack and card components to header rows in TWO queries, not 2N.

    Composition reads happen once per set simulation, inside a job whose budget
    is dominated by the pack simulator - but a per-header round trip would still
    scale with catalogue size for no reason, and batching is not harder to read.
    """
    rows = [dict(header) for header in headers]
    if not rows:
        return []

    composition_ids = [str(row["id"]) for row in rows]

    pack_response = (
        client.table(PACK_COMPONENTS_TABLE)
        .select("composition_id,set_id,pack_count")
        .in_("composition_id", composition_ids)
        .execute()
    )
    card_response = (
        client.table(CARD_COMPONENTS_TABLE)
        .select("composition_id,card_variant_id,canonical_card_id,quantity,component_role")
        .in_("composition_id", composition_ids)
        .execute()
    )

    packs_by_composition: Dict[str, List[Dict[str, Any]]] = {}
    for pack in list(pack_response.data or []):
        packs_by_composition.setdefault(str(pack["composition_id"]), []).append(pack)

    cards_by_composition: Dict[str, List[Dict[str, Any]]] = {}
    for card in list(card_response.data or []):
        cards_by_composition.setdefault(str(card["composition_id"]), []).append(card)

    for row in rows:
        key = str(row["id"])
        row["packComponents"] = packs_by_composition.get(key, [])
        # Sorted by role so the guaranteed-component list is stable across reads;
        # an unstable order would make otherwise-identical audit payloads differ.
        row["guaranteedCardComponents"] = sorted(
            cards_by_composition.get(key, []),
            key=lambda component: str(component.get("component_role") or ""),
        )
    return rows


def get_verified_compositions_for_products(
    sealed_product_ids: Sequence[Any],
    *,
    client: Any = None,
) -> List[Dict[str, Any]]:
    """Every VERIFIED composition for an explicit list of SKUs.

    Only ``status = 'verified'`` is returned. Draft and rejected rows exist to
    record research honestly, and a read path that could surface them would make
    "recorded" and "approved for scoring" the same thing.
    """
    client = client or supabase
    ids = [str(value) for value in sealed_product_ids if value is not None]
    if not ids:
        return []

    response = (
        client.table(COMPOSITIONS_TABLE)
        .select(_HEADER_FIELDS)
        .in_("sealed_product_id", ids)
        .eq("status", STATUS_VERIFIED)
        .execute()
    )
    return _attach_children(list(response.data or []), client)


def get_verified_composition_for_product(
    sealed_product_id: Any,
    *,
    client: Any = None,
) -> Optional[Dict[str, Any]]:
    """The one verified composition for a SKU, or ``None``.

    "One" is guaranteed by a partial unique index on the table rather than by a
    tiebreak here: two verified compositions for a product is a data defect, and
    picking one would hide it.
    """
    rows = get_verified_compositions_for_products([sealed_product_id], client=client)
    return rows[0] if rows else None


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

def upsert_composition(
    *,
    sealed_product_id: Any,
    composition_version: str,
    status: str,
    source_type: str,
    source_reference: str,
    verified_at: Any,
    pack_components: Sequence[Dict[str, Any]],
    guaranteed_card_components: Sequence[Dict[str, Any]],
    notes: Optional[str] = None,
    client: Any = None,
) -> Dict[str, Any]:
    """Write one composition and REPLACE its component sets.

    Components are deleted and rewritten rather than upserted individually. A
    composition's component list is a closed statement about what is in the box:
    if research corrects "2 promos" to "1 promo", an upsert-only path would leave
    the removed promo behind and silently keep valuing it. Replacement makes the
    stored components equal to the asserted components, always.
    """
    client = client or supabase

    header = {
        "sealed_product_id": str(sealed_product_id),
        "composition_version": str(composition_version),
        "status": str(status),
        "source_type": str(source_type),
        "source_reference": str(source_reference),
        "verified_at": str(verified_at),
        "notes": notes,
    }
    response = (
        client.table(COMPOSITIONS_TABLE)
        .upsert(header, on_conflict=COMPOSITION_UNIQUE_KEY)
        .execute()
    )
    rows = list(response.data or [])
    if not rows:
        raise RuntimeError(
            f"composition upsert for sealed_product_id={sealed_product_id} returned no row."
        )
    composition_id = str(rows[0]["id"])

    client.table(PACK_COMPONENTS_TABLE).delete().eq("composition_id", composition_id).execute()
    client.table(CARD_COMPONENTS_TABLE).delete().eq("composition_id", composition_id).execute()

    if pack_components:
        client.table(PACK_COMPONENTS_TABLE).insert(
            [
                {
                    "composition_id": composition_id,
                    "set_id": str(component["set_id"]),
                    "pack_count": int(component["pack_count"]),
                }
                for component in pack_components
            ]
        ).execute()

    if guaranteed_card_components:
        client.table(CARD_COMPONENTS_TABLE).insert(
            [
                {
                    "composition_id": composition_id,
                    "card_variant_id": str(component["card_variant_id"]),
                    "canonical_card_id": (
                        str(component["canonical_card_id"])
                        if component.get("canonical_card_id")
                        else None
                    ),
                    "quantity": int(component.get("quantity", 1)),
                    "component_role": str(component["component_role"]),
                }
                for component in guaranteed_card_components
            ]
        ).execute()

    return {"composition_id": composition_id, **rows[0]}
