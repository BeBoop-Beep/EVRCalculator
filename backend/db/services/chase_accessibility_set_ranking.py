"""Chase Accessibility SET-LEVEL ranking authority.

This module is the ONLY place a Chase Accessibility rank is computed. It is
deliberately separate from :mod:`backend.db.services.chase_accessibility_service`
(which only resolves/persists/projects the raw metric) so that every ranking
surface - Set RIP, Product Family Rankings, Rankings tables - shares exactly
one rank computation instead of each re-deriving its own.

LOCKED PRINCIPLE
----------------
Chase Accessibility is SET-level. A product row NEVER gets its own rank: every
product in set S inherits set S's raw value AND set S's rank. Ranking duplicated
product rows as though each were independent would silently distort the cohort
(a set with 5 products would out-vote a set with 1). This module ranks UNIQUE
`set_id` values only - callers project the result onto as many product rows as
they like afterwards, but the ranking pass itself never sees a product row.

ELIGIBILITY (mirrors `chase_accessibility_service.publication_integrity_failures`)
-----------------------------------------------------------------------------
A set is included in the ranked cohort only if its
`pokemon_set_chase_accessibility_snapshot_latest` row:
  * exists,
  * has `status == STATUS_READY` (an explicit "no pull model" / stale / error
    row is excluded, not coerced to a rank),
  * declares the canonical `CHASE_ACCESSIBILITY_VERSION`,
  * has `mapped_hc_mass >= MIN_MAPPED_HC_MASS`,
  * has a non-null `accessibility` value,
  * and, when the caller supplies `expected_run_by_set` (the same
    set -> calculation_run_id authority the ranking/publication run is using),
    the row's `calculation_run_id` matches it exactly.

A set failing any of these is simply absent from the ranked cohort - it is
NOT assigned a rank of `None` "in the ranking" versus "out of it" is the same
observable state, but the row is never silently averaged in.

TIE SEMANTICS
-------------
This codebase's existing rank producers (`set_rip_service.build_set_rip`,
`product_family_rankings_service._rank_key`) do not use shared/competition
ranking (`1,2,2,4` "standard competition") or dense ranking (`1,2,2,3` - ties
share a rank and the next rank has no gap). They sort by score with a
deterministic secondary key and assign a unique sequential rank to every row
via `enumerate(..., 1)`. Because the secondary key is itself part of the sort
tuple, no two rows can ever compare equal at the point ranks are assigned -
every row gets a distinct rank even when the primary score is identical
between rows. This is **ordinal ranking**, not dense ranking: it is the
established convention across the ranking surfaces this module feeds, and
this module deliberately matches it rather than introducing a new tie
convention. Concretely: sets are ordered by `(-accessibility, set_id)` and
every set receives a unique integer rank 1..N. `set_id` ascending is the
deterministic tiebreak - when two DIFFERENT sets have byte-identical
`accessibility` values, they are NOT assigned the same rank; the one with the
lexicographically smaller `set_id` receives the better (numerically lower)
rank, and the other receives the very next integer with no gap and no shared
rank. This is separate from, and never affects, the LOCKED PRINCIPLE above:
every product belonging to the SAME set still inherits that one set's single
rank verbatim.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Sequence

from backend.db.services.chase_accessibility_service import (
    project_chase_accessibility,
    read_chase_accessibility_snapshots_for_sets,
)
from backend.desirability.chase_accessibility import (
    CHASE_ACCESSIBILITY_VERSION,
    MIN_MAPPED_HC_MASS,
    STATUS_READY,
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _eligible_row(row: Optional[Mapping[str, Any]], set_id: str,
                   expected_run_by_set: Optional[Mapping[str, str]]) -> bool:
    if not row:
        return False
    if row.get("status") != STATUS_READY:
        return False
    if row.get("version") != CHASE_ACCESSIBILITY_VERSION:
        return False
    if row.get("accessibility") is None:
        return False
    mass = row.get("mapped_hc_mass")
    try:
        if mass is None or float(mass) < MIN_MAPPED_HC_MASS:
            return False
    except (TypeError, ValueError):
        return False
    if expected_run_by_set:
        expected = expected_run_by_set.get(set_id)
        if expected and _text(row.get("calculation_run_id")) != _text(expected):
            return False
    return True


def compute_chase_accessibility_set_ranks(
    rows_by_set_id: Mapping[str, Mapping[str, Any]],
    eligible_set_ids: Sequence[str], *,
    expected_run_by_set: Optional[Mapping[str, str]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Rank UNIQUE set_ids by Chase Accessibility. One pass, batch input only.

    ``rows_by_set_id`` must already be the batch-loaded raw snapshot map (see
    :func:`load_chase_accessibility_set_authority`) - this function does no I/O.
    Returns ``{set_id: {"setRank": int, "setCohortSize": int}}`` for eligible
    sets only; ineligible/absent sets simply have no entry.
    """
    candidate_ids = sorted({_text(value) for value in eligible_set_ids if _text(value)})
    eligible = [
        set_id for set_id in candidate_ids
        if _eligible_row(rows_by_set_id.get(set_id), set_id, expected_run_by_set)
    ]
    # ORDINAL ranking (not dense/competition): (-accessibility, set_id) sort
    # then enumerate(..., 1). Because set_id is part of the sort tuple, two
    # DIFFERENT sets with byte-identical accessibility never share a rank -
    # each gets a distinct, consecutive integer, ordered by set_id ascending.
    ordered = sorted(
        eligible,
        key=lambda set_id: (-float(rows_by_set_id[set_id]["accessibility"]), set_id),
    )
    cohort_size = len(ordered)
    return {
        set_id: {"setRank": rank, "setCohortSize": cohort_size}
        for rank, set_id in enumerate(ordered, 1)
    }


