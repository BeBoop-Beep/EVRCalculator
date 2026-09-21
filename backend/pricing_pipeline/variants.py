"""Deterministic default-variant resolution for cards with no TCGplayer NM price.

Mirrors the canonical resolver's identity ranks (manual link < parent API id < variant API id < name/number) with the
price join intentionally omitted, so eBay evidence can attach to an exact physical variant.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

PRINT_ORDER = {"holo": 0, "non-holo": 1, "reverse-holo": 2}


def _name(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def _number(value: Any) -> str:
    return re.sub(r"^0+", "", str(value or "").lower().split("/")[0])


def resolve_default_variants(cards: Iterable[Mapping[str, Any]], inputs: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    legacy_by_set: dict[str, list[Mapping[str, Any]]] = {}
    for legacy in inputs["cards"]:
        legacy_by_set.setdefault(str(legacy["set_id"]), []).append(legacy)
    variants_by_card: dict[str, list[Mapping[str, Any]]] = {}
    for variant in inputs["variants"]:
        variants_by_card.setdefault(str(variant["card_id"]), []).append(variant)
    links: dict[str, list[str]] = {}
    for link in inputs["links"]:
        links.setdefault(str(link["canonical_card_id"]), []).append(str(link["legacy_card_id"]))
    out: dict[str, dict[str, Any]] = {}
    for card in cards:
        cid, set_id = str(card["id"]), str(card["set_id"])
        pool = legacy_by_set.get(set_id, [])
        api = card.get("pokemon_tcg_api_card_id")
        ranked: dict[int, set[str]] = {}
        if links.get(cid):
            ranked.setdefault(-1, set()).update(links[cid])
        parent = {str(x["id"]) for x in pool if api and x.get("pokemon_tcg_api_id") == api}
        if parent:
            ranked.setdefault(0, set()).update(parent)
        else:
            via_variant = {str(x["id"]) for x in pool for v in variants_by_card.get(str(x["id"]), [])
                           if api and v.get("pokemon_tcg_api_id") == api}
            if via_variant:
                ranked.setdefault(1, set()).update(via_variant)
            else:
                wanted = {_number(card.get("number")), _number(card.get("printed_number"))}
                by_name = {str(x["id"]) for x in pool if _name(x.get("name")) == _name(card.get("name"))
                           and _number(x.get("card_number")) in wanted}
                if by_name:
                    ranked.setdefault(2, set()).update(by_name)
        if not ranked:
            out[cid] = {"variant_id": None, "candidate_variants": 0}
            continue
        legacy_ids = ranked[min(ranked)]
        candidates = sorted((v for lid in legacy_ids for v in variants_by_card.get(lid, [])),
                            key=lambda v: (v.get("special_type") is not None, PRINT_ORDER.get(v.get("printing_type"), 9), str(v["id"])))
        out[cid] = {"variant_id": str(candidates[0]["id"]) if candidates else None, "candidate_variants": len(candidates)}
    return out
