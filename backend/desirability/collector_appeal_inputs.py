"""The production-safe reads Collector Appeal is built from, and the subject
assembly that turns them into what CA7 consumes.

WHY THIS MODULE EXISTS
----------------------
Every loader below already existed - inside ``backend/scripts``. That was fine
while Collector Appeal was research: a study script may read however it likes,
because nothing serves what it computes. It stops being fine the moment a
request path needs the same numbers, because a service that imports a CLI study
module inherits the study's argparse, its artifact writers, its ``numpy``
dependency and its logging, and a research script's read is then load-bearing
for a public page without anyone having decided that it should be.

So the reads move HERE - to the desirability package, next to the policy
constants that govern them - and the scripts import them back. One
implementation, two callers, no drift. The alternative (a parallel copy for the
service) would put two functions behind one set of fingerprinted rules, and the
copy would be wrong the first time only one of them was edited.

WHAT MUST NOT CHANGE, AND WHY
-----------------------------
``PULL_MODEL_LOADER_VERSION`` is an input to the Collector Appeal formula
fingerprint (see ``collector_appeal_fingerprint.collect_assumptions``). Its own
docstring says to bump it when the READ changes shape - a different table, a
different payload key, a different column. So the read here is a byte-for-byte
move of the study's loader, NOT an improvement of it:

  * same table (``PULL_MODEL_SOURCE_TABLE``);
  * same columns (``PULL_MODEL_SOURCE_COLUMNS`` - the whole ``payload_json``);
  * same payload keys, same group precedence, same slot rule, same arithmetic.

The whole-``payload_json`` read is genuinely wasteful: production carries ~11 MB
across the snapshot table to yield ~190 kB of pull-rate assumptions, and
selecting ``payload_json->pull_rate_assumptions`` server-side would cut it by
~58x. That optimization is deliberately NOT taken here. It would change the
read's shape, which would require bumping the loader version, which would move
the formula fingerprint - and a fingerprint change means every stored score was
computed under different rules. Trading a fingerprint invalidation for a faster
read is not a performance decision; it is a correctness decision, and it is not
this module's to make. The cost is paid once per cache period instead
(see ``collector_appeal_service``), which is where it belongs.

CARD IDENTITY IS ADDITIVE, AND CANNOT MOVE A SCORE
--------------------------------------------------
``build_subject_index`` attaches canonical card id, number and image URL to each
card. This is safe by construction, not by inspection:

  * ``collector_appeal.subject_dual_path`` reads only ``pull_probability``, so P
    cannot see the new fields;
  * ``card_links.build_card_input_manifest`` hashes an explicit allowlist
    (``card_name``, ``rarity``, ``pull_probability``, ``slot_group``), so the
    source manifest hash cannot see them either;
  * no version constant is touched, so the formula fingerprint cannot move.

A test asserts the enriched index produces byte-identical manifests and P values
to the unenriched one.
"""

from __future__ import annotations

import logging
import math
import random
import time
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from backend.calculations.utils.rarity_classification import normalize_rarity_key
from backend.db.services.data_service_health import classify_data_service_error
from backend.desirability.card_links import (
    CARD_DESIRABILITY_LINK_COLUMNS,
    CARD_DESIRABILITY_LINK_TABLE,
    aggregate_card_appeal,
    subject_key_for,
)
from backend.desirability.composite import COMPOSITE_SCORING_VERSION
from backend.desirability.opening_appeal import build_subjects
from backend.desirability.pull_model import (
    PULL_MODEL_PAYLOAD_KEYS,
    PULL_MODEL_SOURCE_COLUMNS,
    PULL_MODEL_SOURCE_TABLE,
    group_priority,
    probability_from_denominator,
    slot_group_of,
)
from backend.desirability.rarity_buckets import HIT_BUCKETS, classify_rarity

logger = logging.getLogger(__name__)

# The canonical-card read. Not fingerprinted: which COLUMNS of a card row are
# selected cannot change a score, because the scoring inputs (rarity ->
# probability, link -> demand) are unchanged by carrying an image URL alongside
# them. Identity columns are here so the public contract can name a specific
# printing rather than a bare card name.
CANONICAL_CARD_TABLE = "pokemon_canonical_cards"
CANONICAL_CARD_COLUMNS = (
    "id,set_id,name,supertype,subtypes,rarity,number,printed_number,"
    "image_small_url,image_large_url"
)