def load_chase_accessibility_set_authority(
    *, set_ids: Sequence[Any], client: Any,
    expected_run_by_set: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    """Batch-load raw rows for the cohort ONCE and compute the rank map ONCE.

    This is the single entry point ranking-projection callers (product family
    rankings, set rankings) should use: one `read_chase_accessibility_snapshots_for_sets`
    query for the whole cohort, one rank pass over unique set_ids - never a
    per-row or per-product read.
    """
    rows_by_set_id = read_chase_accessibility_snapshots_for_sets(set_ids=set_ids, client=client)
    rank_map = compute_chase_accessibility_set_ranks(
        rows_by_set_id, list(rows_by_set_id.keys()) or [str(s) for s in set_ids],
        expected_run_by_set=expected_run_by_set,
    )
    return {"rowsBySetId": rows_by_set_id, "rankBySetId": rank_map}


def project_chase_accessibility_for_set(
    set_id: Any, *, rows_by_set_id: Mapping[str, Mapping[str, Any]],
    rank_by_set_id: Mapping[str, Mapping[str, Any]],
) -> Dict[str, Any]:
    """The per-row Chase Accessibility presentation contract (Phase 4 shape).

    Field is named ``setRank``/``setCohortSize`` deliberately - never
    ``familyRank``/``productRank`` - because the rank this carries is a SET
    rank, even when this projection is attached to a product row. Every
    product belonging to the same set_id gets the byte-identical dict here
    (same raw value, same setRank, same setCohortSize) because both inputs are
    keyed purely by set_id.
    """
    resolved = _text(set_id)
    row = rows_by_set_id.get(resolved)
    base = project_chase_accessibility(row)
    rank_info = rank_by_set_id.get(resolved)
    return {
        "value": base.get("chaseAccessibility"),
        "percent": base.get("chaseAccessibilityPct"),
        "status": base.get("chaseAccessibilityStatus"),
        "version": base.get("chaseAccessibilityVersion"),
        "chaseDepth": base.get("chaseDepth"),
        "mappedHcMass": base.get("mappedHcMass"),
        "setRank": rank_info.get("setRank") if rank_info else None,
        "setCohortSize": rank_info.get("setCohortSize") if rank_info else None,
    }
