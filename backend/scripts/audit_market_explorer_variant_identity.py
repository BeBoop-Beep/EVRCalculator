"""Read-only production audit for Market Explorer canonical-to-variant identity.

Prints aggregate coverage and bounded examples. It never writes and never
prints database credentials.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict

from backend.db.clients.supabase_client import create_service_role_client


def _paged(client, table: str, columns: str, *, filters=(), size: int = 1000):
    rows, start = [], 0
    while True:
        query = client.table(table).select(columns).order(columns.split(",", 1)[0])
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
                              "canonical_card_id,card_variant_id,condition_id,market_price")

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
    }


if __name__ == "__main__":
    print(json.dumps(audit(create_service_role_client()), indent=2, sort_keys=True))
