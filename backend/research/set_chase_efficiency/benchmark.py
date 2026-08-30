"""Score algorithmic chase-universe rules against human labels.

RUNS ONLY WHEN LABELS EXIST
---------------------------
Every entry point here refuses to invent ground truth. With no labels the
benchmark reports ``HUMAN_LABELS_NOT_YET_AVAILABLE`` and stops; it does not
substitute an algorithmic universe for the missing human one, because a
benchmark scored against a model's own output measures nothing.

MACRO-AVERAGED, NOT POOLED
--------------------------
Sets differ enormously in candidate-pool size - Shrouded Fable has 168 eligible
cards, Prismatic Evolutions 447. Pooling every card into one confusion matrix
would let the two or three largest sets decide the winner. Every headline figure
is therefore the unweighted mean of per-set scores, with pooled figures reported
beside them so the gap is visible rather than hidden.

LEAVE-ONE-SET-OUT
-----------------
The cohort is ten sets. Any rule with a tunable parameter can be fitted to ten
sets and look excellent, so ``leave_one_set_out`` refits on nine and scores the
tenth. A rule whose held-out F1 collapses relative to its in-sample F1 is
overfitted and is rejected on that basis, not on taste.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .labeling import TARGETS, LabelRow, consensus_labels

#: Returned by every entry point when no usable human labels were supplied.
NO_LABELS_STATUS = "HUMAN_LABELS_NOT_YET_AVAILABLE"


def confusion(predicted: Iterable[str], truth: Mapping[str, bool]) -> Dict[str, int]:
    """Confusion counts over the cards the humans actually labelled.

    Predictions for cards outside ``truth`` are ignored rather than counted as
    false positives: an unlabelled card is missing evidence, not evidence of a
    mistake. The count is published as ``predictedOutsideTruth`` so a rule that
    selects far outside the labelled pool cannot hide it.
    """
    chosen = {str(identifier) for identifier in predicted}
    scored = set(truth)
    inside = chosen & scored
    tp = sum(1 for identifier in inside if truth[identifier])
    fp = len(inside) - tp
    fn = sum(1 for identifier in scored - chosen if truth[identifier])
    tn = len(scored - chosen) - fn
    return {
        "truePositives": tp, "falsePositives": fp,
        "falseNegatives": fn, "trueNegatives": tn,
        "labelledCards": len(scored),
        "predictedCards": len(chosen),
        "predictedOutsideTruth": len(chosen - scored),
    }


def scores(counts: Mapping[str, int]) -> Dict[str, Optional[float]]:
    """Precision, recall, F1, error rates and Jaccard from confusion counts.

    Each is ``None`` when its denominator is zero. A rule that selects nothing
    has undefined precision, not perfect precision, and reporting 1.0 there
    would let the emptiest rule win.
    """
    tp, fp = counts["truePositives"], counts["falsePositives"]
    fn, tn = counts["falseNegatives"], counts["trueNegatives"]
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    f1 = (2 * precision * recall / (precision + recall)
          if precision and recall and (precision + recall) else
          (0.0 if precision is not None and recall is not None else None))
    union = tp + fp + fn
    return {
        "precision": None if precision is None else round(precision, 6),
        "recall": None if recall is None else round(recall, 6),
        "f1": None if f1 is None else round(f1, 6),
        "falsePositiveRate": round(fp / (fp + tn), 6) if (fp + tn) else None,
        "falseNegativeRate": round(fn / (fn + tp), 6) if (fn + tp) else None,
        "jaccard": round(tp / union, 6) if union else None,
        "accuracy": round((tp + tn) / (tp + fp + fn + tn), 6) if (tp + fp + fn + tn) else None,
    }


def _macro(values: Sequence[Optional[float]]) -> Optional[float]:
    usable = [value for value in values if value is not None]
    return round(sum(usable) / len(usable), 6) if usable else None


def evaluate_method(
    *,
    method_key: str,
    selections_by_set: Mapping[str, Sequence[str]],
    truth_by_set: Mapping[str, Mapping[str, bool]],
) -> Dict[str, Any]:
    """One rule against one target, per set and macro-averaged."""
    per_set: Dict[str, Any] = {}
    pooled = {"truePositives": 0, "falsePositives": 0, "falseNegatives": 0,
              "trueNegatives": 0, "labelledCards": 0, "predictedCards": 0,
              "predictedOutsideTruth": 0}
    for set_name, truth in truth_by_set.items():
        counts = confusion(selections_by_set.get(set_name, ()), truth)
        for key in pooled:
            pooled[key] += counts[key]
        per_set[set_name] = {
            **counts,
            **scores(counts),
            "selectedK": len(selections_by_set.get(set_name, ())),
            "humanPositiveCount": sum(1 for value in truth.values() if value),
        }
    exact_k = [
        1.0 if row["selectedK"] == row["humanPositiveCount"] else 0.0
        for row in per_set.values()
    ]
    k_error = [
        abs(row["selectedK"] - row["humanPositiveCount"]) for row in per_set.values()
    ]
    f1_values = [row["f1"] for row in per_set.values()]
    usable_f1 = [value for value in f1_values if value is not None]
    return {
        "method": method_key,
        "setCount": len(per_set),
        "perSet": per_set,
        "macro": {
            "precision": _macro([row["precision"] for row in per_set.values()]),
            "recall": _macro([row["recall"] for row in per_set.values()]),
            "f1": _macro(f1_values),
            "jaccard": _macro([row["jaccard"] for row in per_set.values()]),
            "falsePositiveRate": _macro([row["falsePositiveRate"] for row in per_set.values()]),
            "falseNegativeRate": _macro([row["falseNegativeRate"] for row in per_set.values()]),
        },
        "pooled": {**pooled, **scores(pooled)},
        "exactKAgreement": round(sum(exact_k) / len(exact_k), 6) if exact_k else None,
        "meanAbsoluteKError": round(sum(k_error) / len(k_error), 6) if k_error else None,
        # Spread of per-set F1. A rule that is excellent on six sets and useless
        # on four is not a canonical rule, however good its mean looks.
        "f1StandardDeviation": (
            round(math.sqrt(sum((value - sum(usable_f1) / len(usable_f1)) ** 2
                                for value in usable_f1) / len(usable_f1)), 6)
            if len(usable_f1) > 1 else None
        ),
        "worstSetF1": min(usable_f1) if usable_f1 else None,
    }


def benchmark(
    *,
    labels: Sequence[LabelRow],
    selections_by_method: Mapping[str, Mapping[str, Sequence[str]]],
    consensus_rule: str = "majority",
) -> Dict[str, Any]:
    """Every method against both ground-truth targets.

    ``selections_by_method`` maps method key -> set name -> selected
    ``card_variant_id`` values, so it can be populated from the Stage-II
    artifact without re-simulating.
    """
    if not labels:
        return {"status": NO_LABELS_STATUS, "targets": {},
                "reason": "no human labels were supplied; nothing was scored"}

    results: Dict[str, Any] = {"status": "SCORED", "consensusRule": consensus_rule,
                               "targets": {}}
    for target in TARGETS:
        truth = consensus_labels(labels, target=target, rule=consensus_rule)
        truth_by_set: Dict[str, Dict[str, bool]] = {}
        for (set_name, variant), value in truth.items():
            truth_by_set.setdefault(set_name, {})[variant] = value
        ranked = [
            evaluate_method(method_key=method, selections_by_set=selections,
                            truth_by_set=truth_by_set)
            for method, selections in sorted(selections_by_method.items())
        ]
        ranked.sort(key=lambda row: (row["macro"]["f1"] is None, -(row["macro"]["f1"] or 0.0)))
        results["targets"][target] = {
            "labelledSets": len(truth_by_set),
            "labelledCards": len(truth),
            "positiveCards": sum(1 for value in truth.values() if value),
            "methods": ranked,
        }
    return results


def leave_one_set_out(
    *,
    labels: Sequence[LabelRow],
    fit: Callable[[Sequence[str]], Any],
    predict: Callable[[Any, str], Sequence[str]],
    target: str,
    consensus_rule: str = "majority",
) -> Dict[str, Any]:
    """Refit on n-1 sets, score the held-out one, repeat.

    ``fit`` receives the training set NAMES and returns whatever parameter the
    rule needs; ``predict`` receives that parameter and the held-out set name
    and returns selected ``card_variant_id`` values. Keeping both as callbacks
    means this function never learns what any particular rule is, so it cannot
    accidentally privilege one.
    """
    if not labels:
        return {"status": NO_LABELS_STATUS}
    truth = consensus_labels(labels, target=target, rule=consensus_rule)
    truth_by_set: Dict[str, Dict[str, bool]] = {}
    for (set_name, variant), value in truth.items():
        truth_by_set.setdefault(set_name, {})[variant] = value
    set_names = sorted(truth_by_set)
    if len(set_names) < 3:
        return {"status": "INSUFFICIENT_SETS", "labelledSets": len(set_names),
                "reason": "leave-one-set-out needs at least three labelled sets"}

    folds: List[Dict[str, Any]] = []
    for held_out in set_names:
        training = [name for name in set_names if name != held_out]
        parameter = fit(training)
        selected = predict(parameter, held_out)
        counts = confusion(selected, truth_by_set[held_out])
        folds.append({
            "heldOutSet": held_out, "fittedParameter": parameter,
            "selectedK": len(list(selected)),
            "humanPositiveCount": sum(1 for value in truth_by_set[held_out].values() if value),
            **counts, **scores(counts),
        })
    return {
        "status": "SCORED",
        "target": target,
        "folds": folds,
        "heldOutMacro": {
            "precision": _macro([fold["precision"] for fold in folds]),
            "recall": _macro([fold["recall"] for fold in folds]),
            "f1": _macro([fold["f1"] for fold in folds]),
            "jaccard": _macro([fold["jaccard"] for fold in folds]),
        },
        "worstFoldF1": min((fold["f1"] for fold in folds if fold["f1"] is not None),
                           default=None),
    }


def disagreement_profile(labels: Sequence[LabelRow]) -> Dict[str, Any]:
    """Where in the price distribution do humans stop agreeing?

    Phase 11. If disputes cluster tightly in one value band, "chase" has a fuzzy
    boundary rather than a wrong one, and a Core+Extended model is the more
    honest representation. If they are scattered, the labels are noise and no
    universe rule can be validated against them.
    """
    if not labels:
        return {"status": NO_LABELS_STATUS}
    grouped: Dict[Tuple[str, str], List[LabelRow]] = {}
    for row in labels:
        grouped.setdefault((row.set_name, row.card_variant_id), []).append(row)

    bands = ((0, 10), (10, 25), (25, 50), (50, 100), (100, 250), (250, 1e9))
    profile: Dict[str, Dict[str, int]] = {
        f"{int(low)}-{'inf' if high > 1e8 else int(high)}":
            {"cards": 0, "disputed": 0, "unsure": 0} for low, high in bands
    }
    for group in grouped.values():
        price = next((row.market_price for row in group if row.market_price), None)
        if price is None:
            continue
        key = next(f"{int(low)}-{'inf' if high > 1e8 else int(high)}"
                   for low, high in bands if low <= price < high)
        profile[key]["cards"] += 1
        distinct = {row.human_label for row in group}
        if len(group) > 1 and len(distinct) > 1:
            profile[key]["disputed"] += 1
        if "UNSURE" in distinct:
            profile[key]["unsure"] += 1
    for block in profile.values():
        block["disputeRate"] = (round(block["disputed"] / block["cards"], 4)
                                if block["cards"] else None)
    return {"status": "SCORED", "priceBands": profile}