COMPOSITE_SCORE_TABLE = "pokemon_desirability_composite_scores"
COMPOSITE_SCORE_COLUMNS = "pokemon_reference_id,pokemon_name,desirability_score"


# `payload_json` averages ~209 kB/row (max ~483 kB) across 33 rows, and cold
# detoast throughput on this instance was measured at roughly 60-180 kB/s against
# an 8s statement_timeout - so even a 4-row page (~840 kB) failed every attempt.
# One row per request is what reliably fits. It costs 33 round trips once per
# cache period, which is the trade this loader already documents choosing.
# Pagination only - see `load_pull_rate_model` on why this does not touch the
# fingerprint.
PULL_MODEL_READ_PAGE_SIZE = 1


def _paged_select(query: Any, *, page_size: int = 1000, attempts: int = 4) -> List[Dict[str, Any]]:
    """Read every page, retrying TRANSIENT failures with backoff + jitter.

    Transience is decided by the shared classifier rather than by retrying every
    exception: the previous rule spent four attempts and ~12s on faults that
    could never succeed (a missing column, a permission error), and reported all
    of them identically. Backoff is exponential with jitter so several readers
    recovering from the same outage do not retry in lockstep.
    """
    rows: List[Dict[str, Any]] = []
    start = 0
    while True:
        page: Optional[List[Dict[str, Any]]] = None
        last_error: Optional[Exception] = None
        for attempt in range(1, attempts + 1):
            try:
                response = query.range(start, start + page_size - 1).execute()
                page = list(response.data or [])
                break
            except Exception as exc:  # pragma: no cover - network shape
                last_error = exc
                failure = classify_data_service_error(exc)
                if not failure.transient or attempt >= attempts:
                    logger.error(
                        "[collector-appeal-inputs] read failed offset=%s attempt=%s/%s "
                        "error_type=%s code=%s status=%s transient=%s final=true",
                        start, attempt, attempts, failure.error_type, failure.code,
                        failure.status_code, failure.transient,
                    )
                    break
                base_delay = min(4.0, 0.5 * (2 ** (attempt - 1)))
                logger.warning(
                    "[collector-appeal-inputs] read retry offset=%s attempt=%s/%s "
                    "error_type=%s code=%s status=%s",
                    start, attempt, attempts, failure.error_type, failure.code,
                    failure.status_code,
                )
                time.sleep(max(0.0, base_delay + random.uniform(0.0, base_delay * 0.5)))
        if page is None:
            raise RuntimeError(f"read failed after {attempts} attempts at offset {start}") from last_error
        rows.extend(page)
        if len(page) < page_size:
            break
        start += page_size
    return rows


