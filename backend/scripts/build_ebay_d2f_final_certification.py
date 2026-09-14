"""Score the frozen eBay D2M v2 matcher once against frozen Final Blind gold."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from backend.scripts.ebay_d2m_matcher_v2 import (
    MATCHER_VERSION, classify_listing, rule_fingerprint,
)
from backend.scripts.ebay_final_gold_audit import (
    AUDIT_HISTORY, GOLD_MANIFEST, build_audit_queue, effective_gold_fingerprint,
    effective_labels, read_audit_history, reconstruct_audit_state, sha256_file,
)
from backend.scripts.ebay_gold_access import OUT, load_partition
from backend.scripts.ebay_gold_review_server import (
    HISTORY, read_history, reconstruct_effective_state,
)

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs/research/index_fair_value"
FREEZE = OUT / "ebay_d2m_v2_final_freeze_manifest.json"
POSITIVE = "EXACT_TARGET_MATCH"
AMBIGUOUS = "AMBIGUOUS"
NEGATIVE = frozenset({
    "GRADED", "WRONG_CARD_NUMBER", "SEALED_OR_ACCESSORY",
    "RELATED_BUT_WRONG_VARIANT", "LOT_OR_BUNDLE", "WRONG_LANGUAGE",
    "WRONG_SET", "CONDITION_INELIGIBLE", "OTHER",
})
CATASTROPHIC = (
    "RELATED_BUT_WRONG_VARIANT", "WRONG_CARD_NUMBER", "WRONG_SET",
    "WRONG_LANGUAGE", "GRADED", "LOT_OR_BUNDLE", "SEALED_OR_ACCESSORY",
    "AMBIGUOUS",
)
EXPECTED_MATCHER_FINGERPRINT = "a2ac052891df2745f2a2dde8b615a5ccbf1ef23a777eb2a0310e35aef94f6d5e"
EXPECTED_GOLD_FINGERPRINT = "40da9c4ccbe030124d608c59673902f662e14835cc0d8c4b4fffb89231b97a7a"
EXPECTED_FROZEN_COMMIT = "52656c6d1cf6803bbf2ec4f6fc5b14493d68b302"


def ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 8) if denominator else 0.0


def wilson(successes: int, total: int) -> list[float]:
    if not total:
        return [0.0, 0.0]
    z = 1.959963984540054
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return [round(center - margin, 8), round(center + margin, 8)]


def matcher_state(result: Mapping[str, Any]) -> str:
    return str(result["identity_state"])


def high_metrics(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    definitive = [record for record in records if record["human_gold_label"] != AMBIGUOUS]
    tp = sum(record["human_gold_label"] == POSITIVE and record["matcher_confidence_state"] == "HIGH_CONFIDENCE" for record in definitive)
    fp = sum(record["human_gold_label"] in NEGATIVE and record["matcher_confidence_state"] == "HIGH_CONFIDENCE" for record in definitive)
    tn = sum(record["human_gold_label"] in NEGATIVE and record["matcher_confidence_state"] != "HIGH_CONFIDENCE" for record in definitive)
    fn = sum(record["human_gold_label"] == POSITIVE and record["matcher_confidence_state"] != "HIGH_CONFIDENCE" for record in definitive)
    accepted = tp + fp
    precision = ratio(tp, accepted)
    recall = ratio(tp, tp + fn)
    specificity = ratio(tn, tn + fp)
    return {
        "accepted_count": accepted, "true_positives": tp, "false_positives": fp,
        "true_negatives": tn, "false_negatives": fn, "precision": precision,
        "recall": recall, "specificity": specificity,
        "f1": ratio(2 * precision * recall, precision + recall),
        "precision_wilson_95": wilson(tp, accepted),
        "binary_denominator": len(definitive), "ambiguous_excluded": True,
    }


def coverage(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    cards = sorted({str(record["canonical_card_id"]) for record in records})
    names = {str(record["canonical_card_id"]): str(record["target_card_name"]) for record in records}
    exact = defaultdict(list)
    for record in records:
        if record["human_gold_label"] == POSITIVE:
            exact[str(record["canonical_card_id"])].append(record)
    high = {card for card, rows in exact.items() if any(r["matcher_confidence_state"] == "HIGH_CONFIDENCE" for r in rows)}
    only_medium = {card for card, rows in exact.items() if rows and all(r["matcher_confidence_state"] == "MEDIUM_CONFIDENCE" for r in rows)}
    rejected_or_ambiguous = {card for card, rows in exact.items() if rows and all(r["matcher_confidence_state"] in {"REJECTED", "AMBIGUOUS"} for r in rows)}
    no_exact = set(cards) - set(exact)
    describe = lambda values: [{"canonical_card_id": card, "card_name": names[card]} for card in sorted(values)]
    return {
        "benchmark_cards": len(cards), "covered_card_count": len(high),
        "observed_benchmark_coverage": ratio(len(high), len(cards)),
        "conditional_coverage_among_cards_with_exact": ratio(len(high), len(exact)),
        "cards_with_zero_high_exact": describe(set(cards) - high),
        "cards_with_only_medium_exact": describe(only_medium),
        "cards_with_exact_all_rejected_or_ambiguous": describe(rejected_or_ambiguous),
        "cards_with_no_human_exact": describe(no_exact),
    }


def false_negative_cause(record: Mapping[str, Any]) -> str:
    reason = str(record["rejection_or_ambiguity_reason"])
    evidence = json.loads(str(record["identity_evidence"]))
    object_state = str(record["product_object_state"])
    if object_state != "SINGLE_RAW_CARD":
        return "product-object uncertainty"
    if evidence.get("set", {}).get("state") == "ABSENT":
        return "missing set evidence"
    if evidence.get("number", {}).get("state") == "ABSENT":
        return "missing number evidence"
    if evidence.get("variant", {}).get("state") in {"ABSENT", "UNRESOLVED", "CONFLICT"}:
        return "variant uncertainty"
    if reason == "INSUFFICIENT_INDEPENDENT_EVIDENCE":
        return "overly conservative identity evidence"
    return "other"


def with_metadata(payload: Mapping[str, Any], metadata: Mapping[str, Any]) -> dict[str, Any]:
    return {**metadata, **payload}


def dump(name: str, payload: Mapping[str, Any], metadata: Mapping[str, Any]) -> None:
    (OUT / name).write_text(json.dumps(with_metadata(payload, metadata), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    timestamp = datetime.now(timezone.utc).isoformat()
    code_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    gold_manifest = json.loads(GOLD_MANIFEST.read_text(encoding="utf-8"))
    actual_matcher_fingerprint = rule_fingerprint()
    if not (
        MATCHER_VERSION == freeze.get("matcher_version") == "index_fair_value_ebay_d2m_v2"
        and actual_matcher_fingerprint == freeze.get("matcher_fingerprint") == EXPECTED_MATCHER_FINGERPRINT
        and freeze.get("frozen_commit") == EXPECTED_FROZEN_COMMIT
    ):
        raise RuntimeError("MATCHER_FREEZE_MISMATCH")
    if not (
        gold_manifest.get("effective_row_count") == 350
        and gold_manifest.get("effective_gold_fingerprint") == EXPECTED_GOLD_FINGERPRINT
        and sha256_file(OUT / "ebay_gold_final_blind.csv") == gold_manifest.get("partition_fingerprint")
        and sha256_file(HISTORY) == gold_manifest.get("review_history_fingerprint")
        and sha256_file(AUDIT_HISTORY) == gold_manifest.get("audit_history_fingerprint")
    ):
        raise RuntimeError("GOLD_FREEZE_MISMATCH")

    review_events = read_history()
    human_rows = load_partition("FINAL_BLIND_TEST", purpose="human_review")
    row_ids = [str(row["benchmark_row_id"]) for row in human_rows]
    base = reconstruct_effective_state(review_events, "FINAL_BLIND_TEST", str(gold_manifest["reviewer_id"]), row_ids)
    audit_rows = build_audit_queue(human_rows, base["labels"], review_events, str(gold_manifest["reviewer_id"]))
    audit = reconstruct_audit_state(read_audit_history(), str(gold_manifest["reviewer_id"]), [str(row["benchmark_row_id"]) for row in audit_rows])
    gold = effective_labels(base["labels"], audit)
    if len(base["labels"]) != 350 or base["skipped"] or base["unlabeled"] or len(audit["decisions"]) != 42 or audit["unreviewed"]:
        raise RuntimeError("GOLD_RECONSTRUCTION_INCOMPLETE")
    if effective_gold_fingerprint(gold) != EXPECTED_GOLD_FINGERPRINT:
        raise RuntimeError("EFFECTIVE_GOLD_FINGERPRINT_MISMATCH")

    # Final evaluation is opened only with the frozen matcher proof.
    rows = load_partition("FINAL_BLIND_TEST", purpose="final_evaluation", freeze_manifest=FREEZE)

    def score() -> list[dict[str, Any]]:
        output = []
        for row in rows:
            result = classify_listing(
                {"card_name": row["target_card_name"], "set_name": row["target_set_name"], "card_number": row["target_card_number"], "treatment": row["target_treatment"]},
                {"title": row["listing_title"], "condition": row["condition"], "aspects": row["localized_aspects_json"], "itemId": row["listing_item_id"]},
            )
            output.append({
                "benchmark_row_id": row["benchmark_row_id"], "canonical_card_id": row["canonical_card_id"],
                "target_card_name": row["target_card_name"], "target_set_name": row["target_set_name"],
                "target_card_number": row["target_card_number"], "target_treatment": row["target_treatment"],
                "listing_title": row["listing_title"], "human_gold_label": gold[row["benchmark_row_id"]],
                "matcher_identity_state": result["identity_state"], "matcher_confidence_state": matcher_state(result),
                "product_object_state": result["product_object"]["state"], "condition_state": result["condition_state"],
                "identity_evidence": json.dumps(result["evidence"], sort_keys=True, separators=(",", ":")),
                "rejection_or_ambiguity_reason": result["reason"], "matcher_version": MATCHER_VERSION,
                "matcher_fingerprint": actual_matcher_fingerprint, "gold_fingerprint": EXPECTED_GOLD_FINGERPRINT,
                "code_commit": code_commit, "evaluation_timestamp": timestamp,
            })
        return output

    records = score()
    reproduced = score()
    if json.dumps(records, sort_keys=True) != json.dumps(reproduced, sort_keys=True):
        raise RuntimeError("NONDETERMINISTIC_PREDICTIONS")

    prediction_path = OUT / "ebay_d2f_final_blind_predictions.csv"
    with prediction_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]))
        writer.writeheader(); writer.writerows(records)

    metadata = {"matcher_version": MATCHER_VERSION, "matcher_fingerprint": actual_matcher_fingerprint,
                "gold_fingerprint": EXPECTED_GOLD_FINGERPRINT, "code_commit": code_commit,
                "evaluation_timestamp": timestamp}
    high = high_metrics(records)
    card_coverage = coverage(records)
    catastrophic_counts = {label: sum(r["human_gold_label"] == label and r["matcher_confidence_state"] == "HIGH_CONFIDENCE" for r in records) for label in CATASTROPHIC}
    catastrophic = {"counts": catastrophic_counts, "passed": not any(catastrophic_counts.values())}
    ambiguous_behavior = {"human_ambiguous_count": 11, "matcher_behavior": dict(sorted(Counter(r["matcher_confidence_state"] for r in records if r["human_gold_label"] == AMBIGUOUS).items()))}
    medium_rows = [r for r in records if r["matcher_confidence_state"] == "MEDIUM_CONFIDENCE"]
    medium_exact = sum(r["human_gold_label"] == POSITIVE for r in medium_rows)
    medium_fp = sum(r["human_gold_label"] in NEGATIVE for r in medium_rows)
    high_cards = {r["canonical_card_id"] for r in records if r["human_gold_label"] == POSITIVE and r["matcher_confidence_state"] == "HIGH_CONFIDENCE"}
    medium_cards = {r["canonical_card_id"] for r in medium_rows if r["human_gold_label"] == POSITIVE}
    medium = {"count": len(medium_rows), "exact_count": medium_exact, "false_positive_count": medium_fp,
              "precision": ratio(medium_exact, medium_exact + medium_fp),
              "incremental_card_coverage_count": len(medium_cards - high_cards), "authority": "DIAGNOSTIC_ONLY"}
    high_errors = [{key: r[key] for key in ("benchmark_row_id", "target_card_name", "target_set_name", "target_card_number", "listing_title", "human_gold_label", "product_object_state", "identity_evidence", "rejection_or_ambiguity_reason")} for r in records if r["matcher_confidence_state"] == "HIGH_CONFIDENCE" and r["human_gold_label"] != POSITIVE]
    fn_causes = Counter(false_negative_cause(r) for r in records if r["human_gold_label"] == POSITIVE and r["matcher_confidence_state"] != "HIGH_CONFIDENCE")
    stress_patterns = {
        "extended_art_or_custom_cases": r"extended[- ]?art|custom (?:card )?case",
        "choose_or_pick_your_card": r"choose (?:a|your) card|pick your card|you ?pick",
        "graded_cards": None, "wrong_card_numbers": None,
        "reverse_holo_or_parallel_mismatches": r"reverse holo|reverse foil|parallel|master ?ball|poke ?ball|stamped|pokemon center",
        "common_uncommon_rare_variant_ambiguity": None,
        "non_english_cards": None, "multi_card_offers": r"\b(?:lot|bundle|playset|collection|set of [2-9]|[2-9]x)\b",
    }
    stress = {}
    for name, pattern in stress_patterns.items():
        selected = []
        for record in records:
            include = bool(pattern and re.search(pattern, str(record["listing_title"]), re.I))
            include |= name == "graded_cards" and record["human_gold_label"] == "GRADED"
            include |= name == "wrong_card_numbers" and record["human_gold_label"] == "WRONG_CARD_NUMBER"
            include |= name == "common_uncommon_rare_variant_ambiguity" and record["target_treatment"] in {"common", "uncommon", "rare"} and record["human_gold_label"] in {AMBIGUOUS, "RELATED_BUT_WRONG_VARIANT"}
            include |= name == "non_english_cards" and record["human_gold_label"] == "WRONG_LANGUAGE"
            if include: selected.append(record)
        stress[name] = {"count": len(selected), "matcher_behavior": dict(sorted(Counter(r["matcher_confidence_state"] for r in selected).items()))}
    error_analysis = {"high_false_positives": high_errors, "false_negative_causes": dict(sorted(fn_causes.items())), "marketplace_stress_cases": stress, "descriptive_only": True}
    dev = json.loads((OUT / "ebay_d2m_v2_expanded_metrics.json").read_text(encoding="utf-8"))
    comparison = {"expanded_development": {"precision": dev["high"]["precision"], "wilson_95": dev["high"]["wilson_95"], "recall": dev["high"]["recall"], "card_coverage": dev["high"]["card_coverage"], "ambiguity_rate": ratio(dev["ambiguous_count"], 700), "rejection_rate": ratio(dev["rejected_count"], 700)},
                  "final_blind": {"precision": high["precision"], "wilson_95": high["precision_wilson_95"], "recall": high["recall"], "card_coverage": card_coverage["observed_benchmark_coverage"], "ambiguity_rate": ratio(sum(r["matcher_confidence_state"] == "AMBIGUOUS" for r in records), 350), "rejection_rate": ratio(sum(r["matcher_confidence_state"] == "REJECTED" for r in records), 350)}}
    gates = {"precision": high["precision"] >= .99, "wilson_lower": high["precision_wilson_95"][0] >= .98,
             "card_coverage": card_coverage["observed_benchmark_coverage"] >= .80,
             "catastrophic_errors": catastrophic["passed"]}
    passed = all(gates.values())

    dump("ebay_d2f_high_metrics.json", high, metadata)
    dump("ebay_d2f_medium_metrics.json", medium, metadata)
    dump("ebay_d2f_catastrophic_error_gate.json", catastrophic, metadata)
    dump("ebay_d2f_card_coverage.json", card_coverage, metadata)
    dump("ebay_d2f_ambiguous_behavior.json", ambiguous_behavior, metadata)
    dump("ebay_d2f_error_analysis.json", error_analysis, metadata)
    dump("ebay_d2f_dev_final_comparison.json", comparison, metadata)
    if passed:
        dump("ebay_identity_matcher_v2_authority_manifest.json", {
            "decision": "EBAY_IDENTITY_MATCHER_V2_VALIDATED", "gates": gates,
            "identity_matcher_status": "VALIDATED_HIGH_CONFIDENCE_IDENTITY_FILTER",
            "active_supply_status": "CANDIDATE_FOR_PRODUCTION_RESEARCH_COLLECTION",
            "asking_price_status": "REQUIRES_CONDITION_PAGINATION_DISTRIBUTION_AUTHORITY_STUDY",
            "fair_value_status": "REQUIRES_INCREMENTAL_F2D_FAIR_VALUE_EXPERIMENT",
            "completed_sales_status": "UNAVAILABLE_OR_UNVERIFIED",
        }, metadata)
    certification = f"""# eBay D2F Final Blind certification

