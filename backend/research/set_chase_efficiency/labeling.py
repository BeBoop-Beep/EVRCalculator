"""Human chase-labeling: cohort, candidate pool, packet, ingestion, agreement.

WHY THIS EXISTS
---------------
Stage II tested four families of algorithmic chase definitions - fixed K, HHI
adaptive, price boundaries, economic multiples - and none was defensible.
Cross-method agreement on WHICH cards are chases peaked at 0.69 Jaccard, only
4 of 21 sets were stable, and K inside a single set ranged from 1 to 123. The
failure is not statistical, it is semantic: nothing in the data says what a
chase IS.

That circularity can only be broken from outside the data, so this module
builds the apparatus for HUMAN labels and nothing else.

THE ONE RULE THIS MODULE ENFORCES
---------------------------------
The model being evaluated must never label its own ground truth. Every
algorithmic output - HHI-derived K, effective chase count, Beat-the-Buy, Chase
EV contribution, Financial RIP, P95, Jackpot, selection status under any rule -
is EXCLUDED from the packet by construction, not by convention:
``PACKET_COLUMNS`` is a closed allow-list and ``assert_packet_is_blind`` fails
if anything else appears. A labeler who can see which cards the algorithm chose
is no longer independent evidence about whether the algorithm is right.

RECALL OVER PRECISION
---------------------
The candidate pool is deliberately over-inclusive. Showing a labeler an obvious
non-chase costs one row of their attention; omitting a real chase silently caps
the recall of every method benchmarked afterwards and cannot be detected later.
The pool therefore includes the union of every Stage-II method's selections, so
no method can be scored against a pool that excluded its own picks.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

#: Schema version for the packet and label template.
CHASE_LABELING_SCHEMA_VERSION = "chase-labeling-v1"

#: The ONLY columns a labeler may see. Closed allow-list, enforced by
#: ``assert_packet_is_blind``.
PACKET_COLUMNS: Tuple[str, ...] = (
    "set_id", "set_name", "card_id", "card_variant_id", "card_name",
    "card_number", "rarity", "treatment", "printing_type", "market_price",
    "pack_price", "value_in_packs", "image_url",
)

#: Columns the human fills in. Appended to the packet to make the template.
LABEL_COLUMNS: Tuple[str, ...] = ("human_label", "labeler_id", "label_confidence", "notes")

#: Anything matching these substrings must never reach a labeler. Checked
#: case-insensitively against packet column names.
FORBIDDEN_COLUMN_FRAGMENTS: Tuple[str, ...] = (
    "hhi", "effective", "chase_count", "btb", "beat_the_buy", "chase_ev",
    "rip", "p95", "p99", "jackpot", "upside", "score", "rank", "selected",
    "universe", "probability", "pull", "confidence_model", "recommend",
    "predicted", "algorithm", "elbow", "boundary", "cluster", "zscore",
)

VALID_LABELS: Tuple[str, ...] = ("CORE_CHASE", "EXTENDED_CHASE", "NOT_CHASE", "UNSURE")
VALID_CONFIDENCE: Tuple[int, ...] = (1, 2, 3)

#: Absolute dollar floor for the permissive pool. Generous on purpose: it sits
#: below the cheapest card any Stage-II method selected in any set.
POOL_ABSOLUTE_FLOOR = 10.0

#: Cards this many times the pack price or better always enter the pool.
POOL_COST_MULTIPLE = 1.0

#: Top-N by market value always enter the pool regardless of the floors.
POOL_TOP_N = 30


@dataclass(frozen=True)
class CohortSet:
    """One set chosen for labeling, with the structural reason it was chosen."""

    canonical_key: str
    set_name: str
    structure: str
    rationale: str


#: The labeling cohort. Selected for STRUCTURAL DIVERSITY - hero versus deep,
#: cheap versus expensive packs, stable versus unstable chase universes, with
#: and without multi-hit mechanics. Financial RIP rank played no part in the
#: selection and is not consulted anywhere in this module.
LABELING_COHORT: Tuple[CohortSet, ...] = (
    CohortSet("phantasmalFlames", "Phantasmal Flames", "hero_chase",
              "Most concentrated set in the cohort (effective EV count 1.40) and the "
              "ONLY set with a genuine price cliff ($275 -> $27, ratio 10.16). The "
              "case where algorithms already agree, so human disagreement here would "
              "falsify the whole labeling premise."),
    CohortSet("paldeanFates", "Paldean Fates", "hero_chase_expensive",
              "Second-most concentrated (2.57) with a $965 headline card and a $23.11 "
              "pack. Largest Chase-EV-versus-BTB rank disagreement in Stage II "
              "(EV rank 4, BTB rank 19)."),
    CohortSet("scarletAndViolet151", "Scarlet and Violet 151", "unstable_expensive",
              "Highest pack price ($29.81) and an UNSTABLE universe (0.346): methods "
              "return K from 1 to 35 and the Stage-II core was a single card. The "
              "clearest test of whether humans can resolve what algorithms cannot."),
    CohortSet("ascendedHeroes", "Ascended Heroes", "deep_expensive_multihit",
              "Nine-card Stage-II core, six cards over $300, and multi-hit packs "
              "(up to 6 qualifying cards). Deep AND expensive, which no other set "
              "combines."),
    CohortSet("prismaticEvolutions", "Prismatic Evolutions", "godpack_unstable",
              "God-pack mechanics (up to 9 qualifying cards in one pack), highest "
              "Chase EV Return (0.408), unstable universe (0.333), and the widest "
              "value-versus-probability concentration divergence (7.90 vs 25.33)."),
    CohortSet("paradoxRift", "Paradox Rift", "deep_cheap_unstable",
              "Deepest chase pool measured (effective EV count 17.55) with a modest "
              "$120 top card. Unstable (0.327); largest-log-gap says K=1 while "
              ">=2xC says K=27, a 5.7x swing in Beat-the-Buy."),
    CohortSet("whiteFlare", "White Flare", "adaptive_k_disagreement",
              "Largest adaptive-K disagreement in Stage II: K from 7 to 24 purely "
              "from the HHI reference pool, and a 123-card two-means universe. "
              "Stage-II core 3 / extended 120."),
    CohortSet("shroudedFable", "Shrouded Fable", "flat_curve_deep",
              "Flattest price curve in the cohort (75, 59, 58, 54, 49) with the "
              "highest BTB (0.263) and the only set whose lower-quartile chase "
              "journey beats buying. Tests whether a flat curve has a chase line "
              "at all."),
    CohortSet("pitchBlack", "Pitch Black", "stable_cheap",
              "Most STABLE universe in Stage II (0.760) at a $4.75 pack. The "
              "positive control: if humans disagree with algorithms here, the "
              "instability elsewhere is not the algorithms' fault."),
    CohortSet("perfectOrder", "Perfect Order", "cheap_pack_moderate",
              "Cheapest pack-equivalent cost ($4.74) and the largest Stage-I rank "
              "mover (Top-1 rank 20 to Top-10 rank 6). Tests whether a cheap pack "
              "shifts where humans draw the chase line."),
)


def cohort_keys() -> Tuple[str, ...]:
    return tuple(entry.canonical_key for entry in LABELING_COHORT)


# ---------------------------------------------------------------------------
# Candidate pool
# ---------------------------------------------------------------------------

def _price(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def build_candidate_pool(
    cards: Sequence[Mapping[str, Any]],
    *,
    pack_price: Optional[float],
    algorithm_selected_ids: Iterable[str] = (),
    top_n: int = POOL_TOP_N,
    absolute_floor: float = POOL_ABSOLUTE_FLOOR,
    cost_multiple: float = POOL_COST_MULTIPLE,
) -> Dict[str, Any]:
    """Permissive union pool, plus proof that nothing plausible was excluded.

    ``algorithm_selected_ids`` is the union of every Stage-II method's picks for
    this set. It is included so that no benchmarked method can later be scored
    against a pool that omitted its own selections - that would understate its
    recall for a reason having nothing to do with the method.

    The returned ``proof`` block is the audit the brief requires: the cheapest
    card IN the pool against the most expensive card OUT of it.
    """
    selected = {str(identifier) for identifier in algorithm_selected_ids if identifier}
    priced = [
        {**dict(card), "_price": _price(card.get("market_price"))}
        for card in cards
    ]
    ranked = sorted(
        (card for card in priced if card["_price"] is not None),
        key=lambda card: (-card["_price"], str(card.get("card_variant_id") or "")),
    )
    cost_floor = (cost_multiple * pack_price) if pack_price else None

    pool: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []
    for index, card in enumerate(ranked):
        reasons: List[str] = []
        if index < top_n:
            reasons.append(f"top_{top_n}_by_market_value")
        if card["_price"] >= absolute_floor:
            reasons.append(f"at_or_above_absolute_floor_{absolute_floor:g}")
        if cost_floor is not None and card["_price"] >= cost_floor:
            reasons.append(f"at_or_above_{cost_multiple:g}x_pack_price")
        if str(card.get("card_variant_id") or "") in selected:
            reasons.append("selected_by_a_stage2_method")
        if reasons:
            pool.append({**card, "_pool_reasons": reasons})
        else:
            excluded.append(card)

    unpriced = [card for card in priced if card["_price"] is None]
    pool_min = min((card["_price"] for card in pool), default=None)
    excluded_max = max((card["_price"] for card in excluded), default=None)
    return {
        "pool": pool,
        "excluded": excluded,
        "unpriced": unpriced,
        "proof": {
            "poolSize": len(pool),
            "excludedCount": len(excluded),
            "unpricedCount": len(unpriced),
            "cheapestCardInPool": pool_min,
            "dearestCardExcluded": excluded_max,
            # A ratio well below 1 means the boundary is not close to contested.
            "exclusionHeadroomRatio": (
                None if pool_min in (None, 0) or excluded_max is None
                else round(excluded_max / pool_min, 4)
            ),
            "absoluteFloor": absolute_floor,
            "costFloor": cost_floor,
            "algorithmSelectedCoveredByPool": all(
                any(str(card.get("card_variant_id") or "") == identifier for card in pool)
                for identifier in selected
            ) if selected else True,
        },
    }


# ---------------------------------------------------------------------------
# Packet
# ---------------------------------------------------------------------------

def assert_packet_is_blind(rows: Sequence[Mapping[str, Any]]) -> None:
    """Fail loudly if any algorithmic output leaked into the labeling packet.

    Anchoring a labeler to the model under test would silently convert this
    study from a validation into a tautology, and the damage would be invisible
    in the resulting numbers. So the check is structural and runs on every
    build.
    """
    for row in rows:
        unexpected = [column for column in row if column not in PACKET_COLUMNS]
        if unexpected:
            raise ValueError(
                f"labeling packet contains non-allow-listed columns: {sorted(unexpected)}"
            )
        for column in row:
            lowered = column.lower()
            for fragment in FORBIDDEN_COLUMN_FRAGMENTS:
                if fragment in lowered:
                    raise ValueError(
                        f"labeling packet column {column!r} matches forbidden "
                        f"fragment {fragment!r}; the labeler must not see model output"
                    )


def assert_packet_rows_are_unique(rows: Sequence[Mapping[str, Any]]) -> None:
    """Every ``(set_id, card_variant_id)`` must appear exactly once.

    A duplicated printing asks a human to label the same card twice, which
    silently corrupts everything downstream: the card gets double weight in the
    consensus, inflates the apparent labelled-card count, and - if the two
    copies are labelled differently - manufactures a "disagreement" between a
    labeler and themselves that the agreement statistics cannot distinguish
    from a real one.

    This is a backstop, not the fix. The source defect is upstream, where a
    reverse-printing row was emitted even when the reverse variant id was just
    the base variant id echoed back. This invariant exists so that if any future
    input path reintroduces a duplicate, the packet build fails loudly instead
    of shipping a corrupted experiment to a human.
    """
    seen: Dict[Tuple[str, str], int] = {}
    for index, row in enumerate(rows):
        key = (str(row.get("set_id") or ""), str(row.get("card_variant_id") or ""))
        if not key[1]:
            raise ValueError(f"packet row {index} has no card_variant_id")
        if key in seen:
            raise ValueError(
                "labeling packet contains duplicate (set_id, card_variant_id) "
                f"{key!r}: rows {seen[key]} and {index}. A human must never be "
                "asked to label the same printing twice."
            )
        seen[key] = index


def packet_row(card: Mapping[str, Any], *, set_id: str, set_name: str,
               pack_price: Optional[float]) -> Dict[str, Any]:
    """One blind row. Only real-world card facts a collector could look up."""
    price = _price(card.get("market_price"))
    return {
        "set_id": set_id,
        "set_name": set_name,
        "card_id": card.get("card_id") or "",
        "card_variant_id": card.get("card_variant_id") or "",
        "card_name": card.get("card_name") or "",
        "card_number": card.get("card_number") or "",
        "rarity": card.get("rarity") or "",
        "treatment": card.get("treatment") or "",
        "printing_type": card.get("printing_type") or "",
        "market_price": "" if price is None else f"{price:.2f}",
        "pack_price": "" if not pack_price else f"{pack_price:.2f}",
        # Value expressed in packs is a real-world fact about the purchase, not
        # a model output: it is price divided by price. It is included because a
        # labeler judging "is this a chase" reasonably wants to know whether the
        # card is worth two packs or two hundred.
        "value_in_packs": (
            "" if price is None or not pack_price else f"{price / pack_price:.1f}"
        ),
        "image_url": card.get("image_url") or "",
    }


def write_packet_csv(rows: Sequence[Mapping[str, Any]], path: Path) -> Path:
    assert_packet_is_blind(rows)
    assert_packet_rows_are_unique(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(PACKET_COLUMNS))
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_label_template_csv(rows: Sequence[Mapping[str, Any]], path: Path,
                             *, labeler_id: str = "") -> Path:
    """The packet plus empty label columns - the file a human actually fills in.

    Labels are left EMPTY. This module never writes a value into
    ``human_label``; a fabricated label would train the benchmark to reproduce
    the model that produced it, which is the exact failure Stage III exists to
    prevent.
    """
    assert_packet_is_blind(rows)
    assert_packet_rows_are_unique(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(PACKET_COLUMNS) + list(LABEL_COLUMNS)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "human_label": "", "labeler_id": labeler_id,
                             "label_confidence": "", "notes": ""})
    return path


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LabelRow:
    set_name: str
    card_variant_id: str
    card_name: str
    market_price: Optional[float]
    human_label: str
    labeler_id: str
    label_confidence: Optional[int]
    notes: str


def read_labels(path: Path) -> Tuple[List[LabelRow], List[Dict[str, Any]]]:
    """Read a filled template. Returns ``(valid rows, rejected rows)``.

    Rejections carry a reason and are never silently dropped: a labeler who
    typed ``CORE`` instead of ``CORE_CHASE`` must find out, not have their
    judgement quietly discarded.
    """
    rows: List[LabelRow] = []
    rejected: List[Dict[str, Any]] = []
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        for line_number, raw in enumerate(csv.DictReader(handle), start=2):
            label = (raw.get("human_label") or "").strip().upper()
            if not label:
                continue  # unlabelled row: not an error, just not yet done
            reason = None
            if label not in VALID_LABELS:
                reason = f"human_label {label!r} is not one of {VALID_LABELS}"
            labeler = (raw.get("labeler_id") or "").strip()
            if reason is None and not labeler:
                reason = "labeler_id is required once a label is present"
            confidence: Optional[int] = None
            raw_confidence = (raw.get("label_confidence") or "").strip()
            if reason is None and raw_confidence:
                try:
                    confidence = int(raw_confidence)
                except ValueError:
                    reason = f"label_confidence {raw_confidence!r} is not an integer"
                else:
                    if confidence not in VALID_CONFIDENCE:
                        reason = f"label_confidence {confidence} is not one of {VALID_CONFIDENCE}"
            variant = (raw.get("card_variant_id") or "").strip()
            if reason is None and not variant:
                reason = "card_variant_id is required"
            if reason is not None:
                rejected.append({"line": line_number, "reason": reason, "row": dict(raw)})
                continue
            rows.append(LabelRow(
                set_name=(raw.get("set_name") or "").strip(),
                card_variant_id=variant,
                card_name=(raw.get("card_name") or "").strip(),
                market_price=_price(raw.get("market_price")),
                human_label=label,
                labeler_id=labeler,
                label_confidence=confidence,
                notes=(raw.get("notes") or "").strip(),
            ))
    return rows, rejected


# ---------------------------------------------------------------------------
# Ground-truth targets
# ---------------------------------------------------------------------------

#: Target A - only the headline chases count as positive.
TARGET_CORE = "core_chase"
#: Target B - any chase a collector would call a successful hit.
TARGET_MEANINGFUL = "meaningful_chase"

TARGETS = (TARGET_CORE, TARGET_MEANINGFUL)


def target_positive(label: str, target: str) -> Optional[bool]:
    """``True`` positive, ``False`` negative, ``None`` = excluded from scoring.

    ``UNSURE`` returns ``None`` for BOTH targets. Folding it into either class
    would silently invent a judgement the labeler explicitly declined to make;
    it is inspected separately in the disagreement analysis instead.
    """
    if label == "UNSURE":
        return None
    if target == TARGET_CORE:
        return label == "CORE_CHASE"
    if target == TARGET_MEANINGFUL:
        return label in ("CORE_CHASE", "EXTENDED_CHASE")
    raise ValueError(f"unknown target {target!r}")


def consensus_labels(rows: Sequence[LabelRow], *, target: str,
                     rule: str = "majority") -> Dict[Tuple[str, str], bool]:
    """Collapse multiple labelers into one truth value per (set, card).

    ``majority`` requires a strict majority of the labelers who expressed an
    opinion; ties are dropped rather than broken, because a tied card is
    precisely a card the humans do not agree is a chase.
    """
    votes: Dict[Tuple[str, str], List[bool]] = {}
    for row in rows:
        value = target_positive(row.human_label, target)
        if value is None:
            continue
        votes.setdefault((row.set_name, row.card_variant_id), []).append(value)
    truth: Dict[Tuple[str, str], bool] = {}
    for key, values in votes.items():
        positives = sum(1 for value in values if value)
        negatives = len(values) - positives
        if rule == "unanimous":
            if positives and not negatives:
                truth[key] = True
            elif negatives and not positives:
                truth[key] = False
        else:
            if positives > negatives:
                truth[key] = True
            elif negatives > positives:
                truth[key] = False
    return truth


# ---------------------------------------------------------------------------
# Inter-labeler agreement
# ---------------------------------------------------------------------------

def _by_labeler(rows: Sequence[LabelRow]) -> Dict[str, Dict[Tuple[str, str], str]]:
    out: Dict[str, Dict[Tuple[str, str], str]] = {}
    for row in rows:
        out.setdefault(row.labeler_id, {})[(row.set_name, row.card_variant_id)] = row.human_label
    return out


def cohens_kappa(a: Mapping[Any, str], b: Mapping[Any, str]) -> Optional[Dict[str, Any]]:
    """Two-labeler chance-corrected agreement over their shared cards.

    Returns ``None`` below three shared items. Kappa is also ``None`` when both
    labelers used exactly one category for everything: expected agreement is
    then 1.0 and the statistic is undefined, which is a real and reportable
    situation rather than a divide-by-zero to be papered over.
    """
    shared = sorted(set(a) & set(b), key=str)
    n = len(shared)
    if n < 3:
        return None
    observed = sum(1 for key in shared if a[key] == b[key]) / n
    categories = set(a[key] for key in shared) | set(b[key] for key in shared)
    expected = sum(
        (sum(1 for key in shared if a[key] == category) / n)
        * (sum(1 for key in shared if b[key] == category) / n)
        for category in categories
    )
    kappa = None if expected >= 1.0 else (observed - expected) / (1.0 - expected)
    return {
        "sharedItems": n,
        "rawAgreement": round(observed, 6),
        "expectedAgreement": round(expected, 6),
        "cohensKappa": None if kappa is None else round(kappa, 6),
        "kappaUndefinedReason": None if kappa is not None else "expected agreement is 1.0",
    }


def fleiss_kappa(rows: Sequence[LabelRow]) -> Optional[Dict[str, Any]]:
    """Chance-corrected agreement for three or more labelers.

    Uses only cards rated by EVERY labeler, so the marginals are comparable.
    """
    by_labeler = _by_labeler(rows)
    if len(by_labeler) < 3:
        return None
    shared = set.intersection(*(set(mapping) for mapping in by_labeler.values()))
    if len(shared) < 3:
        return None
    raters = len(by_labeler)
    categories = sorted(VALID_LABELS)
    counts = []
    for key in sorted(shared, key=str):
        row = [sum(1 for mapping in by_labeler.values() if mapping[key] == category)
               for category in categories]
        counts.append(row)
    n_items = len(counts)
    p_j = [sum(row[j] for row in counts) / (n_items * raters) for j in range(len(categories))]
    p_i = [(sum(value * value for value in row) - raters) / (raters * (raters - 1))
           for row in counts]
    p_bar = sum(p_i) / n_items
    p_e = sum(value * value for value in p_j)
    kappa = None if p_e >= 1.0 else (p_bar - p_e) / (1.0 - p_e)
    return {
        "labelers": raters,
        "sharedItems": n_items,
        "meanObservedAgreement": round(p_bar, 6),
        "expectedAgreement": round(p_e, 6),
        "fleissKappa": None if kappa is None else round(kappa, 6),
    }


def agreement_report(rows: Sequence[LabelRow]) -> Dict[str, Any]:
    """Everything the study can say about how much the humans agree.

    Agreement is reported for the raw four-category scheme AND for each binary
    target, because labelers can disagree sharply about Core-versus-Extended
    while agreeing almost perfectly on chase-versus-not. Those are different
    facts with different consequences for which target is publishable.
    """
    by_labeler = _by_labeler(rows)
    labelers = sorted(by_labeler)
    pairwise: Dict[str, Any] = {}
    for left, right in combinations(labelers, 2):
        result = cohens_kappa(by_labeler[left], by_labeler[right])
        if result is not None:
            pairwise[f"{left}|{right}"] = result

    binary: Dict[str, Any] = {}
    for target in TARGETS:
        projected = {
            labeler: {
                key: ("POSITIVE" if target_positive(label, target) else "NEGATIVE")
                for key, label in mapping.items()
                if target_positive(label, target) is not None
            }
            for labeler, mapping in by_labeler.items()
        }
        pairs = {}
        for left, right in combinations(labelers, 2):
            result = cohens_kappa(projected[left], projected[right])
            if result is not None:
                pairs[f"{left}|{right}"] = result
        binary[target] = pairs

    disputed = []
    grouped: Dict[Tuple[str, str], List[LabelRow]] = {}
    for row in rows:
        grouped.setdefault((row.set_name, row.card_variant_id), []).append(row)
    for (set_name, variant), group in sorted(grouped.items(), key=str):
        distinct = {row.human_label for row in group}
        if len(group) > 1 and len(distinct) > 1:
            disputed.append({
                "setName": set_name,
                "cardVariantId": variant,
                "cardName": group[0].card_name,
                "marketPrice": group[0].market_price,
                "valueInPacks": None,
                "labels": {row.labeler_id: row.human_label for row in group},
                "confidences": {row.labeler_id: row.label_confidence for row in group},
                "coreVsExtendedOnly": distinct <= {"CORE_CHASE", "EXTENDED_CHASE"},
                "involvesUnsure": "UNSURE" in distinct,
            })

    return {
        "labelers": labelers,
        "labelCount": len(rows),
        "distinctCards": len(grouped),
        "labelDistribution": {
            label: sum(1 for row in rows if row.human_label == label)
            for label in VALID_LABELS
        },
        "pairwiseRawScheme": pairwise,
        "pairwiseByTarget": binary,
        "fleiss": fleiss_kappa(rows),
        "disputedCards": disputed,
        "disputedCount": len(disputed),
        "disputedCoreVsExtendedOnly": sum(1 for row in disputed if row["coreVsExtendedOnly"]),
    }
