"""Pure helpers for replaying snapshot builders with scoped-root values.

This module has no database client and changes nothing by import. It is used only
when a caller explicitly supplies current-day root overrides; production builders
retain their existing source when overrides are omitted.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping, MutableMapping, Sequence


class ScopedSnapshotReplayError(ValueError):
    pass


def _positive_amount(value: Any) -> Decimal:
    if value is None or isinstance(value, bool):
        raise ScopedSnapshotReplayError("current root set value is missing")
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise ScopedSnapshotReplayError("current root set value is not numeric") from exc
    if not amount.is_finite() or amount <= 0:
        raise ScopedSnapshotReplayError("current root set value must be positive")
    return amount


def apply_current_standard_root_overrides(
    histories: Mapping[str, Sequence[Mapping[str, Any]]],
    override_rows: Iterable[Mapping[str, Any]],
    *,
    market_date: str,
    allowed_set_ids: Iterable[str],
) -> dict[str, list[dict[str, Any]]]:
    """Replace only the supplied roots' current-day Standard history point.

    The caller must explicitly supply a root set ID, exact market date and
    Standard scope. Partial overrides are allowed so unrelated sets retain the
    production history source during a diagnostic replay. Duplicate root rows,
    unknown roots, wrong dates/scopes and non-positive values fail closed.
    """
    day = str(market_date)[:10]
    if len(day) != 10:
        raise ScopedSnapshotReplayError("explicit YYYY-MM-DD market date required")
    allowed = {str(value) for value in allowed_set_ids}
    if not allowed:
        raise ScopedSnapshotReplayError("allowed root set IDs are required")

    result: dict[str, list[dict[str, Any]]] = {
        str(set_id): [dict(row) for row in rows]
        for set_id, rows in histories.items()
    }
    seen: set[str] = set()
    for raw in override_rows:
        row = dict(raw)
        set_id = str(row.get("set_id") or "")
        if not set_id or set_id not in allowed:
            raise ScopedSnapshotReplayError("override contains an unknown/non-root set")
        if set_id in seen:
            raise ScopedSnapshotReplayError("duplicate current root override")
        seen.add(set_id)
        if str(row.get("snapshot_date") or "")[:10] != day:
            raise ScopedSnapshotReplayError("root override date does not match replay date")
        if str(row.get("value_scope") or "") != "standard":
            raise ScopedSnapshotReplayError("only Standard root overrides are accepted")
        value = _positive_amount(row.get("set_value"))
        current = [
            dict(point)
            for point in result.get(set_id, [])
            if str(point.get("snapshot_date") or point.get("market_date") or "")[:10] != day
        ]
        current.append({
            "set_id": set_id,
            "snapshot_date": day,
            "set_value": str(value),
            "source": row.get("source") or "price_storage_v2_combined_root_candidate",
        })
        current.sort(key=lambda point: str(point.get("snapshot_date") or point.get("market_date") or ""))
        result[set_id] = current
    return result
