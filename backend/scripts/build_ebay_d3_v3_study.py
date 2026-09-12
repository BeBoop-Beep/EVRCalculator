"""Build D3 v3 development-only evidence and preregister the fresh blind design."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from backend.scripts.ebay_d3_matcher_v3 import (
    ACCESSORY_ONTOLOGY_VERSION, CONDITION_POLICY_VERSION, CONFIDENCE_POLICY_VERSION,
    GRADED_RULE_VERSION, MATCHER_VERSION, MULTIPLICITY_RULE_VERSION,
    PRODUCT_OBJECT_RULE_VERSION, QUERY_CONTRACT_VERSION, SET_ALIAS_REGISTRY_VERSION,
    VARIANT_RULE_VERSION, classify_listing, graded_evidence, multiplicity_evidence,
    rule_fingerprint,
)
from backend.scripts.ebay_final_gold_audit import (
    build_audit_queue, effective_labels, read_audit_history, reconstruct_audit_state,
)
from backend.scripts.ebay_gold_access import OUT, load_partition
from backend.scripts.ebay_gold_review_server import read_history, reconstruct_effective_state
from backend.scripts.prepare_ebay_d2h_benchmark import LABELS

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs/research/index_fair_value"
POSITIVE = "EXACT_TARGET_MATCH"
AMBIGUOUS = "AMBIGUOUS"
NEGATIVE = frozenset(set(LABELS) - {POSITIVE, AMBIGUOUS})
EXPECTED = {"DEVELOPMENT": 450, "VALIDATION": 250, "FINAL_BLIND_TEST": 350}


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def ratio(a: int, b: int) -> float:
    return round(a / b, 8) if b else 0.0


def wilson(successes: int, total: int) -> list[float]:
    z = 1.959963984540054
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return [round(center - margin, 8), round(center + margin, 8)]


def dump(name: str, payload: Any) -> None:
    (OUT / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def target(row: dict[str, Any]) -> dict[str, Any]:
    return {"card_name": row["target_card_name"], "set_name": row["target_set_name"],
            "card_number": row["target_card_number"], "treatment": row["target_treatment"]}


def listing(row: dict[str, Any]) -> dict[str, Any]:
    return {"title": row["listing_title"], "subtitle": row.get("subtitle"),
            "condition": row["condition"], "conditionId": row["condition_id"],
            "category": row["category_id"], "aspects": row["localized_aspects_json"],
            "buying_options": row["buying_options_json"], "itemId": row["listing_item_id"]}


def load_corpus() -> list[tuple[str, dict[str, Any], str]]:
    review_events = read_history()
    audit_events = read_audit_history()
    corpus = []
    for partition, expected in EXPECTED.items():
        rows = load_partition(partition, purpose="human_review")
        state = reconstruct_effective_state(review_events, partition, "Donny", [row["benchmark_row_id"] for row in rows])
        labels = {row_id: event["label"] for row_id, event in state["labels"].items()}
        if partition == "FINAL_BLIND_TEST":
            queue = build_audit_queue(rows, state["labels"], review_events, "Donny")
            audit = reconstruct_audit_state(audit_events, "Donny", [row["benchmark_row_id"] for row in queue])
            labels = effective_labels(state["labels"], audit)
            if len(audit["decisions"]) != 42 or audit["unreviewed"]:
                raise RuntimeError("FINAL_GOLD_AUDIT_INCOMPLETE")
        if len(rows) != expected or len(labels) != expected or state["skipped"] or state["unlabeled"]:
            raise RuntimeError(f"CORPUS_INCOMPLETE:{partition}")
        corpus.extend((partition, dict(row), labels[row["benchmark_row_id"]]) for row in rows)
    return corpus


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frozen-commit", required=True)
    args = parser.parse_args()
    corpus = load_corpus()
    counts = Counter(gold for _, _, gold in corpus)
    membership = [f"{partition}:{row['benchmark_row_id']}:{row['listing_item_id']}" for partition, row, _ in corpus]
    labels = [f"{row['benchmark_row_id']}:{gold}" for _, row, gold in corpus]
    taxonomy = {"version": "ebay_final_blind_gold_taxonomy_v1", "labels": list(LABELS)}
    development_manifest = {
        "version": "ebay_d3_v3_development_manifest_v1", "total_rows": len(corpus),
        "source_partition_rows": EXPECTED, "exact_count": counts[POSITIVE],
        "definitive_negative_count": sum(counts[label] for label in NEGATIVE),
        "ambiguous_count": counts[AMBIGUOUS], "binary_denominator": len(corpus) - counts[AMBIGUOUS],
        "label_breakdown": dict(sorted(counts.items())),
        "membership_fingerprint": hashlib.sha256("\n".join(sorted(membership)).encode()).hexdigest(),
        "effective_labels_fingerprint": hashlib.sha256("\n".join(sorted(labels)).encode()).hexdigest(),
        "taxonomy_fingerprint": digest(taxonomy), "taxonomy": taxonomy,
        "development_corpus_fingerprint": digest(sorted(zip(membership, labels))),
        "independent_certification_evidence": False,
        "methodology_note": "All prior Development, Validation, and Final Blind rows are v3 development evidence.",
    }
    dump("ebay_d3_v3_development_manifest.json", development_manifest)

    evaluated = []
    matrix = Counter(); states = Counter(); high_cards = set(); high_errors = []
    for partition, row, gold in corpus:
        result = classify_listing(target(row), listing(row))
        evaluated.append((partition, row, gold, result))
        state = result["identity_state"]; states[state] += 1
        if gold != AMBIGUOUS:
            positive = gold == POSITIVE; accepted = state == "HIGH_CONFIDENCE"
            matrix["tp" if positive and accepted else "fn" if positive else "fp" if accepted else "tn"] += 1
        if state == "HIGH_CONFIDENCE" and gold == POSITIVE:
            high_cards.add(row["canonical_card_id"])
        if state == "HIGH_CONFIDENCE" and gold != POSITIVE:
            high_errors.append({"benchmark_row_id": row["benchmark_row_id"], "gold": gold,
                                "listing_title": row["listing_title"], "reason": result["reason"]})
    tp, fp, tn, fn = (matrix[key] for key in ("tp", "fp", "tn", "fn"))
    metrics = {
        "version": "ebay_d3_v3_development_metrics_v1", "development_only": True,
        "high": {"accepted": tp + fp, "tp": tp, "fp": fp, "tn": tn, "fn": fn,
                 "precision": ratio(tp, tp + fp), "wilson_95": wilson(tp, tp + fp),
                 "recall": ratio(tp, counts[POSITIVE]), "card_coverage_count": len(high_cards),
                 "card_coverage": ratio(len(high_cards), 70),
                 "false_positive_breakdown": dict(sorted(Counter(error["gold"] for error in high_errors).items())),
                 "false_positive_rows": high_errors},
        "matcher_state_breakdown": dict(sorted(states.items())),
        "gold_by_matcher_state": {state: dict(sorted(Counter(gold for _, _, gold, result in evaluated if result["identity_state"] == state).items())) for state in sorted(states)},
        "catastrophic_high_counts": {label: sum(gold == label and result["identity_state"] == "HIGH_CONFIDENCE" for _, _, gold, result in evaluated) for label in sorted(NEGATIVE | {AMBIGUOUS})},
        "image_only_residual_is_not_structurally_detectable": True,
    }
    dump("ebay_d3_v3_development_metrics.json", metrics)

    graded_rows = [(p, row, result) for p, row, gold, result in evaluated if gold == "GRADED"]
    graded_examples = []
    for partition, row, result in graded_rows:
        evidence = graded_evidence(listing(row))
        graded_examples.append({
            "partition": partition, "benchmark_row_id": row["benchmark_row_id"],
            "listing_title": row["listing_title"], "condition": row["condition"],
            "condition_id": row["condition_id"], "category_id": row["category_id"],
            "item_aspects": json.loads(row["localized_aspects_json"] or "[]"),
            "buying_options": json.loads(row["buying_options_json"] or "[]"),
            "subtitle_available": bool(row.get("subtitle")), "affirmative_graded_evidence": evidence,
            "v3_product_object": result["product_object"]["state"],
            "v3_identity_state": result["identity_state"],
        })
    unresolved_graded = [row for row in graded_examples if not row["affirmative_graded_evidence"]["affirmative"]]
    graded_analysis = {
        "version": "ebay_d3_v3_graded_detection_analysis_v1", "human_graded_rows": len(graded_rows),
        "affirmative_graded_evidence_rows": len(graded_rows) - len(unresolved_graded),
        "no_affirmative_graded_evidence_rows": len(unresolved_graded),
        "image_only_graded_risk_rows": [row["benchmark_row_id"] for row in unresolved_graded],
        "residual_high_image_only_risk_rows": [row["benchmark_row_id"] for row in unresolved_graded if row["v3_identity_state"] == "HIGH_CONFIDENCE"],
        "residual_high_risk_rate_among_human_graded": ratio(sum(row["v3_identity_state"] == "HIGH_CONFIDENCE" for row in unresolved_graded), len(graded_rows)),
        "d2_0310_finding": "Condition=Ungraded, conditionId=4000, empty category/aspects, no subtitle or captured grade metadata; only human image inspection revealed the slab.",
        "policy": "Any affirmative title, condition, conditionId, category, or grading-aspect evidence is GRADED_CARD. Image-only risk is documented, not fabricated.",
        "available_browse_fields": ["title", "condition", "conditionId", "category", "item aspects", "buying options", "seller fields", "image URL"],
        "unavailable_or_empty_in_capture": ["subtitle", "variation/selection indicators", "image-derived metadata"],
        "examples": graded_examples,
    }
    dump("ebay_d3_v3_graded_detection_analysis.json", graded_analysis)

    multi_rows = [(p, row, result) for p, row, gold, result in evaluated if gold == "LOT_OR_BUNDLE"]
    multiplicity_analysis = {
        "version": "ebay_d3_v3_multiplicity_analysis_v1", "human_multi_card_rows": len(multi_rows),
        "v3_multi_card_detected": sum(result["product_object"]["state"] == "MULTI_CARD_OFFER" for _, _, result in multi_rows),
        "v3_high_false_positives": sum(result["identity_state"] == "HIGH_CONFIDENCE" for _, _, result in multi_rows),
        "d2_0674_finding": "D2-0674 showed that V2 handled count-before-X but not X-before-count; X2 was parsed as a single raw card.",
        "contextual_patterns": ["X2", "2X", "x 2", "2 cards", "pair", "two cards", "set of 2", "card-contextual 2-pack", "playset", "4x", "multiple", "lot", "bundle", "reverse holo and holo"],
        "collector_number_control": "Fractional collector numbers such as 2/198 are not multiplicity evidence.",
        "structured_fields": "Only explicit lot/card/package quantities and selectable/variation flags qualify; inventory quantity is not used.",
        "examples": [{"partition": p, "benchmark_row_id": row["benchmark_row_id"], "listing_title": row["listing_title"],
                      "evidence": multiplicity_evidence(listing(row)), "v3_product_object": result["product_object"]["state"]} for p, row, result in multi_rows],
    }
    dump("ebay_d3_v3_multiplicity_analysis.json", multiplicity_analysis)

    object_matrix = Counter((gold, result["product_object"]["state"]) for _, _, gold, result in evaluated)
    product_rules = {
        "version": PRODUCT_OBJECT_RULE_VERSION,
        "states": ["SINGLE_RAW_CARD", "GRADED_CARD", "MULTI_CARD_OFFER", "SEALED_TCG_PRODUCT", "CARD_ACCESSORY", "UNKNOWN_PRODUCT_OBJECT"],
        "high_eligible": ["SINGLE_RAW_CARD"],
        "evaluation_order": ["GRADED_CARD", "CARD_ACCESSORY", "SEALED_TCG_PRODUCT", "MULTI_CARD_OFFER", "SINGLE_RAW_CARD"],
        "graded_rule_version": GRADED_RULE_VERSION, "multiplicity_rule_version": MULTIPLICITY_RULE_VERSION,
        "accessory_rule_version": ACCESSORY_ONTOLOGY_VERSION,
        "ambiguity_policy": "Unresolved identity, selection, conflict, or product object never reaches HIGH.",
        "gold_object_matrix": {f"{gold}|{state}": count for (gold, state), count in sorted(object_matrix.items())},
    }
    dump("ebay_d3_v3_product_object_rules.json", product_rules)

    power = {
        "version": "ebay_d3_new_certification_power_analysis_v1", "confidence_level": .95,
        "precision_gate": .99, "wilson_lower_gate": .98,
        "minimum_high_n_with_zero_false_positives": 189,
        "minimum_high_n_with_one_false_positive": 280,
        "planned_precision_cohort_n": 300,
        "wilson_lower_at_300_of_300": wilson(300, 300)[0],
        "wilson_lower_at_299_of_300": wilson(299, 300)[0],
        "justification": "A 300-HIGH cohort allows one false positive while retaining a Wilson lower bound above 98%; the catastrophic gate independently still requires zero.",
    }
    dump("ebay_d3_new_certification_power_analysis.json", power)

    design = {
        "version": "ebay_d3_new_blind_benchmark_design_v1",
        "development_item_id_exclusion_count": len({row["listing_item_id"] for _, row, _ in corpus}),
        "precision_cohort": {"target_rows": 300, "population": "fresh frozen-v3 HIGH predictions",
                             "selection": "deterministic SHA-256 ordering with preregistered strata across cards, sets, treatments, sellers, and title patterns; no human labels exist at selection",
                             "reviewer_blinding": ["matcher state", "confidence tier", "price", "Fair Value", "TCGplayer"]},
        "coverage_cohort": {"target_rows": 420, "target_per_card": 6, "cards": 70,
                            "selection": "independent per-card SHA-256 ordering across all fresh results before human labels"},
        "overlap": "Allowed only when independently selected by both deterministic rules; row is reviewed once.",
        "expected_unique_human_reviews": 600, "hard_maximum_unique_human_reviews": 720,
        "api_plan": {"exact_maximum_browse_calls": 140, "cards_queried": 70, "pages_per_card": 2,
                     "page_size": 100, "maximum_returned_listings": 14000,
                     "returned_listings": "RECORDED_AFTER_CAPTURE", "deduplicated_fresh_listings": "RECORDED_AFTER_CAPTURE",
                     "high_candidates": "RECORDED_AFTER_FROZEN_V3_PREDICTION", "daily_default_limit": 5000},
        "freshness": {"new_capture_required": True, "observed_at_required": True,
                      "exclude_all_1050_prior_listing_item_ids": True,
                      "secondary_dedupe": "normalized seller_id + normalized title",
                      "prior_rows_are_never_certification_evidence": True},
        "preregistered_gate": {"high_precision_minimum": .99, "wilson_95_lower_minimum": .98,
                               "card_coverage_minimum": .80, "catastrophic_high_false_positives_maximum": 0,
                               "catastrophic_classes": ["GRADED", "LOT_OR_BUNDLE", "WRONG_CARD_NUMBER", "RELATED_BUT_WRONG_VARIANT", "WRONG_SET", "WRONG_LANGUAGE", "SEALED_OR_ACCESSORY", "AMBIGUOUS"]},
        "medium_authority": "DIAGNOSTIC_ONLY",
    }
    design["benchmark_design_fingerprint"] = digest(design)
    dump("ebay_d3_new_blind_benchmark_design.json", design)

    freeze = {
        "version": "ebay_d3_v3_freeze_manifest_v1", "matcher_version": MATCHER_VERSION,
        "matcher_fingerprint": rule_fingerprint(), "frozen_commit": args.frozen_commit,
        "development_corpus_fingerprint": development_manifest["development_corpus_fingerprint"],
        "benchmark_design_fingerprint": design["benchmark_design_fingerprint"],
        "query_contract_version": QUERY_CONTRACT_VERSION, "product_object_rule_version": PRODUCT_OBJECT_RULE_VERSION,
        "graded_rule_version": GRADED_RULE_VERSION, "multiplicity_rule_version": MULTIPLICITY_RULE_VERSION,
        "accessory_rule_version": ACCESSORY_ONTOLOGY_VERSION, "variant_rule_version": VARIANT_RULE_VERSION,
        "alias_registry_version": SET_ALIAS_REGISTRY_VERSION, "condition_policy_version": CONDITION_POLICY_VERSION,
        "confidence_policy_version": CONFIDENCE_POLICY_VERSION, "logic_frozen": True,
        "new_certification_labels_viewed": False, "production_authority": False,
    }
    dump("ebay_d3_v3_freeze_manifest.json", freeze)

    study = f"""# eBay D3 v3 redevelopment study

