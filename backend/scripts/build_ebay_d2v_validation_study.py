"""Evaluate the frozen D2M matcher on Validation without changing its logic."""
from __future__ import annotations
import csv, json, math
from collections import Counter, defaultdict
from pathlib import Path
from backend.scripts.ebay_d2m_matcher import (
    CONDITION_POLICY_VERSION, MATCHER_VERSION, QUERY_CONTRACT_VERSION,
    SET_ALIAS_REGISTRY_VERSION, VARIANT_RULE_VERSION, classify_listing, rule_fingerprint,
)
from backend.scripts.ebay_gold_access import OUT, load_partition
from backend.scripts.ebay_gold_review_server import HISTORY, read_history, reconstruct_effective_state

DOCS=Path(__file__).resolve().parents[2]/"docs/research/index_fair_value"
EXPECTED_VERSION="index_fair_value_ebay_d2m_v1"
EXPECTED_FINGERPRINT="d47384a38912b59bb073c0b7a655e3120424154fa1617faaca541c86d53f2e1c"
FROZEN_MATCHER_COMMIT="705b124e7e939d86944ffc0c647b78ef2ae1052b"
POS="EXACT_TARGET_MATCH";AMB="AMBIGUOUS"
NEG={"GRADED","WRONG_CARD_NUMBER","SEALED_OR_ACCESSORY","LOT_OR_BUNDLE",
     "RELATED_BUT_WRONG_VARIANT","WRONG_LANGUAGE","WRONG_SET","CONDITION_INELIGIBLE","OTHER"}

def dump(name,value):
    (OUT/name).write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def ratio(a,b): return round(a/b,8) if b else 0.0
def wilson(a,n):
    z=1.959963984540054;p=a/n;d=1+z*z/n;c=(p+z*z/(2*n))/d
    m=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return [round(c-m,8),round(c+m,8)]
def target(r):
    return {"card_name":r["target_card_name"],"set_name":r["target_set_name"],
            "card_number":r["target_card_number"],"treatment":r["target_treatment"]}
def listing(r):
    return {"title":r["listing_title"],"condition":r["condition"],
            "aspects":r["localized_aspects_json"],"itemId":r["listing_item_id"]}

