"""Bounded historical composite-root Set Value calculation and backfill."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable, Mapping, Sequence

from backend.db.services.pokemon_set_value_constituent_freeze import (
    build_freeze_items, freeze_set_value_constituents,
)

PRICE_RPC = "get_pokemon_set_value_canonical_prices_as_of_v2_shadow"
HISTORY_TABLE = "pokemon_set_value_daily_history"
STANDARD_SOURCE = "canonical_root_standard_backfill_v1"
TOP10_SOURCE = "canonical_root_top10_backfill_v1"
ROLLOUT_VIEW = "pokemon_market_public_rollout_root_sets_v1"
ROOT_AUTHORITY_CUTOVER = "2026-09-10"
LEGACY_GENERIC_SOURCES = {
    "standard": "card_variant_price_observations_near_mint_latest_as_of_day:standard:canonical_checklist",
    "top10": "card_variant_price_observations_near_mint_latest_as_of_day:top10:canonical_checklist",
}
PROTECTED_ROOT_SOURCES = {
    "canonical_root_set_public_rollout_v1",
    "canonical_root_top10_public_rollout_v1",
    "canonical_root_set_public_rollout_candidate_v1",
    "canonical_root_top10_public_rollout_candidate_v1",
    STANDARD_SOURCE,
    TOP10_SOURCE,
}
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
    set_by_card = {str(row["id"]): str(row["set_id"]) for row in eligible}
    frozen_items = build_freeze_items(
        {**row, "set_id": set_by_card[str(row["canonical_card_id"])]} for row in priced
    )
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
            "frozen_items": frozen_items,
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


def _material(row: Mapping[str, Any]) -> dict[str, Any]:
    return {key: row.get(key) for key in (
        "set_id", "snapshot_date", "value_scope", "set_value",
        "priced_card_count", "total_card_count", "canonical_card_count",
        "linked_card_count", "included_card_count", "coverage_pct",
    )}


def _same_material(old: Mapping[str, Any], value: Mapping[str, Any], coverage: Any) -> bool:
    return (
        _money(old.get("set_value")) == _money(value.get("set_value"))
        and int(old.get("priced_card_count") or 0) == int(value.get("priced_card_count") or 0)
        and int(old.get("total_card_count") or 0) == int(value.get("total_card_count") or 0)
        and _money(old.get("coverage_pct")) == _money(coverage)
    )


def _same_full_material(old: Mapping[str, Any], value: Mapping[str, Any], coverage: Any) -> bool:
    return _same_material(old, value, coverage) and all(
        int(old.get(key) or 0) == int(value.get(key) or 0)
        for key in ("canonical_card_count", "linked_card_count", "included_card_count")
    )


def _active_ids(client: Any, table: str, roots: Sequence[str], day: str) -> set[str]:
    fields = ("set_id,activated_market_date" if table == ROLLOUT_VIEW
              else "set_id,activated_market_date,deactivated_market_date,enabled")
    query = client.table(table).select(fields).in_("set_id", roots)
    if table != ROLLOUT_VIEW:
        query = query.eq("enabled", True)
    rows = _rows(query.lte("activated_market_date", day).execute())
    return {str(row["set_id"]) for row in rows
            if row.get("enabled", True)
            and (not row.get("deactivated_market_date")
                 or str(row["deactivated_market_date"])[:10] > day)}


def _activation_anchor(client: Any, root: str) -> dict[str, Any]:
    projection = calculate_root_as_of(client, root, ROOT_AUTHORITY_CUTOVER)
    rows = _rows(client.table(HISTORY_TABLE).select(
        "id,set_id,snapshot_date,value_scope,set_value,priced_card_count,total_card_count,canonical_card_count,linked_card_count,included_card_count,coverage_pct,source"
    ).eq("set_id", root).eq("snapshot_date", ROOT_AUTHORITY_CUTOVER)
      .in_("value_scope", ["standard", "top10"]).execute())
    by_scope = {str(row.get("value_scope")): row for row in rows}
    scopes = {
        scope: {
            "passed": bool(by_scope.get(scope)) and _same_material(
                by_scope[scope], projection[scope], projection["coverage_pct"]
            ),
            "persisted": _material(by_scope[scope]) if by_scope.get(scope) else None,
            "projected": {**_material({**projection[scope], "set_id": root,
                                       "snapshot_date": ROOT_AUTHORITY_CUTOVER}),
                          "coverage_pct": projection["coverage_pct"]},
        }
        for scope in ("standard", "top10")
    }
    result = {"root_set_id": root, "market_date": ROOT_AUTHORITY_CUTOVER,
              "scopes": scopes, "passed": all(item["passed"] for item in scopes.values())}
    if not result["passed"]:
        raise RuntimeError(f"Sep10 activation anchor mismatch for {root}")
    return result


def plan_historical_root_backfill(client: Any, root_set_ids: Sequence[str], start_date: str,
                                  end_date: str, *, normalize_provenance: bool = False,
                                  repair_conflicting_generic: bool = False) -> list[dict[str, Any]]:
    if repair_conflicting_generic and not normalize_provenance:
        raise ValueError("repair_conflicting_generic requires normalize_provenance")
    roots = sorted(set(str(value) for value in root_set_ids))
    if not roots or len(roots) > MAX_ROOTS:
        raise ValueError(f"root count must be between 1 and {MAX_ROOTS}")
    planned: list[dict[str, Any]] = []
    anchors: dict[str, dict[str, Any]] = {}
    for day in _dates(start_date, end_date):
        active_ids = _active_ids(client, "pokemon_market_root_authority", roots, day)
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
                    same = _same_material(old, value, projection["coverage_pct"])
                    if not same:
                        if not repair_conflicting_generic:
                            raise RuntimeError(f"conflicting approved history for {root} {day} {scope}")
                        if day < ROOT_AUTHORITY_CUTOVER:
                            raise RuntimeError(f"conflict repair before root-authority cutover for {root} {day}")
                        if old.get("source") in PROTECTED_ROOT_SOURCES:
                            raise RuntimeError(f"refusing conflicting canonical-root history for {root} {day} {scope}")
                        if old.get("source") != LEGACY_GENERIC_SOURCES[scope]:
                            raise RuntimeError(f"refusing unknown conflict source for {root} {day} {scope}")
                        rollout_ids = _active_ids(client, ROLLOUT_VIEW, roots, day)
                        if root not in rollout_ids:
                            raise RuntimeError(f"non-rollout root conflict repair requested for {root} {day}")
                        if root not in anchors:
                            anchors[root] = _activation_anchor(client, root)
                        anchor = anchors[root]
                        action = "repair_conflicting_generic"
                    else:
                        anchor = None
                        action = ("noop_identical" if old.get("source") == value["source"] or not normalize_provenance
                                  else "normalize_provenance")
                else:
                    anchor = None
                    action = "insert"
                planned.append({**value, "set_id": root, "snapshot_date": day,
                                "coverage_pct": projection["coverage_pct"], "action": action,
                                "member_set_ids": projection["member_set_ids"],
                                "activation_anchor": anchor,
                                "existing_row_id": old.get("id") if old else None,
                                "existing_source": old.get("source") if old else None,
                                "existing_material": _material(old) if old else None,
                                "old_material": _material(old) if action == "repair_conflicting_generic" else None,
                                "new_material": _material({**value, "set_id": root, "snapshot_date": day,
                                                           "coverage_pct": projection["coverage_pct"]})
                                if action == "repair_conflicting_generic" else None})
    return planned


def execute_historical_root_backfill(client: Any, root_set_ids: Sequence[str], start_date: str,
                                     end_date: str, *, commit: bool = False,
                                     normalize_provenance: bool = False,
                                     repair_conflicting_generic: bool = False,
                                     freeze_constituents: bool = False) -> list[dict[str, Any]]:
    plan = plan_historical_root_backfill(
        client, root_set_ids, start_date, end_date,
        normalize_provenance=normalize_provenance,
        repair_conflicting_generic=repair_conflicting_generic,
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
            "id,set_id,snapshot_date,value_scope,set_value,priced_card_count,total_card_count,canonical_card_count,linked_card_count,included_card_count,coverage_pct,source"
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
    for row in (item for item in plan if item["action"] == "repair_conflicting_generic"):
        changes = {key: row[key] for key in (
            "set_value", "priced_card_count", "total_card_count", "canonical_card_count",
            "linked_card_count", "included_card_count", "coverage_pct", "source",
        )}
        changes["updated_at"] = datetime.now(timezone.utc).isoformat()
        query = client.table(HISTORY_TABLE).update(changes)
        expected_material = row["existing_material"]
        for key in ("id", "set_id", "snapshot_date", "value_scope", "set_value",
                    "priced_card_count", "total_card_count", "canonical_card_count", "linked_card_count",
                    "included_card_count", "coverage_pct", "source"):
            expected = (row["existing_row_id"] if key == "id" else row["existing_source"]
                        if key == "source" else expected_material[key])
            query = query.eq(key, expected)
        changed = _rows(query.execute())
        if len(changed) != 1:
            raise RuntimeError(f"concurrent economic repair mismatch for {row['set_id']} {row['snapshot_date']} {row['value_scope']}")
        verified = _rows(client.table(HISTORY_TABLE).select(
            "id,set_id,snapshot_date,value_scope,set_value,priced_card_count,total_card_count,canonical_card_count,linked_card_count,included_card_count,coverage_pct,source"
        ).eq("id", row["existing_row_id"]).limit(2).execute())
        post = verified[0] if len(verified) == 1 else {}
        if post.get("source") != row["source"] or not _same_full_material(post, row, row["coverage_pct"]):
            raise RuntimeError("economic repair postcondition failed")
    if freeze_constituents:
        # Exact in-memory rows that produced each Standard value; failure propagates.
        for row in (item for item in plan if item["value_scope"] == "standard"):
            freeze_set_value_constituents(
                client, root_set_id=row["set_id"], market_date=row["snapshot_date"],
                set_value=row["set_value"], items=row["frozen_items"], commit=True,
            )
    return plan