All 1,050 previously labeled listings are v3 development evidence: {counts[POSITIVE]}
exact, {sum(counts[label] for label in NEGATIVE)} definitive negative, and
{counts[AMBIGUOUS]} ambiguous. None remains independent certification evidence.

V2's `D2-0674` failure was a directional multiplicity gap: it recognized `2x` but not
`X2`. V3 uses contextual bidirectional quantities, explicit card counts, pairs, sets,
packs, playsets, and selectable offers while protecting collector-number fractions.

`D2-0310` has condition `Ungraded`, conditionId `4000`, empty category/aspects, no
subtitle, and no captured grading metadata. Its slab status came only from human image
inspection. V3 rejects every affirmative structured/textual graded signal, but records
this irreducible deterministic limitation as `IMAGE_ONLY_GRADED_RISK`.

Development-only HIGH: {tp + fp} accepted, {tp} TP, {fp} FP, precision
{ratio(tp,tp+fp):.4%}, Wilson 95% CI [{wilson(tp,tp+fp)[0]:.4%},
{wilson(tp,tp+fp)[1]:.4%}], recall {ratio(tp,counts[POSITIVE]):.4%}, and card coverage
{len(high_cards)}/70 ({ratio(len(high_cards),70):.4%}). The sole HIGH error is the
image-only graded row. These figures are development diagnostics, not authority.