def main():
    if MATCHER_VERSION!=EXPECTED_VERSION or rule_fingerprint()!=EXPECTED_FINGERPRINT:
        raise RuntimeError("FROZEN_MATCHER_FINGERPRINT_MISMATCH")
    rows=load_partition("VALIDATION",purpose="human_review")
    ids=[r["benchmark_row_id"] for r in rows]
    state=reconstruct_effective_state(read_history(HISTORY),"VALIDATION","Donny",ids)
    if (len(rows),len(state["labels"]),len(state["skipped"]),len(state["unlabeled"]))!=(250,250,0,0):
        raise RuntimeError("VALIDATION_GOLD_INCOMPLETE")
    gold={k:v["label"] for k,v in state["labels"].items()}
    distribution=Counter(gold.values())

    predictions=[];matrix=Counter();by_state=defaultdict(Counter);rejections=Counter()
    high_cards=set();medium_cards=set();high_errors=[];rejected_exact=[]
    for r in rows:
        label=gold[r["benchmark_row_id"]]
        result=classify_listing(target(r),listing(r))
        matcher_state=result["identity_state"]
        if matcher_state=="HIGH_CONFIDENCE" and label==POS: high_cards.add(r["canonical_card_id"])
        if matcher_state=="MEDIUM_CONFIDENCE" and label==POS: medium_cards.add(r["canonical_card_id"])
        if label!=AMB:
            positive=label==POS; accepted=matcher_state=="HIGH_CONFIDENCE"
            matrix["tp" if positive and accepted else "fn" if positive else "fp" if accepted else "tn"]+=1
        by_state[matcher_state][label]+=1
        if matcher_state=="REJECT": rejections[result["reason"]]+=1
        disagreement=(
            "HUMAN_AMBIGUOUS" if label==AMB else
            "HIGH_FALSE_POSITIVE" if matcher_state=="HIGH_CONFIDENCE" and label in NEG else
            "EXACT_NOT_HIGH" if label==POS and matcher_state!="HIGH_CONFIDENCE" else
            "NONE"
        )
        row_out={"benchmark_row_id":r["benchmark_row_id"],"canonical_card_id":r["canonical_card_id"],
          "target_card_name":r["target_card_name"],"target_set_name":r["target_set_name"],
          "target_card_number":r["target_card_number"],"target_treatment":r["target_treatment"],
          "listing_title":r["listing_title"],"human_gold_label":label,
          "matcher_state":matcher_state,"condition_state":result["condition_state"],
          "matcher_reason":result["reason"],"identity_evidence":json.dumps(result["evidence"],sort_keys=True),
          "disagreement_type":disagreement}
        predictions.append(row_out)
        if disagreement=="HIGH_FALSE_POSITIVE": high_errors.append(row_out)
        if label==POS and matcher_state=="REJECT": rejected_exact.append(row_out)
    with (OUT/"ebay_d2v_validation_predictions.csv").open("w",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=list(predictions[0]));writer.writeheader();writer.writerows(predictions)

    # Extend the existing blinded queue without exposing gold labels or matcher states.
    queue_path=OUT/"ebay_d2m_second_review_queue.csv"
    with queue_path.open(encoding="utf-8",newline="") as f:
        queue=list(csv.DictReader(f))
    queued_ids={item["benchmark_row_id"] for item in queue}
    source_by_id={row["benchmark_row_id"]:row for row in rows}
    for prediction in predictions:
        if prediction["disagreement_type"]=="NONE" or prediction["benchmark_row_id"] in queued_ids:
            continue
        row=source_by_id[prediction["benchmark_row_id"]]
        queue.append({"benchmark_row_id":row["benchmark_row_id"],"canonical_card_id":row["canonical_card_id"],
          "target_card_name":row["target_card_name"],"target_set_name":row["target_set_name"],
          "target_card_number":row["target_card_number"],"target_treatment":row["target_treatment"],
          "listing_title":row["listing_title"],"condition":row["condition"],"image_url":row["image_url"],
          "item_url":row["item_url"],"review_reason":"VALIDATION_"+prediction["disagreement_type"],
          "review_status":"PENDING_SECOND_REVIEW"})
    with queue_path.open("w",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(queue[0]));writer.writeheader();writer.writerows(queue)

    tp,fp,tn,fn=(matrix[x] for x in ("tp","fp","tn","fn"))
    high={"version":"ebay_d2v_high_metrics_v1","matcher_version":MATCHER_VERSION,
      "matcher_fingerprint":rule_fingerprint(),"ambiguous_excluded":distribution[AMB],
      "accepted_count":sum(v for (s,_),v in Counter((x["matcher_state"],x["human_gold_label"]) for x in predictions).items() if s=="HIGH_CONFIDENCE"),
      "true_positives":tp,"false_positives":fp,"true_negatives":tn,"false_negatives":fn,
      "precision":ratio(tp,tp+fp),"wilson_95":wilson(tp,tp+fp),"recall":ratio(tp,tp+fn),
      "specificity":ratio(tn,tn+fp),"f1":ratio(2*tp,2*tp+fp+fn),
      "card_coverage_count":len(high_cards),"card_coverage":ratio(len(high_cards),70),
      "gate":{"precision_minimum":.99,"wilson_lower_minimum":.98,"card_coverage_minimum":.80,
              "catastrophic_errors_maximum":0},
      "catastrophic_error_count":len(high_errors),"passed":False,
      "decision":"LOGIC_FAILURE_REDEVELOPMENT_REQUIRED"}
    dump("ebay_d2v_high_metrics.json",high)

    medium_n=sum(by_state["MEDIUM_CONFIDENCE"].values());medium_tp=by_state["MEDIUM_CONFIDENCE"][POS]
    medium_def=sum(v for k,v in by_state["MEDIUM_CONFIDENCE"].items() if k!=AMB)
    medium={"version":"ebay_d2v_medium_metrics_v1","count":medium_n,
      "true_positives":medium_tp,"precision":ratio(medium_tp,medium_def),
      "recall_contribution":ratio(medium_tp,distribution[POS]),
      "false_positive_breakdown":dict(Counter(k for k,v in by_state["MEDIUM_CONFIDENCE"].items() for _ in range(v) if k in NEG)),
      "incremental_card_coverage_count":len(medium_cards-high_cards),
      "combined_card_coverage_count":len(high_cards|medium_cards),
      "recommendation":"DIAGNOSTIC_ONLY"}
    dump("ebay_d2v_medium_metrics.json",medium)

    error={"version":"ebay_d2v_error_analysis_v1",
      "high_false_positives":high_errors,
      "high_false_positive_breakdown":dict(Counter(x["human_gold_label"] for x in high_errors)),
      "human_ambiguous_count":distribution[AMB],
      "matcher_ambiguous_count":sum(by_state["AMBIGUOUS"].values()),
      "matcher_ambiguity_rate":ratio(sum(by_state["AMBIGUOUS"].values()),250),
      "rejected_exact_count":len(rejected_exact),
      "rejection_reason_distribution":dict(rejections),
      "structural_defect":"Extended Art Custom Case is not covered by the frozen accessory rejection pattern.",
      "rule_change_in_this_task":False}
    dump("ebay_d2v_error_analysis.json",error)

    all_cards={r["canonical_card_id"] for r in rows}
    any_states=defaultdict(set)
    for x,r in zip(predictions,rows):
        if x["human_gold_label"]==POS:any_states[r["canonical_card_id"]].add(x["matcher_state"])
    zero=sorted(all_cards-high_cards)
    only_medium=sorted(c for c in zero if "MEDIUM_CONFIDENCE" in any_states[c])
    only_low=sorted(c for c in zero if "MEDIUM_CONFIDENCE" not in any_states[c])
    coverage={"version":"ebay_d2v_card_coverage_v1","total_cards":70,
      "high_covered_count":len(high_cards),"high_coverage":ratio(len(high_cards),70),
      "zero_high_card_ids":zero,"only_medium_card_ids":only_medium,
      "only_rejected_or_ambiguous_card_ids":only_low}
    dump("ebay_d2v_card_coverage.json",coverage)

    dev=json.loads((OUT/"ebay_d2m_development_benchmark.json").read_text(encoding="utf-8"))
    comparison={"version":"ebay_d2v_dev_validation_comparison_v1",
      "development":{"precision":dev["high"]["precision"],"recall":dev["high"]["recall"],
                     "card_coverage":dev["high"]["card_coverage"],"ambiguity_rate":dev["ambiguous"]["rate"]},
      "validation":{"precision":high["precision"],"recall":high["recall"],
                    "card_coverage":high["card_coverage"],"ambiguity_rate":error["matcher_ambiguity_rate"]},
      "delta_validation_minus_development":{
        "precision":round(high["precision"]-dev["high"]["precision"],8),
        "recall":round(high["recall"]-dev["high"]["recall"],8),
        "card_coverage":round(high["card_coverage"]-dev["high"]["card_coverage"],8),
        "ambiguity_rate":round(error["matcher_ambiguity_rate"]-dev["ambiguous"]["rate"],8)},
      "finding":"Material degradation plus catastrophic accessory false positives."}
    dump("ebay_d2v_dev_validation_comparison.json",comparison)

    fp_table="\n".join(f"| {x['target_card_name']} | {x['listing_title']} | {x['human_gold_label']} | {x['identity_evidence']} | {x['matcher_reason']} |" for x in high_errors)
    study=f"""# eBay D2V frozen-matcher Validation study

Validation gold reconstructed at 250/250, with {distribution[POS]} positives,
{sum(distribution[x] for x in NEG)} negatives, and {distribution[AMB]} ambiguous row
excluded from binary metrics. The matcher remained {MATCHER_VERSION}, fingerprint
{rule_fingerprint()}; no matcher, alias, variant, condition, or query rule changed.

## HIGH result

Accepted {high['accepted_count']}: TP {tp}, FP {fp}, TN {tn}, FN {fn}. Precision
{high['precision']:.4%}, Wilson 95% CI [{high['wilson_95'][0]:.4%},
{high['wilson_95'][1]:.4%}], recall {high['recall']:.4%}, specificity
{high['specificity']:.4%}, F1 {high['f1']:.4%}, card coverage {len(high_cards)}/70
({high['card_coverage']:.4%}).

| Target card | Listing title | Human label | Matcher evidence | Accepted reason |
|---|---|---|---|---|
{fp_table}

Both false positives are catastrophic SEALED_OR_ACCESSORY cases. Precision, Wilson
lower bound, card coverage, and zero-catastrophic-error gates fail. This is a structural
logic defect, not an allowed threshold-policy choice. No Validation-derived patch was made.

MEDIUM has {medium_n} rows, precision {medium['precision']:.4%}, recall contribution
{medium['recall_contribution']:.4%}, and {medium['incremental_card_coverage_count']} incremental
cards; it remains diagnostic-only. Matcher ambiguity is {error['matcher_ambiguity_rate']:.4%}.

Final Blind remains sealed. Matcher v1 cannot be frozen for Final evaluation. Return to
Development with a new matcher version, then repeat independent Validation while keeping
the 350-row Final Blind partition untouched.
"""
    DOCS.mkdir(parents=True,exist_ok=True)
    (DOCS/"EBAY_D2V_VALIDATION_STUDY.md").write_text(study,encoding="utf-8")
    handoff=f"""# eBay D2V Final Blind handoff

Status: BLOCKED — DO NOT UNLOCK FINAL BLIND.

The benchmark manifest records 350 Final Blind rows. Their labels were not loaded or
evaluated. Frozen matcher v1 failed Validation with two catastrophic accessory false
positives and 54/70 HIGH card coverage. No final matcher freeze manifest was created.

Required next step: return to Development, create a new matcher version without using
Final Blind evidence, freeze it, and rerun an independent Validation protocol. Only a
passing committed freeze manifest containing matcher_version, matcher_fingerprint, and
frozen_commit may unlock Final Blind evaluation.

Failed frozen input commit: {FROZEN_MATCHER_COMMIT}
Query contract retained: {QUERY_CONTRACT_VERSION}
Alias registry retained: {SET_ALIAS_REGISTRY_VERSION}
Variant rules retained: {VARIANT_RULE_VERSION}
Condition policy retained: {CONDITION_POLICY_VERSION}
"""
    (DOCS/"EBAY_D2V_FINAL_BLIND_HANDOFF.md").write_text(handoff,encoding="utf-8")
    print(json.dumps({"high":high,"medium":medium,"decision":"REDEVELOPMENT_REQUIRED"},indent=2))

if __name__=="__main__":main()
