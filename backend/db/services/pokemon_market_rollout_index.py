from __future__ import annotations

from typing import Any, Mapping, Sequence

from backend.db.services.pokemon_market_index_service import (
    PAGE_SIZE,
    TABLE,
    read_raw_index_history_for_audit,
)
from backend.db.services.pokemon_market_rollout_cohort import (
    resolve_market_root_cohort,
    rollout_transition_set_ids,
)
from backend.domain.pokemon.market_index import (
    CHASE_INDEX_KEY,
    INDEX_KEYS,
    MARKET_INDEX_CONTRACT_VERSION,
    MARKET_INDEX_METHODOLOGY_VERSION,
    RAW_INDEX_KEY,
    deterministic_fingerprint,
)


def _current_source_rows(client: Any, set_ids: Sequence[str], market_date: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for offset in range(0, len(set_ids), 100):
        batch = list(set_ids[offset:offset + 100])
        page = list(
            client.table("pokemon_set_value_daily_history")
            .select(
                "set_id,snapshot_date,set_value,priced_card_count,total_card_count,"
                "value_scope,source,updated_at"
            )
            .in_("set_id", batch)
            .eq("snapshot_date", str(market_date)[:10])
            .in_("value_scope", ["standard", "top10"])
            .execute().data or []
        )
        rows.extend(dict(row) for row in page)
    return rows


def _latest_previous_by_key(client: Any, market_date: str) -> dict[str, dict[str, Any]]:
    rows = [
        dict(row)
        for row in read_raw_index_history_for_audit(client, through_date=market_date)
        if str(row.get("market_date") or "")[:10] < str(market_date)[:10]
    ]
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row.get("index_key") or "")
        if key not in INDEX_KEYS:
            continue
        existing = latest.get(key)
        if existing is None or str(row.get("market_date")) > str(existing.get("market_date")):
            latest[key] = row
    return latest


def _previous_constituents(row: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not row:
        return {}
    return {
        str(item.get("setId") or item.get("set_id")): dict(item)
        for item in (row.get("constituents_json") or [])
        if item.get("setId") or item.get("set_id")
    }


def build_rollout_market_index_rows(client: Any, *, market_date: str) -> list[dict[str, Any]]:
    """Build only the promoted date, preserving prior index history verbatim.

    On an era's activation date every set in that era is excluded from the
    common-cohort return calculation. That neutralizes both brand-new set entry
    and any Set Value definition correction (for example parent + Trainer
    Gallery) without rewriting historical index performance. The next market
    date compares the corrected staged cohort normally.
    """
    day = str(market_date)[:10]
    sets = resolve_market_root_cohort(client, market_date=day)
    if not sets:
        raise RuntimeError("eligible Pokemon Market cohort is empty")
    set_by_id = {str(row["id"]): row for row in sets}
    set_ids = sorted(set_by_id)
    source_rows = _current_source_rows(client, set_ids, day)
    by_scope_set = {
        (str(row.get("value_scope")), str(row.get("set_id"))): row
        for row in source_rows
    }
    previous = _latest_previous_by_key(client, day)
    transition_ids = rollout_transition_set_ids(client, day)

    built: list[dict[str, Any]] = []
    for index_key in INDEX_KEYS:
        scope = "standard" if index_key == RAW_INDEX_KEY else "top10"
        constituents: list[dict[str, Any]] = []
        missing: list[str] = []
        for set_id in set_ids:
            source = by_scope_set.get((scope, set_id))
            value = float(source.get("set_value") or 0) if source else 0.0
            count = int(source.get("priced_card_count") or 0) if source else 0
            if not source or value <= 0 or count <= 0:
                missing.append(set_id)
                continue
            pokemon_set = set_by_id[set_id]
            constituents.append({
                "setId": set_id,
                "canonicalKey": pokemon_set.get("canonical_key"),
                "setValue": value,
                "includedCardCount": count,
                "sourceSnapshotDate": day,
                "source": source.get("source"),
                "sourceUpdatedAt": source.get("updated_at"),
            })
        if missing:
            raise RuntimeError(
                f"{scope} rollout source is incomplete for {len(missing)} sets: {missing[:5]}"
            )

        previous_row = previous.get(index_key)
        previous_values = _previous_constituents(previous_row)
        current_values = {str(item["setId"]): item for item in constituents}
        basket_value = sum(float(item["setValue"]) for item in constituents)

        if previous_row is None:
            daily_return = None
            normalized_index_value = 100.0
            previous_market_date = None
            common_ids: list[str] = []
        else:
            previous_market_date = str(previous_row.get("market_date"))[:10]
            common_ids = sorted(
                (set(previous_values) & set(current_values)) - set(transition_ids)
            )
            if not common_ids:
                raise RuntimeError(
                    f"{index_key} has no non-rollout common cohort with {previous_market_date}"
                )
            previous_common = sum(float(previous_values[key]["setValue"]) for key in common_ids)
            current_common = sum(float(current_values[key]["setValue"]) for key in common_ids)
            if previous_common <= 0:
                raise RuntimeError("previous common-cohort basket must be positive")
            daily_return = current_common / previous_common - 1.0
            normalized_index_value = float(previous_row["normalized_index_value"]) * (1.0 + daily_return)

        cohort_fp = deterministic_fingerprint([item["setId"] for item in constituents])
        source_fp = deterministic_fingerprint([
            {
                key: item.get(key)
                for key in (
                    "setId", "setValue", "includedCardCount", "sourceSnapshotDate",
                    "source", "sourceUpdatedAt"
                )
            }
            for item in constituents
        ])
        built.append({
            "tcg": "pokemon",
            "index_key": index_key,
            "market_date": day,
            "contract_version": MARKET_INDEX_CONTRACT_VERSION,
            "methodology_version": MARKET_INDEX_METHODOLOGY_VERSION,
            "basket_value": basket_value,
            "normalized_index_value": normalized_index_value,
            "daily_return": daily_return,
            "previous_market_date": previous_market_date,
            "set_count": len(constituents),
            "card_count": sum(int(item["includedCardCount"]) for item in constituents),
            "cohort_fingerprint": cohort_fp,
            "source_generation_fingerprint": source_fp,
            "constituents_json": constituents,
            "diagnostics_json": {
                "commonSetIds": common_ids,
                "rolloutNeutralizedSetIds": sorted(transition_ids),
                "rolloutTransition": bool(transition_ids),
            },
        })
    return built


def persist_rollout_market_index_rows(client: Any, rows: Sequence[Mapping[str, Any]]) -> int:
    if not rows:
        return 0
    client.table(TABLE).upsert(
        [dict(row) for row in rows],
        on_conflict="tcg,index_key,market_date,methodology_version",
    ).execute()
    return len(rows)