Frozen matcher `{MATCHER_VERSION}` at `{EXPECTED_FROZEN_COMMIT}` was evaluated against
350 independently frozen Final Blind gold rows. Ambiguous human gold was excluded from
the 339-row primary binary denominator. Deterministic reproduction was identical.

HIGH accepted {high['accepted_count']}: TP {high['true_positives']}, FP {high['false_positives']},
TN {high['true_negatives']}, FN {high['false_negatives']}. Precision {high['precision']:.4%},
Wilson 95% CI [{high['precision_wilson_95'][0]:.4%}, {high['precision_wilson_95'][1]:.4%}],
recall {high['recall']:.4%}, specificity {high['specificity']:.4%}, F1 {high['f1']:.4%}.
Card coverage is {card_coverage['covered_card_count']}/70 ({card_coverage['observed_benchmark_coverage']:.4%}).
Catastrophic HIGH errors: {sum(catastrophic_counts.values())}. Decision: {'PASS' if passed else 'FAIL'}.

This result validates only the frozen HIGH-confidence identity-filtering layer. It does
not validate asking-price authority, Near Mint condition, pagination/depth, completed
sales, or Fair Value.
"""
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "EBAY_D2F_FINAL_BLIND_CERTIFICATION.md").write_text(certification, encoding="utf-8")
    handoff = """# Downstream eBay research handoff

Active supply identity is eligible for production-research candidacy only if the
certification authority manifest exists. Asking-price authority still requires a
condition/NM and pagination/distribution study. Supply count requires depth-stability
work. Fair Value requires a separate incremental experiment. Completed-sales authority
remains unavailable or unverified. No production mutation is authorized by this handoff.
"""
    (DOCS / "EBAY_D2F_DOWNSTREAM_RESEARCH_HANDOFF.md").write_text(handoff, encoding="utf-8")
    print(json.dumps({"passed": passed, "gates": gates, "high": high, "medium": medium,
                      "coverage": card_coverage, "ambiguous": ambiguous_behavior,
                      "catastrophic": catastrophic, "metadata": metadata}, indent=2))


if __name__ == "__main__":
    main()
