from __future__ import annotations

from ..clients.supabase_client import supabase, SUPABASE_URL, SUPABASE_KEY
from supabase import create_client
from postgrest.exceptions import APIError
from typing import Optional, Dict, Any, List, Set
import time
from backend.db.services.supabase_persistence_retry import run_supabase_with_transient_retry

BULK_READ_CHUNK_SIZE = 150
BULK_READ_PAGE_SIZE = 1000

class ExternalVariantIdentityConflict(RuntimeError):
    pass

class AmbiguousExternalVariantIdentity(RuntimeError):
    pass


def external_identity_key(provider: Any, external_product_id: Any,
                          external_variant_key: Any) -> tuple[str, str, str]:
    return (str(provider).strip().lower(), str(external_product_id).strip(),
            str(external_variant_key).strip())


def variant_natural_key(card_id: Any, printing_type: Any, special_type: Any,
                        edition: Any) -> tuple[str, Any, Any, Any]:
    return (str(card_id), printing_type, special_type, edition)


def _chunks(values: List[Any], size: int = BULK_READ_CHUNK_SIZE):
    for offset in range(0, len(values), size):
        yield values[offset:offset + size]


def get_card_variant_external_identities_bulk(
    provider: str, identity_pairs: List[tuple[Any, Any]],
) -> tuple[Dict[tuple[str, str, str], Dict[str, Any]], int]:
    """Load requested external identities in bounded product-id queries."""
    normalized_provider = str(provider).strip().lower()
    requested = {external_identity_key(normalized_provider, product_id, variant_key)
                 for product_id, variant_key in identity_pairs}
    product_ids = sorted({key[1] for key in requested})
    found: Dict[tuple[str, str, str], Dict[str, Any]] = {}
    operations = 0
    for chunk in _chunks(product_ids):
        def operation(client, _attempt):
            rows = []
            page = 0
            while True:
                start = page * BULK_READ_PAGE_SIZE
                page_rows = list((client.table("card_variant_external_identities")
                    .select("id,provider,external_product_id,external_variant_key,card_variant_id")
                    .eq("provider", normalized_provider).in_("external_product_id", chunk)
                    .order("id").range(start, start + BULK_READ_PAGE_SIZE - 1)
                    .execute()).data or [])
                rows.extend(page_rows)
                page += 1
                if len(page_rows) < BULK_READ_PAGE_SIZE:
                    return rows, page
        rows, page_operations = run_supabase_with_transient_retry(
            operation, operation_name="get_card_variant_external_identities_bulk")
        operations += page_operations
        for row in rows:
            key = external_identity_key(row.get("provider"), row.get("external_product_id"),
                                        row.get("external_variant_key"))
            if key not in requested:
                continue
            if key in found:
                raise AmbiguousExternalVariantIdentity(
                    f"{key[0]} product {key[1]} variant {key[2]} has duplicate identity rows")
            found[key] = dict(row)
    return found, operations


def get_card_variants_bulk(
    *, variant_ids: List[Any], card_ids: List[Any],
) -> tuple[Dict[str, Dict[str, Any]], Dict[tuple[str, Any, Any, Any], Dict[str, Any]], int]:
    """Load mapped variants and natural-key candidates with bounded reads."""
    by_id: Dict[str, Dict[str, Any]] = {}
    by_natural: Dict[tuple[str, Any, Any, Any], Dict[str, Any]] = {}
    operations = 0
    select = "id,card_id,printing_type,special_type,edition"
    for column, values in (("id", sorted({str(value) for value in variant_ids if value is not None})),
                           ("card_id", sorted({str(value) for value in card_ids if value is not None}))):
        for chunk in _chunks(values):
            def operation(client, _attempt, column=column, chunk=chunk):
                rows = []
                page = 0
                while True:
                    start = page * BULK_READ_PAGE_SIZE
                    page_rows = list((client.table("card_variants").select(select)
                        .in_(column, chunk).order("id")
                        .range(start, start + BULK_READ_PAGE_SIZE - 1)
                        .execute()).data or [])
                    rows.extend(page_rows)
                    page += 1
                    if len(page_rows) < BULK_READ_PAGE_SIZE:
                        return rows, page
            rows, page_operations = run_supabase_with_transient_retry(
                operation, operation_name=f"get_card_variants_bulk_by_{column}")
            operations += page_operations
            for row in rows:
                normalized = dict(row)
                by_id[str(row["id"])] = normalized
                key = variant_natural_key(row.get("card_id"), row.get("printing_type"),
                                          row.get("special_type"), row.get("edition"))
                existing = by_natural.get(key)
                if existing and str(existing["id"]) != str(row["id"]):
                    raise ExternalVariantIdentityConflict(f"duplicate card variant natural key: {key}")
                by_natural[key] = normalized
    return by_id, by_natural, operations