def _chunked(values: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    for index in range(0, len(values), size):
        yield values[index:index + size]


def load_pull_rate_model(client: Any) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """``set_id -> {rarity_key: {probability, slot_group}}`` from the modeled pack model.

    ``slot_label`` is the mutually-exclusive slot; cards sharing it must have
    their probabilities added, never combined by an independence formula.

    Byte-identical to the study loader this replaces - see the module docstring
    on why the wasteful whole-payload read is retained deliberately.

    Read in small PAGES, which is not the optimization the module docstring
    refuses. That refusal is about the read's SHAPE - a different table, column,
    or payload key would change the inputs and so must move the fingerprint.
    Page size changes none of those: the same rows of the same columns of the
    same table are returned, only across more requests, so the loader version
    and the fingerprint are deliberately unchanged. It is required because the
    default 1000-row page asks for all ~6.9 MB of `payload_json` at once and
    exceeds the 8s statement_timeout on every attempt - a deterministic failure
    that no retry can clear, and the reason CA7 was unavailable for every set.
    """
    rows = _paged_select(
        client.table(PULL_MODEL_SOURCE_TABLE).select(PULL_MODEL_SOURCE_COLUMNS),
        page_size=PULL_MODEL_READ_PAGE_SIZE,
    )
    by_set: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for row in rows:
        payload = row.get("payload_json")
        if not isinstance(payload, dict):
            continue
        assumptions = next(
            (payload[key] for key in PULL_MODEL_PAYLOAD_KEYS
             if isinstance(payload.get(key), dict)),
            None,
        )
        if assumptions is None:
            continue
        best: Dict[str, Any] = {}
        for entry in assumptions.get("rows") or []:
            if not isinstance(entry, dict):
                continue
            probability = probability_from_denominator(entry.get("specific_card_odds_denominator"))
            rarity_key = normalize_rarity_key(str(entry.get("rarity") or ""))
            if not rarity_key or probability is None:
                continue
            priority = group_priority(entry.get("group"))
            current = best.get(rarity_key)
            if current is None or priority < current[0]:
                best[rarity_key] = (
                    priority,
                    {
                        "probability": probability,
                        "slot_group": slot_group_of(entry),
                        "card_count": entry.get("card_count"),
                        "expected_cards_per_pack": entry.get("expected_cards_per_pack"),
                    },
                )
        if best:
            by_set[str(row.get("set_id"))] = {key: value for key, (_p, value) in best.items()}
    return by_set


def load_cards(client: Any, set_ids: Sequence[str]) -> List[Dict[str, Any]]:
    """Canonical card rows for the given sets, including identity/image columns."""
    cards: List[Dict[str, Any]] = []
    for chunk in _chunked(sorted(set_ids), 5):
        cards.extend(
            _paged_select(
                client.table(CANONICAL_CARD_TABLE)
                .select(CANONICAL_CARD_COLUMNS)
                .in_("set_id", list(chunk))
            )
        )
    return cards


def load_appeal_by_card(client: Any, card_ids: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    """``canonical_card_id -> aggregated subject appeal`` through the canonical link policy.

    Aggregation is delegated to ``card_links.aggregate_card_appeal`` - the
    fingerprinted rule - so this function only reads.
    """
    scores = {
        int(row["pokemon_reference_id"]): row
        for row in _paged_select(
            client.table(COMPOSITE_SCORE_TABLE)
            .select(COMPOSITE_SCORE_COLUMNS)
            .eq("scoring_version", COMPOSITE_SCORING_VERSION)
        )
        if row.get("pokemon_reference_id") is not None
    }
    links_by_card: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for chunk in _chunked(sorted(card_ids), 200):
        for link in _paged_select(
            client.table(CARD_DESIRABILITY_LINK_TABLE)
            .select(CARD_DESIRABILITY_LINK_COLUMNS)
            .in_("pokemon_canonical_card_id", list(chunk))
        ):
            links_by_card[str(link.get("pokemon_canonical_card_id"))].append(link)

    appeal: Dict[str, Dict[str, Any]] = {}
    for card_id, links in links_by_card.items():
        aggregated = aggregate_card_appeal(links, scores)
        if aggregated is not None:
            appeal[card_id] = aggregated
    return appeal


def _image_url(card: Mapping[str, Any]) -> Optional[str]:
    """Prefer the large art; fall back to small. None when neither exists."""
    for field in ("image_large_url", "image_small_url"):
        value = card.get(field)
        if value:
            return str(value)
    return None


def build_subject_index(
    client: Any,
    set_ids: Sequence[str],
    pull_model: Mapping[str, Any],
) -> Dict[str, List[Dict[str, Any]]]:
    """``set_id -> subjects`` for every set that has a modeled pack.

    The eligibility rules are the fingerprinted ones and are applied in the same
    order as the study loader: hit-bucket eligibility, then a desirability link,
    then a modeled probability for the card's rarity. A card missing any of the
    three is skipped rather than defaulted - a defaulted probability would be a
    fabricated measurement.

    Identity fields are additive; see the module docstring for why they cannot
    move P or any manifest hash.
    """
    modelled_ids = [sid for sid in set_ids if sid in pull_model]
    if not modelled_ids:
        return {}
    cards = load_cards(client, modelled_ids)
    appeal_by_card = load_appeal_by_card(client, [str(card.get("id")) for card in cards])

    by_set: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for card in cards:
        set_id = str(card.get("set_id"))
        rarity_model = pull_model.get(set_id) or {}
        classification = classify_rarity(card.get("rarity"))
        if classification.bucket not in HIT_BUCKETS:
            continue
        appeal_row = appeal_by_card.get(str(card.get("id")))
        model = rarity_model.get(classification.normalized_key)
        if appeal_row is None or model is None:
            continue
        by_set[set_id].append(
            {
                # --- scoring inputs (fingerprinted; order and values unchanged)
                "subject_key": subject_key_for(appeal_row["primary_reference_id"]),
                "subject_name": appeal_row.get("primary_species"),
                "subject_demand": appeal_row["appeal"],
                "pull_probability": min(model["probability"], 1.0),
                "slot_group": model["slot_group"],
                "card_name": card.get("name"),
                "rarity": card.get("rarity"),
                # --- identity only (additive; never read by P or any manifest)
                "canonical_card_id": str(card.get("id")),
                "card_number": card.get("number"),
                "printed_number": card.get("printed_number"),
                "image_url": _image_url(card),
                "rarity_priority": classification.rarity_priority,
            }
        )
    return {set_id: build_subjects(cards) for set_id, cards in by_set.items()}


# ---------------------------------------------------------------------------
# Deterministic subject-path identity
# ---------------------------------------------------------------------------

# The tie-break, in order. Dictionary/query order is NOT a tie-break: it is a
# coin flip that happens to be reproducible on one machine, and it would let the
# displayed "elite chase" for a subject change because a row came back in a
# different order.
SUBJECT_PATH_TIE_BREAK_VERSION = "subject_path_tie_break_v1_probability_rarity_number_id"


def _path_sort_key(card: Mapping[str, Any], *, accessible: bool) -> tuple:
    """Total order over a subject's cards for path selection.

    ``accessible`` picks the reachable end (highest probability first); its
    negation picks the elite end (lowest probability first). Every subsequent
    key is a deterministic tiebreak, and the canonical card id is last so the
    order is total even for two identical printings.
    """
    probability = card.get("pull_probability")
    probability = float(probability) if isinstance(probability, (int, float)) else 0.0
    # Rarity priority: higher means rarer/more premium (see rarity_buckets).
    rarity_priority = card.get("rarity_priority") or 0
    number = str(card.get("printed_number") or card.get("card_number") or "")
    card_id = str(card.get("canonical_card_id") or "")
    if accessible:
        # Most reachable first; then the LEAST premium rarity, so the
        # "accessible path" is the plainest printing at that probability.
        return (-probability, rarity_priority, number, card_id)
    # Rarest first; then the MOST premium rarity.
    return (probability, -rarity_priority, number, card_id)


def _path_payload(card: Mapping[str, Any]) -> Dict[str, Any]:
    probability = card.get("pull_probability")
    probability = float(probability) if isinstance(probability, (int, float)) else None
    implied_odds = None
    if probability is not None and probability > 0 and math.isfinite(probability):
        implied_odds = round(1.0 / probability, 1)
    return {
        "canonicalCardId": card.get("canonical_card_id"),
        "cardName": card.get("card_name"),
        "cardNumber": card.get("printed_number") or card.get("card_number"),
        "rarity": card.get("rarity"),
        "imageUrl": card.get("image_url"),
        "modeledProbability": probability,
        "impliedOdds": implied_odds,
    }


def select_subject_paths(subject: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """The specific printings behind one subject's accessible and elite paths.

    Returns None when the subject carries no card with a modeled probability -
    never a half-populated pair, because a path naming a card with no odds would
    be an identity without a measurement.

    This does NOT recompute Dual-Path Depth. It reports WHICH printings the
    depth calculation's two ends refer to, selected under the same
    easiest/rarest rule and made total by the tie-break above.
    """
    cards = [
        card for card in (subject.get("cards") or [])
        if isinstance(card.get("pull_probability"), (int, float))
    ]
    if not cards:
        return None
    accessible = min(cards, key=lambda card: _path_sort_key(card, accessible=True))
    elite = min(cards, key=lambda card: _path_sort_key(card, accessible=False))
    return {
        "accessiblePath": _path_payload(accessible),
        "elitePath": _path_payload(elite),
        "printingCount": len(cards),
        "tieBreakVersion": SUBJECT_PATH_TIE_BREAK_VERSION,
    }
