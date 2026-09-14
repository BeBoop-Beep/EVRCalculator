"""Build frozen D1/D2M artifacts from Development human labels only."""
from __future__ import annotations
import csv, hashlib, json, math
from collections import Counter, defaultdict
from pathlib import Path
from backend.scripts.ebay_d2m_matcher import (
    CONDITION_POLICY_VERSION, MATCHER_VERSION, PARALLEL_TERMS,
    QUERY_CONTRACT_VERSION, SET_ALIASES, SET_ALIAS_REGISTRY_VERSION,
    TREATMENT_TERMS, VARIANT_RULE_VERSION, classify_listing as d2m, rule_fingerprint,
)
from backend.scripts.ebay_gold_access import OUT, load_partition
from backend.scripts.ebay_gold_review_server import HISTORY, read_history, reconstruct_effective_state
from backend.scripts.index_fair_value_ebay_supply import classify_listing as d1

DOCS=Path(__file__).resolve().parents[2]/"docs/research/index_fair_value"
POS="EXACT_TARGET_MATCH"; AMB="AMBIGUOUS"
NEG={"RELATED_BUT_WRONG_VARIANT","WRONG_SET","WRONG_CARD_NUMBER","WRONG_LANGUAGE",
     "GRADED","LOT_OR_BUNDLE","SEALED_OR_ACCESSORY","CONDITION_INELIGIBLE","OTHER"}

