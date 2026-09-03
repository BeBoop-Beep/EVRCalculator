"""Read-only production audit for Market Explorer canonical-to-variant identity.

Prints aggregate coverage and bounded examples. It never writes and never
prints database credentials.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from backend.db.clients.supabase_client import create_service_role_client

# The identity-drift diagnostic only needs recent history to compare
# selected-vs-raw freshness; a full-table scan of price observations is
# both unbounded and (at this table's size) non-reproducible under
# offset pagination. Mirrors CARD_MOVEMENT_LOOKBACK_DAYS /
# CARD_MOVERS_HISTORY_LOOKBACK_DAYS used elsewhere in this codebase.
IDENTITY_DRIFT_LOOKBACK_DAYS = 45

# card_variant_price_observations' indexes both lead with card_variant_id,
# so any read of this (very large) table must constrain card_variant_id to
# be index-supported -- an unconstrained condition_id/captured_at filter
# still forces a sequential scan under growing OFFSET pagination. Mirrors
# CARD_PRICE_OBSERVATION_CHUNK_SIZE / _chunks() in pokemon_snapshot_builders.py.
IDENTITY_DRIFT_VARIANT_CHUNK_SIZE = 100


def _chunks(values, size):
    values = list(values)
    for index in range(0, len(values), size):
        yield values[index : index + size]


def _paged(client, table: str, columns: str, *, filters=(), size: int = 1000):
    rows, start = [], 0
    order_key = columns.split(",", 1)[0]
    while True:
        query = client.table(table).select(columns).order(order_key)
        for method, field, value in filters:
            query = getattr(query, method)(field, value)
        page = list(query.range(start, start + size - 1).execute().data or [])
        rows.extend(page)
        if len(page) < size:
            return rows
        start += size


def _fold(value):
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _number(value):
    return re.sub(r"^0+", "", str(value or "").split("/", 1)[0].lower())


def _compute_canonical_price_identity_drift(
    *, set_id, canonical_key, selected_rows, raw_observation_rows,
):
    """Flag sets where the canonical selected-price layer is stale even
    though raw Near Mint USD observations are current. Read-only; does
    not auto-link or mutate anything.

    Modeled on the Nintendo Black Star Promos incident: raw TCGPlayer
    observations were current, canonical selected-price rows existed, but
    none of the currently-selected variant identities reached the fresh
    date because a fresh replacement identity existed but wasn't linked
    into the canonical selection.

    Limitation: both dates are set-wide maxima, so one fresh canonical
    card in a set suppresses the flag for the whole set -- this catches
    set-wide drift only, not per-card drift. An empty result does not
    mean no card in the set is stale.
    """
    if not selected_rows:
        return []

    def _latest_date(rows):
        dates = [_fold(row.get("captured_at"))[:10] for row in rows if row.get("captured_at")]
        return max(dates) if dates else None

    selected_latest = _latest_date(selected_rows)
    raw_latest = _latest_date(raw_observation_rows)
    if not selected_latest or not raw_latest or selected_latest >= raw_latest:
        return []

    return [{
        "setId": set_id,
        "canonicalKey": canonical_key,
        "selectedLatestDate": selected_latest,
        "rawLatestDate": raw_latest,
        "selectedRowCount": len(selected_rows),
        "rawIdentityCount": len({row.get("card_variant_id") for row in raw_observation_rows}),
    }]


def audit(client):
    canonical = _paged(client, "pokemon_canonical_cards",
                       "id,set_id,name,number,printed_number,pokemon_tcg_api_card_id,rarity")
    links = _paged(client, "pokemon_canonical_card_legacy_identity_links",
                   "canonical_card_id,legacy_card_id,match_basis,confidence")
    cards = _paged(client, "cards", "id,set_id,name,card_number,pokemon_tcg_api_id")
    variants = _paged(client, "card_variants",
                      "id,card_id,edition,printing_type,special_type,pokemon_tcg_api_id")
    sets = _paged(client, "sets", "id,name,era_id,release_date")
    eras = _paged(client, "eras", "id,name")
    subject_links = _paged(client, "pokemon_card_desirability_links",
                           "pokemon_canonical_card_id,pokemon_reference_id")
    references = _paged(client, "pokemon_reference", "id,display_name")
    conditions = _paged(client, "conditions", "id,name,abbreviation")
    nm = next(row for row in conditions
              if _fold(row.get("name")) == "near mint" and str(row.get("abbreviation") or "").upper() == "NM")
    canonical_latest = _paged(client, "pokemon_canonical_card_market_prices_latest",
                              "canonical_card_id,set_id,card_variant_id,condition_id,market_price,captured_at")
    drift_lookback_start = (
        datetime.now(timezone.utc) - timedelta(days=IDENTITY_DRIFT_LOOKBACK_DAYS)
    ).date().isoformat()

    cards_by_id = {str(row["id"]): row for row in cards}
    sets_by_id = {str(row["id"]): row.get("name") for row in sets}
    set_rows_by_id = {str(row["id"]): row for row in sets}
    eras_by_id = {str(row["id"]): row.get("name") for row in eras}
    reference_names = {str(row["id"]): row.get("display_name") for row in references}
    subjects_by_card = defaultdict(list)
    for row in subject_links:
        subjects_by_card[str(row["pokemon_canonical_card_id"])].append(
            reference_names.get(str(row["pokemon_reference_id"]), str(row["pokemon_reference_id"])))
    variants_by_card = defaultdict(list)
    variants_by_api = defaultdict(list)
    for row in variants:
        variants_by_card[str(row.get("card_id"))].append(row)
        if row.get("pokemon_tcg_api_id"):
            card = cards_by_id.get(str(row.get("card_id"))) or {}
            variants_by_api[(str(card.get("set_id")), str(row["pokemon_tcg_api_id"]))].append(str(row["card_id"]))
    explicit = defaultdict(list)
    for row in links:
        explicit[str(row["canonical_card_id"])].append(str(row["legacy_card_id"]))
    parent_api = defaultdict(list)
    name_number = defaultdict(list)
    for row in cards:
        if row.get("pokemon_tcg_api_id"):
            parent_api[(str(row["set_id"]), str(row["pokemon_tcg_api_id"]))].append(str(row["id"]))
        name_number[(str(row["set_id"]), _fold(row.get("name")), _number(row.get("card_number")))].append(str(row["id"]))

    resolved, basis, ambiguous = {}, {}, {}
    for row in canonical:
        cid, set_id, api_id = str(row["id"]), str(row["set_id"]), str(row.get("pokemon_tcg_api_card_id") or "")
        options = [
            ("explicit_legacy_identity_link", explicit.get(cid, [])),
            ("parent_pokemon_tcg_api_id", parent_api.get((set_id, api_id), [])),
            ("variant_pokemon_tcg_api_id", variants_by_api.get((set_id, api_id), [])),
        ]
        fallback = set()
        for number in {_number(row.get("number")), _number(row.get("printed_number"))} - {""}:
            fallback.update(name_number.get((set_id, _fold(row.get("name")), number), []))
        options.append(("normalized_name_number_fallback", sorted(fallback)))
        for label, ids in options:
            unique = sorted(set(ids))
            if unique:
                resolved[cid], basis[cid] = unique[0], label
                if len(unique) > 1:
                    ambiguous[cid] = {"basis": label, "candidateCount": len(unique)}
                break

    canonical_latest_variants = {str(row["card_variant_id"]) for row in canonical_latest
                                 if str(row.get("condition_id")) == str(nm["id"])}
    current_price_by_card = {}
    for row in canonical_latest:
        if str(row.get("condition_id")) == str(nm["id"]) and row.get("market_price") is not None:
            cid = str(row["canonical_card_id"])
            current_price_by_card[cid] = max(float(row["market_price"]), current_price_by_card.get(cid, 0.0))
    mapped_variants = [variant for cid, card_id in resolved.items()
                       for variant in variants_by_card.get(card_id, [])]
    variant_counts = Counter(resolved_cid for resolved_cid, card_id in resolved.items()
                             for _ in variants_by_card.get(card_id, []))
    canonical_by_id = {str(row["id"]): row for row in canonical}

    def has_nm_history(variant_id):
        rows = (client.table("card_variant_price_observations").select("id")
                .eq("card_variant_id", variant_id).eq("condition_id", nm["id"])
                .gt("market_price", 0).limit(1).execute().data or [])
        return bool(rows)

    def example(cid):
        card = canonical_by_id[cid]
        legacy = cards_by_id[resolved[cid]]
        return {
            "canonicalCard": {"id": cid, "name": card.get("name"), "number": card.get("number"),
                              "set": sets_by_id.get(str(card.get("set_id")))},
            "legacyCardId": resolved[cid], "identityBasis": basis[cid],
            "variants": [{"cardVariantId": str(v["id"]), "edition": v.get("edition"),
                          "printingType": v.get("printing_type"), "specialType": v.get("special_type"),
                          "hasNearMintPriceHistory": has_nm_history(str(v["id"]))}
                         for v in variants_by_card.get(str(legacy["id"]), [])],
        }

    candidate_ids = [cid for cid in resolved]
    requested = []
    predicates = [
        lambda c: "dragonite" in _fold(c.get("name")) and "expedition" in _fold(sets_by_id.get(str(c.get("set_id")))),
        lambda c: _fold(c.get("name")).startswith("dragonite ex"),
        lambda c: any(_fold(v.get("edition")) in {"first", "1st-edition"} for v in variants_by_card.get(resolved.get(str(c["id"]), ""), []))
                  and any(_fold(v.get("edition")) == "unlimited" for v in variants_by_card.get(resolved.get(str(c["id"]), ""), [])),
        lambda c: any("reverse" in _fold(v.get("printing_type")) for v in variants_by_card.get(resolved.get(str(c["id"]), ""), [])),
    ]
    for predicate in predicates:
        match = next((str(c["id"]) for c in canonical if str(c["id"]) in resolved and predicate(c)), None)
        if match and match not in requested:
            requested.append(match)

    total = len(canonical)
    canonical_latest_count = sum(str(v["id"]) in canonical_latest_variants for v in mapped_variants)
    def debt_row(cid, classification):
        card = canonical_by_id[cid]
        set_row = set_rows_by_id.get(str(card.get("set_id"))) or {}
        mapped = variants_by_card.get(resolved.get(cid, ""), [])
        name = str(card.get("name") or "")
        return {"classification": classification, "canonicalCardId": cid,
                "cardName": name, "cardNumber": card.get("number"), "rarity": card.get("rarity"),
                "setId": card.get("set_id"), "setName": set_row.get("name"),
                "eraId": set_row.get("era_id"), "eraName": eras_by_id.get(str(set_row.get("era_id"))),
                "currentPrice": current_price_by_card.get(cid),
                "firstEdition": any(_fold(v.get("edition")) in {"first", "1st-edition"} for v in mapped),
                "unlimited": any(_fold(v.get("edition")) == "unlimited" for v in mapped),
                "pokemonSubjects": sorted(set(subjects_by_card.get(cid, []))),
                "namedImpact": next((key for key in ("dragonite", "charizard", "pikachu")
                                     if key in _fold(name)), None)}

    canonical_latest_by_set = defaultdict(list)
    for row in canonical_latest:
        if str(row.get("condition_id")) == str(nm["id"]):
            canonical_latest_by_set[str(row.get("set_id"))].append(row)
    set_variant_ids = defaultdict(set)
    for row in canonical:
        legacy_card_id = resolved.get(str(row["id"]))
        if not legacy_card_id:
            continue
        for variant in variants_by_card.get(legacy_card_id, []):
            set_variant_ids[str(row["set_id"])].add(str(variant["id"]))

    # Chunk the union of all resolved variant ids and query
    # card_variant_price_observations with card_variant_id IN (chunk) --
    # index-supported (leads with card_variant_id) and still date-bounded,
    # instead of an unconstrained sequential scan under OFFSET pagination.
    all_variant_ids = sorted({vid for ids in set_variant_ids.values() for vid in ids})
    raw_nm_observations = []
    for variant_chunk in _chunks(all_variant_ids, IDENTITY_DRIFT_VARIANT_CHUNK_SIZE):
        raw_nm_observations.extend(_paged(
            client, "card_variant_price_observations",
            "id,card_variant_id,condition_id,captured_at,market_price",
            filters=(("in_", "card_variant_id", variant_chunk),
                     ("eq", "condition_id", nm["id"]),
                     ("gte", "captured_at", drift_lookback_start)),
        ))
    raw_nm_by_variant = defaultdict(list)
    for row in raw_nm_observations:
        raw_nm_by_variant[str(row.get("card_variant_id"))].append(row)
    canonical_price_identity_drift = []
    for set_id, variant_ids in set_variant_ids.items():
        raw_rows = [obs for vid in variant_ids for obs in raw_nm_by_variant.get(vid, [])]
        canonical_price_identity_drift.extend(_compute_canonical_price_identity_drift(
            set_id=set_id, canonical_key=sets_by_id.get(set_id) or set_id,
            selected_rows=canonical_latest_by_set.get(set_id, []),
            raw_observation_rows=raw_rows,
        ))

    unresolved_ids = sorted(set(canonical_by_id) - set(resolved))
    debt = [debt_row(cid, "unresolved") for cid in unresolved_ids]
    debt.extend(debt_row(cid, "ambiguous") for cid in sorted(ambiguous))
    top_debt = sorted(debt, key=lambda row: (-(row.get("currentPrice") or 0), row["cardName"]))[:25]
    return {
        "nearMintAuthority": {"conditionName": nm["name"], "abbreviation": nm["abbreviation"]},
        "coverage": {
            "canonicalCards": total, "resolvedCanonicalCards": len(resolved),
            "resolvedCanonicalPct": round(100 * len(resolved) / total, 3) if total else 0,
            "unresolvedCanonicalCards": total - len(resolved),
            "identityBasis": dict(Counter(basis.values())),
            "ambiguousWinningMappings": len(ambiguous),
            "mappedVariants": len(mapped_variants),
            "multiVariantCanonicalCards": sum(count > 1 for count in variant_counts.values()),
            "mappedVariantsSelectedByCanonicalLatestLayer": canonical_latest_count,
            "note": "This selected-variant count is not full variant price coverage; the existing canonical latest layer intentionally selects one variant per canonical card.",
        },
        "variantMetadata": {
            "edition": dict(Counter(str(v.get("edition") or "(null)") for v in mapped_variants)),
            "printingType": dict(Counter(str(v.get("printing_type") or "(null)") for v in mapped_variants)),
            "specialType": dict(Counter(str(v.get("special_type") or "(null)") for v in mapped_variants)),
        },
        "mappingDebt": {
            "unresolvedCount": len(unresolved_ids), "ambiguousCount": len(ambiguous),
            "marketValueRepresented": round(sum(row.get("currentPrice") or 0 for row in debt), 2),
            "namedCounts": {name: sum(row.get("namedImpact") == name for row in debt)
                            for name in ("dragonite", "charizard", "pikachu")},
            "firstEditionCount": sum(bool(row.get("firstEdition")) for row in debt),
            "unlimitedCount": sum(bool(row.get("unlimited")) for row in debt),
            "top25": top_debt,
        },
        "examples": [example(cid) for cid in requested],
        "canonicalPriceIdentityDrift": canonical_price_identity_drift,
    }


if __name__ == "__main__":
    print(json.dumps(audit(create_service_role_client()), indent=2, sort_keys=True))