The next certification is preregistered as a fresh 300-HIGH precision cohort plus an
independent 420-row card-stratified coverage/failure cohort. Expected unique review
burden is about 600, capped at 720. The capture budget is exactly 140 Browse calls,
well below the 5,000-call daily default.
"""
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "EBAY_D3_V3_REDEVELOPMENT_STUDY.md").write_text(study, encoding="utf-8")
    handoff = f"""# eBay D3 new blind review handoff

Frozen matcher `{MATCHER_VERSION}` has fingerprint `{rule_fingerprint()}` and
implementation commit `{args.frozen_commit}`. Benchmark design fingerprint:
`{design['benchmark_design_fingerprint']}`.

No new certification labels have been viewed. First obtain a fresh capture using the
140-call preregistered budget, exclude all prior item IDs, run frozen v3 before labels
exist, and materialize `PRECISION_BLIND` and `COVERAGE_BLIND` without matcher or price
fields. Human review remains resume-safe and append-only. MEDIUM is diagnostic-only.
"""
    (DOCS / "EBAY_D3_NEW_BLIND_REVIEW_HANDOFF.md").write_text(handoff, encoding="utf-8")
    print(json.dumps({"development_manifest": development_manifest, "metrics": metrics,
                      "freeze": freeze, "design": design}, indent=2))


if __name__ == "__main__":
    main()
