from __future__ import annotations

import json
import math
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Mapping, Optional


CURRENCY_ROUNDING_TOLERANCE = 0.01
SET_VALUE_SCOPES = ("standard", "hits", "top10")
SUBSET_SCOPES = ("hits", "top10")
DEFAULT_EXTREME_DISCONTINUITY_RATIO = 5.0


def _number(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _date_key(row: Mapping[str, Any]) -> Optional[str]:
    value = row.get("snapshot_date") or row.get("snapshotDate") or row.get("date")
    text = str(value or "").strip()
    return text[:10] if len(text) >= 10 else None


def _scope_value(row: Mapping[str, Any]) -> Any:
    for key in ("set_value", "setValue", "value"):
        if key in row:
            return row.get(key)
    return None


class SetValueScopeInvariantError(ValueError):
    def __init__(self, details: Dict[str, Any]):
        self.details = details
        super().__init__(json.dumps(details, sort_keys=True, default=str))


def _violation(
    *,
    set_id: Any,
    snapshot_date: Any,
    scope: str,
    reason: str,
    subset_value: Any = None,
    checklist_value: Any = None,
) -> Dict[str, Any]:
    return {
        "code": "POKEMON_SET_VALUE_SCOPE_INVARIANT",
        "setId": str(set_id or ""),
        "date": snapshot_date,
        "scope": scope,
        "reason": reason,
        "subsetValue": subset_value,
        "checklistValue": checklist_value,
    }


def validate_set_value_scope_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    set_id: Any = None,
    tolerance: float = CURRENCY_ROUNDING_TOLERANCE,
) -> None:
    by_date: Dict[str, Dict[str, float]] = defaultdict(dict)
    for row in rows:
        scope = str(row.get("value_scope") or row.get("valueScope") or row.get("scope") or "").lower()
        date_key = _date_key(row)
        raw_value = _scope_value(row)
        parsed = _number(raw_value)
        row_set_id = row.get("set_id") or row.get("setId") or set_id
        if scope not in SET_VALUE_SCOPES or not date_key:
            continue
        if parsed is None:
            raise SetValueScopeInvariantError(
                _violation(
                    set_id=row_set_id,
                    snapshot_date=date_key,
                    scope=scope,
                    reason="value_not_finite",
                    subset_value=raw_value if scope in SUBSET_SCOPES else None,
                )
            )
        if parsed < 0:
            raise SetValueScopeInvariantError(
                _violation(
                    set_id=row_set_id,
                    snapshot_date=date_key,
                    scope=scope,
                    reason="value_negative",
                    subset_value=parsed if scope in SUBSET_SCOPES else None,
                )
            )
        by_date[date_key][scope] = parsed

    for date_key, values in sorted(by_date.items()):
        checklist = values.get("standard")
        if checklist is None:
            continue
        for scope in SUBSET_SCOPES:
            subset = values.get(scope)
            if subset is not None and subset > checklist + tolerance:
                raise SetValueScopeInvariantError(
                    _violation(
                        set_id=set_id,
                        snapshot_date=date_key,
                        scope=scope,
                        reason="subset_exceeds_checklist",
                        subset_value=subset,
                        checklist_value=checklist,
                    )
                )


def validate_histories_by_scope(
    histories_by_scope: Mapping[str, Any],
    *,
    set_id: Any,
    tolerance: float = CURRENCY_ROUNDING_TOLERANCE,
) -> None:
    rows = [
        {**point, "value_scope": scope, "set_id": set_id}
        for scope, history in (histories_by_scope or {}).items()
        if scope in SET_VALUE_SCOPES and isinstance(history, list)
        for point in history
        if isinstance(point, dict)
    ]
    validate_set_value_scope_rows(rows, set_id=set_id, tolerance=tolerance)


def audit_set_value_scope_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    tolerance: float = CURRENCY_ROUNDING_TOLERANCE,
    discontinuity_ratio: float = DEFAULT_EXTREME_DISCONTINUITY_RATIO,
) -> Dict[str, Any]:
    normalized: List[Dict[str, Any]] = []
    hard_failures: List[Dict[str, Any]] = []
    for row in rows:
        scope = str(row.get("value_scope") or row.get("valueScope") or "").lower()
        date_key = _date_key(row)
        set_id = str(row.get("set_id") or row.get("setId") or "")
        raw_value = _scope_value(row)
        value = _number(raw_value)
        if scope not in SET_VALUE_SCOPES or not date_key or not set_id:
            continue
        if value is None:
            hard_failures.append(_violation(set_id=set_id, snapshot_date=date_key, scope=scope, reason="value_not_finite", subset_value=raw_value))
            continue
        if value < 0:
            hard_failures.append(_violation(set_id=set_id, snapshot_date=date_key, scope=scope, reason="value_negative", subset_value=value))
        normalized.append({"set_id": set_id, "snapshot_date": date_key, "value_scope": scope, "set_value": value})

    by_set_date: Dict[tuple[str, str], Dict[str, float]] = defaultdict(dict)
    for row in normalized:
        by_set_date[(row["set_id"], row["snapshot_date"])][row["value_scope"]] = row["set_value"]
    for (set_id, date_key), values in sorted(by_set_date.items()):
        checklist = values.get("standard")
        if checklist is None:
            continue
        for scope in SUBSET_SCOPES:
            subset = values.get(scope)
            if subset is not None and subset > checklist + tolerance:
                hard_failures.append(
                    _violation(
                        set_id=set_id,
                        snapshot_date=date_key,
                        scope=scope,
                        reason="subset_exceeds_checklist",
                        subset_value=subset,
                        checklist_value=checklist,
                    )
                )

    warnings: List[Dict[str, Any]] = []
    by_set_scope: Dict[tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for row in normalized:
        by_set_scope[(row["set_id"], row["value_scope"])].append(row)
    for (set_id, scope), scope_rows in sorted(by_set_scope.items()):
        scope_rows.sort(key=lambda row: row["snapshot_date"])
        for previous, current in zip(scope_rows, scope_rows[1:]):
            low = min(previous["set_value"], current["set_value"])
            high = max(previous["set_value"], current["set_value"])
            ratio = math.inf if low == 0 and high > 0 else (high / low if low > 0 else 1.0)
            if ratio >= discontinuity_ratio:
                warnings.append(
                    {
                        "code": "POKEMON_SET_VALUE_EXTREME_DISCONTINUITY",
                        "setId": set_id,
                        "scope": scope,
                        "previousDate": previous["snapshot_date"],
                        "date": current["snapshot_date"],
                        "previousValue": previous["set_value"],
                        "value": current["set_value"],
                        "ratio": ratio,
                    }
                )

    return {
        "rowsAudited": len(normalized) + sum(1 for row in hard_failures if row["reason"] == "value_not_finite"),
        "hardFailureCount": len(hard_failures),
        "warningCount": len(warnings),
        "hardFailures": hard_failures,
        "warnings": warnings,
    }
