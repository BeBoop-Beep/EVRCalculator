"""Bounded historical composite-root Set Value calculation and backfill."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable, Mapping, Sequence

PRICE_RPC = "get_pokemon_set_value_canonical_prices_as_of_v2_shadow"
HISTORY_TABLE = "pokemon_set_value_daily_history"
STANDARD_SOURCE = "canonical_root_standard_backfill_v1"
TOP10_SOURCE = "canonical_root_top10_backfill_v1"
MAX_ROOTS = 10
MAX_DAYS = 31


def _money(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _rows(result: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in ((result.data if result else None) or [])]


def resolve_composite_members(client: Any, root_set_id: str) -> list[dict[str, Any]]:
    root_rows = _rows(client.table("sets").select(
        "id,name,parent_opening_set_id,counts_toward_parent_set_value,catalog_only"
    ).eq("id", root_set_id).limit(1).execute())
    if not root_rows:
        raise ValueError(f"unknown root set: {root_set_id}")
    root = root_rows[0]
    if root.get("parent_opening_set_id"):
        raise ValueError(f"member set is not a root: {root_set_id}")
    children = _rows(client.table("sets").select(
        "id,name,parent_opening_set_id,counts_toward_parent_set_value,catalog_only"
    ).eq("parent_opening_set_id", root_set_id)
      .eq("counts_toward_parent_set_value", True).execute())
    return sorted([root, *children], key=lambda row: str(row["id"]))


def calculate_root_as_of(client: Any, root_set_id: str, market_date: str) -> dict[str, Any]:
    day = str(market_date)[:10]
    members = resolve_composite_members(client, root_set_id)
    member_ids = [str(row["id"]) for row in members]
    eligible = _rows(client.table("pokemon_canonical_cards").select("id,set_id")
                     .in_("set_id", member_ids).eq("set_value_eligible", True).execute())
    expected_ids = {str(row["id"]) for row in eligible}
    priced_by_id: dict[str, dict[str, Any]] = {}
    for member_id in member_ids:
        for row in _rows(client.rpc(PRICE_RPC, {
            "target_set_id": member_id, "target_date": day,
        }).execute()):
            card_id = str(row["canonical_card_id"])
            if card_id not in expected_ids:
                raise RuntimeError(f"price RPC returned ineligible card {card_id}")
            captured = str(row.get("captured_at") or "")[:10]
            if captured and captured > day:
                raise RuntimeError(f"future price leaked into {day}: {card_id} at {captured}")
            current = priced_by_id.get(card_id)
            key = (captured, str(row.get("card_variant_id") or ""))
            old_key = (str(current.get("captured_at") or "")[:10], str(current.get("card_variant_id") or "")) if current else None
            if current is None or key > old_key:
                priced_by_id[card_id] = row
    missing = sorted(expected_ids - priced_by_id.keys())
    if missing:
        raise RuntimeError(f"incomplete composite root {root_set_id} on {day}: {len(missing)} unpriced cards")
    priced = sorted(priced_by_id.values(), key=lambda row: str(row["canonical_card_id"]))
    top10 = sorted(priced, key=lambda row: (-_money(row["market_price"]), str(row["canonical_card_id"])))[:10]
    if len(top10) != 10:
        raise RuntimeError(f"composite root {root_set_id} has fewer than 10 priced cards")
    total = len(expected_ids)
    common = {
        "set_id": root_set_id, "market_date": day,
        "member_set_ids": member_ids, "canonical_card_count": total,
        "coverage_pct": "100.00", "price_authority": PRICE_RPC,
    }
    return {
        **common,
        "standard": {
            "value_scope": "standard", "set_value": str(_money(sum(_money(r["market_price"]) for r in priced))),
            "priced_card_count": total, "total_card_count": total,
            "included_card_count": total, "canonical_card_count": total, "linked_card_count": total,
            "constituent_card_ids": [str(r["canonical_card_id"]) for r in priced],
            "source": STANDARD_SOURCE,
        },
        "top10": {
            "value_scope": "top10", "set_value": str(_money(sum(_money(r["market_price"]) for r in top10))),
            "priced_card_count": 10, "total_card_count": 10,
            "included_card_count": 10, "canonical_card_count": 10,
            "linked_card_count": 10,
            "constituent_card_ids": [str(r["canonical_card_id"]) for r in top10],
            "source": TOP10_SOURCE,
        },
    }


def _dates(start_date: str, end_date: str) -> list[str]:
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    if end < start or end >= date.today() + timedelta(days=1):
        raise ValueError("date range must be ordered and must not include future dates")
    days = (end - start).days + 1
    if days > MAX_DAYS:
        raise ValueError(f"date range exceeds {MAX_DAYS} days")
    return [str(start + timedelta(days=i)) for i in range(days)]


def plan_historical_root_backfill(client: Any, root_set_ids: Sequence[str], start_date: str,
                                  end_date: str, *, normalize_provenance: bool = False) -> list[dict[str, Any]]:
    roots = sorted(set(str(value) for value in root_set_ids))
    if not roots or len(roots) > MAX_ROOTS:
        raise ValueError(f"root count must be between 1 and {MAX_ROOTS}")
    planned: list[dict[str, Any]] = []
    for day in _dates(start_date, end_date):
        active = _rows(client.table("pokemon_market_root_authority").select("set_id,deactivated_market_date")
                       .in_("set_id", roots).eq("enabled", True)
                       .lte("activated_market_date", day).execute())
        active_ids = {str(row["set_id"]) for row in active
                      if not row.get("deactivated_market_date")
                      or str(row["deactivated_market_date"])[:10] > day}
        if active_ids != set(roots):
            raise ValueError(f"non-authority root requested for {day}: {sorted(set(roots)-active_ids)}")
        for root in roots:
            projection = calculate_root_as_of(client, root, day)
            existing = _rows(client.table(HISTORY_TABLE).select(
                "id,set_id,snapshot_date,value_scope,set_value,priced_card_count,total_card_count,canonical_card_count,linked_card_count,included_card_count,coverage_pct,source"
            ).eq("set_id", root).eq("snapshot_date", day).in_("value_scope", ["standard", "top10"]).execute())
            by_scope = {str(row["value_scope"]): row for row in existing}
            for scope in ("standard", "top10"):
                value = projection[scope]
                old = by_scope.get(scope)
                if old:
                    same = (_money(old["set_value"]) == _money(value["set_value"])
                            and int(old["priced_card_count"]) == value["priced_card_count"]
                            and int(old["total_card_count"]) == value["total_card_count"]
                            and _money(old.get("coverage_pct")) == _money(projection["coverage_pct"]))
                    if not same:
                        raise RuntimeError(f"conflicting approved history for {root} {day} {scope}")
                    action = ("noop_identical" if old.get("source") == value["source"] or not normalize_provenance
                              else "normalize_provenance")
                else:
                    action = "insert"
                planned.append({**value, "set_id": root, "snapshot_date": day,
                                "coverage_pct": projection["coverage_pct"], "action": action,
                                "member_set_ids": projection["member_set_ids"],
                                "existing_row_id": old.get("id") if old else None,
                                "existing_source": old.get("source") if old else None,
                                "existing_material": ({key: old.get(key) for key in (
                                    "set_id", "snapshot_date", "value_scope", "set_value",
                                    "priced_card_count", "total_card_count", "canonical_card_count",
                                    "linked_card_count", "included_card_count", "coverage_pct",
                                )} if old else None)})
    return planned


def execute_historical_root_backfill(client: Any, root_set_ids: Sequence[str], start_date: str,
                                     end_date: str, *, commit: bool = False,
                                     normalize_provenance: bool = False) -> list[dict[str, Any]]:
    plan = plan_historical_root_backfill(
        client, root_set_ids, start_date, end_date,
        normalize_provenance=normalize_provenance,
    )
    if not commit:
        return plan
    rows = [{key: row[key] for key in (
        "set_id", "snapshot_date", "value_scope", "set_value", "priced_card_count",
        "total_card_count", "canonical_card_count", "linked_card_count", "included_card_count", "coverage_pct", "source"
    )} for row in plan if row["action"] == "insert"]
    if rows:
        # INSERT (not upsert) is deliberate: a concurrent row appearing after
        # planning must raise a uniqueness error rather than overwrite history.
        client.table(HISTORY_TABLE).insert(rows).execute()
    for row in (item for item in plan if item["action"] == "normalize_provenance"):
        query = client.table(HISTORY_TABLE).update({"source": row["source"]})
        expected_material = row["existing_material"]
        for key in ("id", "set_id", "snapshot_date", "value_scope", "set_value",
                    "priced_card_count", "total_card_count", "canonical_card_count", "linked_card_count",
                    "included_card_count", "coverage_pct", "source"):
            expected = (row["existing_row_id"] if key == "id" else row["existing_source"]
                        if key == "source" else expected_material[key])
            query = query.eq(key, expected)
        changed = _rows(query.execute())
        if len(changed) != 1:
            raise RuntimeError(f"concurrent provenance normalization mismatch for {row['set_id']} {row['snapshot_date']} {row['value_scope']}")
        verified = _rows(client.table(HISTORY_TABLE).select(
            "id,set_id,snapshot_date,value_scope,set_value,priced_card_count,total_card_count,canonical_card_count,included_card_count,coverage_pct,source"
        ).eq("id", row["existing_row_id"]).limit(2).execute())
        post = verified[0] if len(verified) == 1 else {}
        material_ok = (
            post.get("source") == row["source"]
            and str(post.get("set_id")) == row["set_id"]
            and str(post.get("snapshot_date"))[:10] == row["snapshot_date"]
            and str(post.get("value_scope")) == row["value_scope"]
            and _money(post.get("set_value")) == _money(expected_material["set_value"])
            and _money(post.get("coverage_pct")) == _money(expected_material["coverage_pct"])
            and all(int(post.get(k) or 0) == int(expected_material[k] or 0) for k in (
                "priced_card_count", "total_card_count", "canonical_card_count", "linked_card_count", "included_card_count"
            ))
        )
        if not material_ok:
            raise RuntimeError("provenance normalization postcondition failed")
    return plan