def get_card_variant_external_identity(provider: str, external_product_id: str,
                                       external_variant_key: Optional[str] = None):
    def operation(client, _attempt):
        query = (client.table("card_variant_external_identities").select("*")
                 .eq("provider", provider.strip().lower())
                 .eq("external_product_id", str(external_product_id)))
        if external_variant_key is not None:
            query = query.eq("external_variant_key", external_variant_key)
        rows = query.limit(2).execute().data or []
        if len(rows) > 1:
            raise AmbiguousExternalVariantIdentity(
                f"{provider} product {external_product_id} has multiple source variants")
        return rows[0] if rows else None
    return run_supabase_with_transient_retry(operation, operation_name="get_card_variant_external_identity")

def link_card_variant_external_identity(card_variant_id: str, identity: Dict[str, Any], *,
                                        known_absent: bool = False) -> str:
    """Idempotently link a provider product, refusing identity reassignment."""
    provider = str(identity["provider"]).strip().lower()
    product_id = str(identity["external_product_id"]).strip()
    variant_key = str(identity["external_variant_key"]).strip()
    existing = None if known_absent else get_card_variant_external_identity(provider, product_id, variant_key)
    if existing:
        if str(existing["card_variant_id"]) != str(card_variant_id):
            raise ExternalVariantIdentityConflict(
                f"{provider} product {product_id} is already linked to variant {existing['card_variant_id']}, not {card_variant_id}")
        return existing["id"]
    payload = {**identity, "provider": provider, "external_product_id": product_id,
               "card_variant_id": card_variant_id}
    def operation(client, attempt):
        if attempt > 1:
            reconciled = get_card_variant_external_identity(provider, product_id, variant_key)
            if reconciled:
                if str(reconciled["card_variant_id"]) != str(card_variant_id):
                    raise ExternalVariantIdentityConflict(
                        f"{provider} product {product_id} concurrently linked to variant {reconciled['card_variant_id']}")
                return reconciled["id"]
        try:
            res = client.table("card_variant_external_identities").insert(payload).execute()
            return res.data[0]["id"]
        except APIError:
            reconciled = get_card_variant_external_identity(provider, product_id, variant_key)
            if reconciled and str(reconciled["card_variant_id"]) == str(card_variant_id):
                return reconciled["id"]
            if reconciled:
                raise ExternalVariantIdentityConflict(
                    f"{provider} product {product_id} concurrently linked to variant {reconciled['card_variant_id']}")
            raise
    return run_supabase_with_transient_retry(operation, operation_name="link_card_variant_external_identity")


def insert_card_variant(card_variant_row: Dict[str, Any]) -> int:
    """
    Insert a card variant row into `card_variants` and return the new id.
    
    Args:
        card_variant_row: Should include card_id, printing_type, special_type (optional), edition (optional)
        
    Returns:
        The id of the newly inserted card variant
        
    Raises:
        RuntimeError: If insertion fails
    """
    def operation(client, attempt):
        if attempt > 1:
            existing = get_card_variant_by_card_and_type(
                card_variant_row["card_id"], card_variant_row["printing_type"],
                card_variant_row.get("special_type"), card_variant_row.get("edition"))
            if existing:
                return existing["id"]
        res = client.table("card_variants").insert(card_variant_row).execute()
        if res is None or not res.data:
            raise RuntimeError("Insert card variant returned no data")
        return res.data[0]["id"]
    return run_supabase_with_transient_retry(operation, operation_name="insert_card_variant")