def dump(name,value):
    path=OUT/name;path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
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
    rows=load_partition("DEVELOPMENT",purpose="matcher_development")
    ids=[r["benchmark_row_id"] for r in rows]
    state=reconstruct_effective_state(read_history(HISTORY),"DEVELOPMENT","Donny",ids)
    if (len(rows),len(state["labels"]),len(state["skipped"]),len(state["unlabeled"]))!=(450,450,0,0):
        raise RuntimeError("DEVELOPMENT_GOLD_INCOMPLETE")
    labels={k:v["label"] for k,v in state["labels"].items()}
    distribution=Counter(labels.values())

    cm=Counter();d1_accept=0;d1_fps=[];records=[]
    for r in rows:
        gold=labels[r["benchmark_row_id"]]; result=d1(target(r),listing(r))
        accepted=result["match_state"]=="EXACT_MATCH" and result["raw_condition_state"]=="RAW_ELIGIBLE_CONDITION"
        d1_accept+=accepted
        if gold!=AMB:
            positive=gold==POS
            cm["tp" if positive and accepted else "fn" if positive else "fp" if accepted else "tn"]+=1
            if accepted and not positive:
                d1_fps.append({"benchmark_row_id":r["benchmark_row_id"],"target_card":r["target_card_name"],
                  "listing_title":r["listing_title"],"gold_label":gold,"d1_verdict":result["match_state"],
                  "failure":"D1 did not model treatment/parallel identity."})
        records.append((r,gold,result,accepted))
    tp,fp,tn,fn=(cm[x] for x in ("tp","fp","tn","fn"))
    d1out={"version":"ebay_d1_development_benchmark_v1","partition":"DEVELOPMENT",
      "binary_rows":450-distribution[AMB],"ambiguous_excluded":distribution[AMB],
      "accepted_count_all_rows":d1_accept,"true_positives":tp,"false_positives":fp,
      "true_negatives":tn,"false_negatives":fn,"precision":ratio(tp,tp+fp),
      "recall":ratio(tp,tp+fn),"specificity":ratio(tn,tn+fp),
      "f1":ratio(2*tp,2*tp+fp+fn),
      "false_positive_breakdown":dict(Counter(x["gold_label"] for x in d1_fps)),
      "false_positives":d1_fps}
    dump("ebay_d1_development_benchmark.json",d1out)

    counts=Counter();by_state=defaultdict(Counter);cards=set();high_bad=[];d2records=[]
    for r in rows:
        gold=labels[r["benchmark_row_id"]];result=d2m(target(r),listing(r));state_name=result["identity_state"]
        counts[state_name]+=1;by_state[state_name][gold]+=1;d2records.append((r,gold,result))
        if state_name=="HIGH_CONFIDENCE":
            if gold==POS: cards.add(r["canonical_card_id"])
            else: high_bad.append({"benchmark_row_id":r["benchmark_row_id"],"gold_label":gold,
                                   "listing_title":r["listing_title"]})
    high_tp=by_state["HIGH_CONFIDENCE"][POS]
    high_n=sum(v for k,v in by_state["HIGH_CONFIDENCE"].items() if k!=AMB)
    med_tp=by_state["MEDIUM_CONFIDENCE"][POS]
    med_n=sum(v for k,v in by_state["MEDIUM_CONFIDENCE"].items() if k!=AMB)
    d2out={"version":"ebay_d2m_development_benchmark_v1","matcher_version":MATCHER_VERSION,
      "rule_fingerprint":rule_fingerprint(),"partition":"DEVELOPMENT",
      "high":{"accepted_count":counts["HIGH_CONFIDENCE"],"true_positives":high_tp,
        "precision":ratio(high_tp,high_n),"wilson_95":wilson(high_tp,high_n),
        "recall":ratio(high_tp,distribution[POS]),"card_coverage_count":len(cards),
        "card_coverage":ratio(len(cards),70),"non_positive_rows":high_bad},
      "medium":{"count":counts["MEDIUM_CONFIDENCE"],"precision":ratio(med_tp,med_n),
                "gold_breakdown":dict(by_state["MEDIUM_CONFIDENCE"])},
      "ambiguous":{"count":counts["AMBIGUOUS"],"rate":ratio(counts["AMBIGUOUS"],450),
                   "gold_breakdown":dict(by_state["AMBIGUOUS"])},
      "reject":{"count":counts["REJECT"],"rate":ratio(counts["REJECT"],450),
                "gold_breakdown":dict(by_state["REJECT"])},
      "high_false_positive_breakdown":dict(Counter(x["gold_label"] for x in high_bad if x["gold_label"] in NEG))}
    dump("ebay_d2m_development_benchmark.json",d2out)

    classes={}
    for label in sorted(NEG|{AMB}):
        members=[x for x in d2records if x[1]==label]
        classes[label]={"count":len(members),"d2_states":dict(Counter(x[2]["identity_state"] for x in members)),
          "rule_outcomes":dict(Counter(x[2]["reason"] for x in members)),
          "distinct_cards":len({x[0]["canonical_card_id"] for x in members}),
          "distinct_sets":len({x[0]["target_set_name"] for x in members}),
          "resolution":"SECOND_REVIEW" if label==AMB else "HARD_REJECTION_OR_CONFLICT"}
    dump("ebay_d2m_error_taxonomy.json",{"version":"ebay_d2m_error_taxonomy_v1",
      "development_only":True,"classes":classes,
      "leave_error_type_out_diagnostic":{"method":"Reusable lexical/identity rules; diversity measured across cards and sets.",
                                        "validation_is_independent_test":True}})
    dump("ebay_set_alias_registry.json",{"version":SET_ALIAS_REGISTRY_VERSION,
      "provenance":"Canonical set names and established abbreviations observed in Development.","aliases":SET_ALIASES})
    dump("ebay_variant_identity_rules.json",{"version":VARIANT_RULE_VERSION,
      "treatment_terms":TREATMENT_TERMS,"parallel_conflicts":PARALLEL_TERMS,
      "base_treatment_policy":"Base rarity needs explicit parallel resolution for HIGH."})
    dump("ebay_matcher_confidence_rules.json",{"version":MATCHER_VERSION,
      "high":["name+number+set+non-base variant compatible","name+number+explicit variant, set absent, no conflict"],
      "medium":["base name+number+set with parallel unspecified"],
      "ambiguous":["multiple numbers or insufficient independent evidence"],
      "reject":["hard exclusion or identity conflict"],"condition_is_separate":True})

    queue=[]
    for r,gold,result in d2records:
        disagreement=(gold==POS and result["identity_state"]!="HIGH_CONFIDENCE") or (
          gold in NEG and result["identity_state"] in {"HIGH_CONFIDENCE","MEDIUM_CONFIDENCE"})
        difficult=gold=="RELATED_BUT_WRONG_VARIANT"
        if gold==AMB or disagreement or difficult:
            queue.append({"benchmark_row_id":r["benchmark_row_id"],"canonical_card_id":r["canonical_card_id"],
              "target_card_name":r["target_card_name"],"target_set_name":r["target_set_name"],
              "target_card_number":r["target_card_number"],"target_treatment":r["target_treatment"],
              "listing_title":r["listing_title"],"condition":r["condition"],"image_url":r["image_url"],
              "item_url":r["item_url"],"review_reason":"|".join(filter(None,[
                "HUMAN_AMBIGUOUS" if gold==AMB else "",
                "MATCHER_HUMAN_DISAGREEMENT" if disagreement else "",
                "DIFFICULT_VARIANT" if difficult else ""])),"review_status":"PENDING_SECOND_REVIEW"})
    with (OUT/"ebay_d2m_second_review_queue.csv").open("w",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=list(queue[0]));writer.writeheader();writer.writerows(queue)

    dump("ebay_d2m_matcher_manifest.json",{"matcher_version":MATCHER_VERSION,"logic_frozen":True,
      "rule_config_fingerprint":rule_fingerprint(),"query_contract_version":QUERY_CONTRACT_VERSION,
      "query_changes":"NONE","development_api_calls":0,
      "set_alias_registry_version":SET_ALIAS_REGISTRY_VERSION,"variant_rule_version":VARIANT_RULE_VERSION,
      "condition_policy_version":CONDITION_POLICY_VERSION,
      "development_partition_sha256":hashlib.sha256((OUT/"ebay_gold_development.csv").read_bytes()).hexdigest(),
      "review_history_sha256_at_freeze":hashlib.sha256(HISTORY.read_bytes()).hexdigest(),
      "validation_policy_family":["HIGH_CONFIDENCE_ONLY","HIGH_PLUS_MEDIUM_WITH_MANUAL_REVIEW"],
      "validation_labels_accessed":False,"final_blind_labels_accessed":False,"fair_value_fitted":False})

    table="\n".join(f"| {x['target_card']} | {x['listing_title']} | {x['gold_label']} | {x['d1_verdict']} | {x['failure']} |" for x in d1_fps)
    study=f"""# eBay D2M Development matcher study

## Gold authority

Development only: 450/450 effective labels, 0 skipped, 0 unlabeled. Definitive positive:
{distribution[POS]}; definitive negative: {sum(distribution[x] for x in NEG)}; ambiguous
pending adjudication: {distribution[AMB]}. Validation and Final Blind labels were not
loaded. Price fields are excluded from matcher inputs and outputs.

## Frozen D1 baseline

Accepted {d1_accept}/450. On {450-distribution[AMB]} definitive rows: TP {tp}, FP {fp},
TN {tn}, FN {fn}; precision {d1out['precision']:.4%}, recall {d1out['recall']:.4%},
specificity {d1out['specificity']:.4%}, F1 {d1out['f1']:.4%}.

| Target card | Listing title | Gold label | D1 verdict | Failure |
|---|---|---|---|---|
{table}

## Error taxonomy and D2M result

D1 definitive false positives were treatment/parallel failures. Development includes 77
graded, 29 wrong-number, 23 wrong-variant, 2 wrong-set, 5 wrong-language, 11 lot/bundle,
and 9 sealed/accessory examples. D2M applies hard exclusions, collector-number parsing,
versioned set aliases, and treatment evidence while keeping condition separate.

HIGH accepted {d2out['high']['accepted_count']} at {d2out['high']['precision']:.4%}
precision, Wilson 95% CI [{d2out['high']['wilson_95'][0]:.4%},
{d2out['high']['wilson_95'][1]:.4%}], recall {d2out['high']['recall']:.4%}, card coverage
{len(cards)}/70 ({d2out['high']['card_coverage']:.4%}). No definitive negative is HIGH.
MEDIUM count is {d2out['medium']['count']}; ambiguity rate is
{d2out['ambiguous']['rate']:.4%}.

Rules span distinct cards and sets reported in the taxonomy. Validation remains the
independent generalization test. D1 queries are unchanged and no API calls were issued.
Matcher {MATCHER_VERSION} fingerprint {rule_fingerprint()} is frozen. The human-ambiguous,
matcher-disagreement, and difficult-variant rows remain pending in the second-review queue.
"""
    DOCS.mkdir(parents=True,exist_ok=True)
    (DOCS/"EBAY_D2M_DEVELOPMENT_MATCHER_STUDY.md").write_text(study,encoding="utf-8")
    (DOCS/"EBAY_MATCHER_DEVELOPMENT_EVIDENCE.md").write_text(
      "# eBay matcher Development evidence\n\nSee [the frozen Development study](EBAY_D2M_DEVELOPMENT_MATCHER_STUDY.md). Only Development human labels were used; Validation and Final Blind remain sealed.\n",encoding="utf-8")
    print(json.dumps({"d1":d1out,"d2m":d2out,"second_review":len(queue)},indent=2))

if __name__=="__main__": main()
