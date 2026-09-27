"""Bounded, complete edition history reads and explicit-date materialization.

A successful HTTP response is not proof that all history rows were returned.
Keep the exact count and deterministic row identity until the batch is complete.
No scope fallback and no date relabeling is permitted here.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Iterable

HISTORY_RPC = 'get_pokemon_market_root_set_value_daily_history_bulk_v1'
REFRESH_RPC = 'refresh_pokemon_edition_history_day_v1'
PAGE_SIZE = 256
MAX_ROWS_PER_BATCH = 200_000


class EditionHistoryIncomplete(RuntimeError):
    """The source response cannot be certified complete."""


def read_edition_history_batch(
    client: Any, root_ids: Iterable[str], *, start_date: str, end_date: str,
    page_size: int = PAGE_SIZE,
) -> list[dict]:
    ids = sorted(set(str(value) for value in root_ids))
    if not ids:
        return []
    if not 1 <= len(ids) <= 4 or not 1 <= page_size <= 1000:
        raise ValueError('edition history requires 1-4 roots and 1-1000 rows per page')
    start = date.fromisoformat(str(start_date)[:10]).isoformat()
    end = date.fromisoformat(str(end_date)[:10]).isoformat()
    if start > end:
        raise ValueError('history dates are reversed')
    params = {'p_root_set_ids': ids, 'p_start_date': start, 'p_end_date': end}
    rows: list[dict] = []
    expected = None
    previous_key = None
    for _ in range(MAX_ROWS_PER_BATCH + 1):
        response = (client.rpc(HISTORY_RPC, params, count='exact')
                    .order('set_id').order('market_scope').order('market_date')
                    .range(len(rows), len(rows) + page_size - 1).execute())
        total = getattr(response, 'count', None)
        if type(total) is not int or not 0 <= total <= MAX_ROWS_PER_BATCH:
            raise EditionHistoryIncomplete('missing_or_invalid_exact_count')
        if expected is None:
            expected = total
        elif expected != total:
            raise EditionHistoryIncomplete('history_changed_during_pagination')
        page = response.data
        if not isinstance(page, list) or len(page) > page_size:
            raise EditionHistoryIncomplete('invalid_history_page')
        if not page:
            if len(rows) != expected:
                raise EditionHistoryIncomplete('history_ended_before_exact_count')
            return rows
        for row in page:
            key = tuple(str(row.get(k) or '') for k in ('set_id', 'market_scope', 'market_date'))
            if key[0] not in ids or key[1] not in ('standard', 'first_edition', 'unlimited', 'shadowless'):
                raise EditionHistoryIncomplete('unexpected_history_identity')
            if not start <= key[2] <= end or (previous_key is not None and key <= previous_key):
                raise EditionHistoryIncomplete('unordered_duplicate_or_out_of_range_history')
            rows.append(dict(row))
            previous_key = key
        if len(rows) > expected:
            raise EditionHistoryIncomplete('history_exceeds_exact_count')
        if len(rows) == expected:
            return rows
        # Advance by the actual count, not requested page size: lower server
        # caps may return a short page before the real end of the history.
    raise EditionHistoryIncomplete('history_page_budget_exhausted')


def refresh_edition_history_for_markets(client: Any, markets: Iterable[dict], *, market_date: str) -> list[dict]:
    """Each root is committed independently by the source-gated SQL function.

    Called on the canonical publisher's serialized write path. SQL checks exact
    date lineage, raw/V2 price parity, and preserves uncertified scope status.
    """
    day = date.fromisoformat(str(market_date)[:10]).isoformat()
    ids = sorted({str(m.get('id') or m.get('set_id')) for m in markets
                  if m.get('market_scope') in ('first_edition', 'unlimited', 'shadowless')
                  and (m.get('id') or m.get('set_id'))})
    receipts = []
    for root_id in ids:
        response = client.rpc(REFRESH_RPC, {'p_root_set_id': root_id, 'p_market_date': day}).execute()
        receipt = response.data
        if (not isinstance(receipt, dict) or receipt.get('status') not in ('complete', 'noop')
                or receipt.get('market_date') != day or receipt.get('root_set_id') != root_id
                or receipt.get('raw_v2_equal') is not True):
            raise EditionHistoryIncomplete(f'edition_history_refresh_not_verified:{root_id}')
        receipts.append(receipt)
    return receipts