def get_card_variant_by_card_and_type(
    card_id: int, 
    printing_type: str, 
    special_type: Optional[str] = None,
    edition: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Retrieve a card variant by card_id and printing characteristics.
    
    Args:
        card_id: The ID of the card
        printing_type: The printing type (e.g., 'holo', 'reverse-holo', 'non-holo')
        special_type: Optional special type (e.g., 'ex', 'v', 'vmax')
        edition: Optional edition info
        
    Returns:
        The card variant record, or None if not found
    """
    def operation(client, _attempt):
        query = (
            client.table("card_variants")
            .select("*")
            .eq("card_id", card_id)
            .eq("printing_type", printing_type)
        )

        if special_type is not None:
            query = query.eq("special_type", special_type)
        else:
            query = query.is_("special_type", "null")

        if edition is not None:
            query = query.eq("edition", edition)
        else:
            query = query.is_("edition", "null")

        res = query.maybe_single().execute()
        return res.data if res and res.data else None
    return run_supabase_with_transient_retry(operation, operation_name="get_card_variant_by_card_and_type")


def get_card_variant_by_id(card_variant_id: str) -> Optional[Dict[str, Any]]:
    def operation(client, _attempt):
        res = (client.table("card_variants").select("*")
               .eq("id", card_variant_id).maybe_single().execute())
        return res.data if res and res.data else None
    return run_supabase_with_transient_retry(operation, operation_name="get_card_variant_by_id")


def get_card_variants_by_card_id(card_id: int) -> List[Dict[str, Any]]:
    """
    Retrieve all card variants for a given card.
    
    Args:
        card_id: The ID of the card
        
    Returns:
        List of card variant records
    """
    res = supabase.table("card_variants").select("*").eq("card_id", card_id).execute()
    return res.data if res and res.data else []


def get_card_variants_by_card_ids(card_ids: List[int]) -> List[Dict[str, Any]]:
    """Retrieve all card variants for a list of card IDs."""
    if not card_ids:
        return []

    res = (
        supabase.table("card_variants")
        .select(
            "id, card_id, pokemon_tcg_api_id, printing_type, special_type, edition, image_small_url, image_large_url"
        )
        .in_("card_id", card_ids)
        .execute()
    )
    return res.data if res and res.data else []


def load_active_simulation_excluded_variant_ids(client) -> Set[str]:
    result = (
        client.table("simulation_card_variant_exclusions")
        .select("card_variant_id")
        .eq("active", True)
        .execute()
    )
    return {
        str(row["card_variant_id"])
        for row in (result.data or [])
        if row.get("card_variant_id")
    }


def update_card_variant_image_sync_fields(card_id: str, update_fields: Dict[str, Any]) -> Dict[str, Any]:
    """Update card image sync fields for a single card variant."""
    payload = {
        key: value
        for key, value in update_fields.items()
        if key in {"pokemon_tcg_api_id", "image_small_url", "image_large_url", "image_last_synced_at"}
        and value is not None
    }

    if not payload:
        raise ValueError("No non-null card variant sync fields were provided")

    max_retries = 3
    last_error = None

    for attempt in range(max_retries):
        try:
            fresh_client = create_client(SUPABASE_URL, SUPABASE_KEY)
            res = (
                fresh_client.table("card_variants")
                .update(payload)
                .eq("id", card_id)
                .execute()
            )
            if res is None:
                raise RuntimeError("Update card variant returned no response object")
            updated = res.data
            if not updated:
                raise RuntimeError(f"Update returned no data for card_id={card_id}")
            return updated[0]
        except APIError as e:
            error_msg = str(e)
            last_error = error_msg
            duplicate_api_id_conflict = (
                "23505" in error_msg
                and "card_variants_pokemon_tcg_api_id_key" in error_msg
                and "pokemon_tcg_api_id" in payload
            )

            if duplicate_api_id_conflict:
                fallback_payload = {k: v for k, v in payload.items() if k != "pokemon_tcg_api_id"}
                if fallback_payload:
                    try:
                        fallback_res = (
                            fresh_client.table("card_variants")
                            .update(fallback_payload)
                            .eq("id", card_id)
                            .execute()
                        )
                        if fallback_res and fallback_res.data:
                            return fallback_res.data[0]
                    except Exception:
                        # Fall through to the regular error path below.
                        pass

            if "schema cache" in error_msg.lower() and attempt < max_retries - 1:
                print(f"[WARN]  Schema cache error on attempt {attempt + 1}/{max_retries}, retrying...")
                time.sleep(1)
                continue
            raise RuntimeError(f"Failed to update card variant sync fields: {error_msg}")
        except RuntimeError as e:
            last_error = str(e)
            if "schema cache" in str(e).lower() and attempt < max_retries - 1:
                time.sleep(1)
                continue
            raise

    raise RuntimeError(f"Failed to update card variant after {max_retries} retries: {last_error}")


def update_card_variant_image_sync_fields_batch(updates: List[Dict[str, Any]]) -> int:
    """Apply card image sync field updates sequentially and return the number of updated rows."""
    updated_count = 0

    for update in updates:
        card_id = update.get("card_id")
        if not card_id:
            raise ValueError("Each card sync update must include card_id")

        payload = {key: value for key, value in update.items() if key != "card_id"}
        update_card_variant_image_sync_fields(card_id, payload)
        updated_count += 1

    return updated_count


def insert_card_variants_batch(card_variants: List[Dict[str, Any]]) -> List[int]:
    """
    Insert multiple card variant rows in a single batch operation.
    
    Args:
        card_variants: List of card variant dictionaries to insert
        
    Returns:
        List of IDs of the newly inserted card variants
        
    Raises:
        RuntimeError: If insertion fails
    """
    if not card_variants:
        return []
    
    max_retries = 3
    last_error = None
    
    for attempt in range(max_retries):
        try:
            fresh_client = create_client(SUPABASE_URL, SUPABASE_KEY)
            print(f"[DEBUG] insert_card_variants_batch -> card_variants | count={len(card_variants)}")
            res = fresh_client.table("card_variants").insert(card_variants).execute()
            
            if res is None:
                raise RuntimeError("Batch insert card variants returned no response object")
            
            inserted = res.data
            if not inserted:
                raise RuntimeError("Batch insert returned no data")
            
            # Return list of IDs
            return [item["id"] for item in inserted]
        
        except APIError as e:
            error_msg = str(e)
            last_error = error_msg
            if "schema cache" in error_msg.lower():
                print(f"[WARN]  Schema cache error on batch insert attempt {attempt + 1}/{max_retries}, retrying...")
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
            else:
                raise RuntimeError(f"Failed to batch insert card variants: {error_msg}")
        except RuntimeError as e:
            last_error = str(e)
            if "schema cache" in str(e).lower() and attempt < max_retries - 1:
                time.sleep(1)
                continue
            raise
    
    raise RuntimeError(f"Failed to batch insert card variants after {max_retries} retries: {last_error}")

