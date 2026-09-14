"""Final certification using frozen D3 predictions and frozen fresh human gold."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from backend.scripts.ebay_d3_fresh_gold_audit import (
    build_audit_queue, effective_gold_fingerprint, effective_labels,
    read_audit_history, reconstruct_audit_state,
)
from backend.scripts.ebay_d3_matcher_v3 import MATCHER_VERSION, rule_fingerprint
from backend.scripts.ebay_gold_access import OUT, load_partition
from backend.scripts.ebay_gold_review_server import read_history, reconstruct_effective_state

ROOT=Path(__file__).resolve().parents[2]
DOCS=ROOT/"docs/research/index_fair_value"
PREDICTIONS=OUT/"ebay_d3_private_frozen_v3_predictions.jsonl"
PRECISION=OUT/"ebay_d3_precision_blind.csv"
COVERAGE=OUT/"ebay_d3_coverage_blind.csv"
REVIEW=OUT/"ebay_d3_blind_review_queue.csv"
BLIND_MANIFEST=OUT/"ebay_d3_fresh_blind_manifest.json"
GOLD_MANIFEST=OUT/"ebay_d3_fresh_human_gold_manifest.json"
DESIGN=OUT/"ebay_d3_new_blind_benchmark_design.json"
DEVELOPMENT=OUT/"ebay_d3_v3_development_metrics.json"
POSITIVE="EXACT_TARGET_MATCH"
AMBIGUOUS="AMBIGUOUS"
CATASTROPHIC=("GRADED","LOT_OR_BUNDLE","SEALED_OR_ACCESSORY","WRONG_CARD_NUMBER",
              "RELATED_BUT_WRONG_VARIANT","WRONG_SET","WRONG_LANGUAGE","AMBIGUOUS")
EXPECTED={
 "matcher":"b5e44641f35c5f846a8d83bc6c777285f6e07707c9c672feef47c55cd67c95ec",
 "design":"75505bfcbe2e167821a3178b5da192e1240879fe3e4edd75891fa2c55c02d2c6",
 "fresh":"9e9b62b65a7f40c7c175e0fdb16cde7a27b193fb3f5e43d6951604d6f860ff1e",
 "prediction":"2c4ac28be281a754259631fa530c4d86638f5da26ae03680a22838e59743d3f6",
 "precision":"2292c755f3e3563c0d8eb268219fa5863b5243b61093264eec1da991ff1142c5",
 "coverage":"e76e63dbbec489e3f8965dcfcaa9f920d004002632f00095318bc7fbc4c7061a",
 "review":"897ad0574f70c649311dc440e0af7a2380cd8d9addaf28b55c2cb1313621ccde",
 "gold":"635365a6773910f8acb5c57efecba81163e187c147eb34f844a50a71bdf85a8c",
}


def file_hash(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def ratio(a:float,b:float)->float:return round(a/b,8) if b else 0.0
def wilson(successes:int,total:int)->list[float]:
 z=1.959963984540054
 if not total:return [0.0,0.0]
 p=successes/total;d=1+z*z/total;c=(p+z*z/(2*total))/d;m=z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/d
 return [round(c-m,8),round(c+m,8)]


def high_precision_metrics(rows:list[Mapping[str,Any]])->dict[str,Any]:
 if any(row["matcher_state"]!="HIGH_CONFIDENCE" for row in rows):raise ValueError("precision cohort contains a non-HIGH prediction")
 tp=sum(row["human_gold"]==POSITIVE for row in rows);fp=len(rows)-tp;amb=sum(row["human_gold"]==AMBIGUOUS for row in rows)
 return {"logical_rows":len(rows),"evaluable_rows":len(rows),"human_ambiguous_rows":amb,
         "true_positives":tp,"false_positives":fp,"precision":ratio(tp,len(rows)),
         "wilson_95":wilson(tp,len(rows)),"exact_match_count":tp,"non_exact_count":fp,
         "false_positives_by_human_label":dict(sorted(Counter(row["human_gold"] for row in rows if row["human_gold"]!=POSITIVE).items())),
         "sufficient_effective_power":len(rows)>=280}


def coverage_metrics(rows:list[Mapping[str,Any]])->dict[str,Any]:
 cards={row["canonical_card_id"] for row in rows};per_card=Counter(row["canonical_card_id"] for row in rows)
 high=[row for row in rows if row["matcher_state"]=="HIGH_CONFIDENCE"]
 tp=sum(row["human_gold"]==POSITIVE for row in high);fp=sum(row["human_gold"]!=POSITIVE for row in high)
 positives=sum(row["human_gold"]==POSITIVE for row in rows);fn=positives-tp
 definitive_negative=[row for row in rows if row["human_gold"] not in {POSITIVE,AMBIGUOUS}]
 binary_fp=sum(row["matcher_state"]=="HIGH_CONFIDENCE" for row in definitive_negative)
 tn=len(definitive_negative)-binary_fp
 precision=ratio(tp,tp+fp);recall=ratio(tp,positives)
 high_cards={row["canonical_card_id"] for row in high if row["human_gold"]==POSITIVE}
 names={row["canonical_card_id"]:row["target_card_name"] for row in rows}
 return {"logical_rows":len(rows),"cards_represented":len(cards),"rows_per_card":dict(sorted(per_card.items())),
         "all_cards_have_six":len(cards)==70 and set(per_card.values())=={6},
         "high_count":len(high),"medium_count":sum(row["matcher_state"]=="MEDIUM_CONFIDENCE" for row in rows),
         "rejected_or_unaccepted_count":sum(row["matcher_state"] not in {"HIGH_CONFIDENCE","MEDIUM_CONFIDENCE"} for row in rows),
         "high_true_positives":tp,"high_false_positives":fp,"false_negatives":fn,
         "recall":recall,"specificity":ratio(tn,tn+binary_fp),"f1":ratio(2*precision*recall,precision+recall),
         "matcher_ambiguity_rate":ratio(sum(row["matcher_state"]=="AMBIGUOUS" for row in rows),len(rows)),
         "matcher_rejection_rate":ratio(sum(row["matcher_state"]=="REJECTED" for row in rows),len(rows)),
         "covered_cards":len(high_cards),"card_coverage":ratio(len(high_cards),70),
         "cards_with_zero_valid_high_exact":[{"canonical_card_id":card,"card_name":names[card]} for card in sorted(cards-high_cards)]}


def load_csv(path:Path)->list[dict[str,str]]:
 with path.open(encoding="utf-8",newline="") as handle:return list(csv.DictReader(handle))


def join_rows(cohort:list[Mapping[str,str]],predictions:Mapping[str,Mapping[str,Any]],gold_by_item:Mapping[str,str])->list[dict[str,Any]]:
 output=[]
 for row in cohort:
  item=row["listing_item_id"]
  if item not in predictions or item not in gold_by_item:raise RuntimeError(f"MISSING_CERTIFICATION_MAPPING:{item}")
  prediction=predictions[item]
  output.append({**dict(row),"human_gold":gold_by_item[item],"matcher_state":prediction["matcher_state"],
                 "product_object_state":prediction["product_object_state"],"matcher_reason":prediction["matcher_reason"],
                 "matcher_evidence":json.dumps(prediction["matcher_evidence"],sort_keys=True,separators=(",",":"))})
 return output


def write_csv(path:Path,rows:list[Mapping[str,Any]])->None:
 with path.open("w",encoding="utf-8",newline="") as handle:
  writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def likely_cause(row:Mapping[str,Any])->str:
 gold=row["human_gold"]
 if gold=="GRADED":return "affirmative grading evidence not classified as graded or image-only slab"
 if gold=="LOT_OR_BUNDLE":return "multiplicity/selectability evidence not classified as multi-card"
 if gold=="SEALED_OR_ACCESSORY":return "non-card product evidence not classified as accessory/sealed"
 if gold=="WRONG_CARD_NUMBER":return "number conflict absent or not parsed"
 if gold=="RELATED_BUT_WRONG_VARIANT":return "variant conflict absent or unresolved"
 if gold=="WRONG_SET":return "set conflict absent or alias collision"
 if gold=="WRONG_LANGUAGE":return "language conflict absent or not parsed"
 if gold==AMBIGUOUS:return "human identity remained unresolved"
 return "other"


def main()->None:
 blind=json.loads(BLIND_MANIFEST.read_text(encoding="utf-8"));gold_manifest=json.loads(GOLD_MANIFEST.read_text(encoding="utf-8"));design=json.loads(DESIGN.read_text(encoding="utf-8"))
 checks={"matcher":rule_fingerprint()==blind["matcher_fingerprint"]==EXPECTED["matcher"],
         "design":design["benchmark_design_fingerprint"]==blind["benchmark_design_fingerprint"]==EXPECTED["design"],
         "fresh":file_hash(OUT/"ebay_d3_fresh_observations.csv")==blind["fresh_observation_fingerprint"]==EXPECTED["fresh"],
         "prediction":file_hash(PREDICTIONS)==blind["private_prediction_fingerprint"]==EXPECTED["prediction"],
         "precision":file_hash(PRECISION)==blind["precision_cohort_fingerprint"]==EXPECTED["precision"],
         "coverage":file_hash(COVERAGE)==blind["coverage_cohort_fingerprint"]==EXPECTED["coverage"],
         "review":file_hash(REVIEW)==blind["review_queue_fingerprint"]==EXPECTED["review"]}
 review_rows=load_partition("D3_BLIND_REVIEW",purpose="human_review");ids=[row["benchmark_row_id"] for row in review_rows]
 base=reconstruct_effective_state(read_history(),"D3_BLIND_REVIEW","Donny",ids);queue=build_audit_queue(review_rows,base["labels"]);audit=reconstruct_audit_state(read_audit_history(),"Donny",[row["benchmark_row_id"] for row in queue]);gold=effective_labels(base["labels"],audit)
 checks["gold"]=effective_gold_fingerprint(gold)==gold_manifest["effective_human_gold_fingerprint"]==EXPECTED["gold"]
 checks["gold_state"]=len(gold)==704 and not base["skipped"] and not base["unlabeled"] and len(audit["decisions"])==43 and not audit["unreviewed"]
 if not all(checks.values()):raise RuntimeError(f"CERTIFICATION_FREEZE_MISMATCH:{checks}")

 # This is the single authorized unseal. The matcher is never regenerated.
 prediction_rows=[json.loads(line) for line in PREDICTIONS.read_text(encoding="utf-8").splitlines() if line.strip()]
 predictions={}
 for row in prediction_rows:
  item=str(row["listing_item_id"])
  if item in predictions and predictions[item]!=row:raise RuntimeError(f"CONFLICTING_PREDICTIONS:{item}")
  predictions[item]=row
 review_by_item={row["listing_item_id"]:row for row in review_rows}
 if len(review_by_item)!=704 or set(review_by_item)-set(predictions):raise RuntimeError("PREDICTION_MAPPING_INCOMPLETE")
 gold_by_item={item:gold[row["benchmark_row_id"]] for item,row in review_by_item.items()}
 precision_rows=join_rows(load_csv(PRECISION),predictions,gold_by_item);coverage_rows=join_rows(load_csv(COVERAGE),predictions,gold_by_item)
 precision_items={row["listing_item_id"] for row in precision_rows};coverage_items={row["listing_item_id"] for row in coverage_rows}
 if len(precision_rows)!=300 or len(coverage_rows)!=420 or len(precision_items&coverage_items)!=16 or len(precision_items|coverage_items)!=704:raise RuntimeError("COHORT_MEMBERSHIP_MISMATCH")

 precision_metrics=high_precision_metrics(precision_rows);coverage_result=coverage_metrics(coverage_rows)
 unique_rows={row["listing_item_id"]:row for row in precision_rows+coverage_rows}
 catastrophic={label:sum(row["matcher_state"]=="HIGH_CONFIDENCE" and row["human_gold"]==label for row in unique_rows.values()) for label in CATASTROPHIC}
 high_false_positives=[row for row in unique_rows.values() if row["matcher_state"]=="HIGH_CONFIDENCE" and row["human_gold"]!=POSITIVE]
 medium=[row for row in unique_rows.values() if row["matcher_state"]=="MEDIUM_CONFIDENCE"]
 medium_exact=sum(row["human_gold"]==POSITIVE for row in medium);medium_fp=len(medium)-medium_exact
 coverage_high_cards={row["canonical_card_id"] for row in coverage_rows if row["matcher_state"]=="HIGH_CONFIDENCE" and row["human_gold"]==POSITIVE}
 coverage_medium_cards={row["canonical_card_id"] for row in coverage_rows if row["matcher_state"]=="MEDIUM_CONFIDENCE" and row["human_gold"]==POSITIVE}
 medium_result={"unique_row_count":len(medium),"exact_matches":medium_exact,"false_positives":medium_fp,
                "precision":ratio(medium_exact,len(medium)),"incremental_coverage_cards":len(coverage_medium_cards-coverage_high_cards),"authority":"DIAGNOSTIC_ONLY"}
 gates={"precision":precision_metrics["precision"]>=design["preregistered_gate"]["high_precision_minimum"],
        "wilson_lower":precision_metrics["wilson_95"][0]>=design["preregistered_gate"]["wilson_95_lower_minimum"],
        "coverage":coverage_result["card_coverage"]>=design["preregistered_gate"]["card_coverage_minimum"],
        "catastrophic":not any(catastrophic.values())}
 passed=all(gates.values())
 development=json.loads(DEVELOPMENT.read_text(encoding="utf-8"))
 stability={"development":{"precision":development["high"]["precision"],"recall":development["high"]["recall"],"coverage":development["high"]["card_coverage"],"ambiguity_rate":ratio(development["matcher_state_breakdown"]["AMBIGUOUS"],1050),"rejection_rate":ratio(development["matcher_state_breakdown"]["REJECTED"],1050),"catastrophic":development["catastrophic_high_counts"]},
            "fresh":{"precision":precision_metrics["precision"],"recall":coverage_result["recall"],"coverage":coverage_result["card_coverage"],"ambiguity_rate":coverage_result["matcher_ambiguity_rate"],"rejection_rate":coverage_result["matcher_rejection_rate"],"catastrophic":catastrophic}}
 timestamp=datetime.now(timezone.utc).isoformat();code_commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
 metadata={"version":"ebay_d3_v3_final_certification_metrics_v1","matcher_version":MATCHER_VERSION,
           "matcher_fingerprint":EXPECTED["matcher"],"prediction_fingerprint":EXPECTED["prediction"],
           "benchmark_design_fingerprint":EXPECTED["design"],"human_gold_fingerprint":EXPECTED["gold"],
           "evaluation_code_commit":code_commit,"evaluated_at":timestamp}
 metrics={**metadata,"precision_cohort":precision_metrics,"coverage_cohort":coverage_result,
          "catastrophic_high_errors":catastrophic,"medium_diagnostics":medium_result,
          "stability":stability,"gates":gates,"overall_result":"PASS" if passed else "FAIL"}
 metrics_path=OUT/"ebay_d3_v3_final_certification_metrics.json";metrics_path.write_text(json.dumps(metrics,indent=2)+"\n",encoding="utf-8")
 write_csv(OUT/"ebay_d3_v3_precision_certification_rows.csv",precision_rows)
 write_csv(OUT/"ebay_d3_v3_coverage_certification_rows.csv",coverage_rows)
 forensic=[]
 for row in sorted(high_false_positives,key=lambda item:item["benchmark_row_id"]):
  forensic.append({"benchmark_row_id":row["benchmark_row_id"],"listing_item_id":row["listing_item_id"],
                   "target_card":row["target_card_name"],"human_gold":row["human_gold"],"matcher_state":row["matcher_state"],
                   "matcher_reason":row["matcher_reason"],"matcher_evidence":row["matcher_evidence"],"listing_title":row["listing_title"],
                   "condition":row["condition"],"condition_id":row["condition_id"],"category_id":row["category_id"],
                   "localized_aspects_json":row["localized_aspects_json"],
                   "cohort_membership":"PRECISION_BLIND+COVERAGE_BLIND" if row["listing_item_id"] in precision_items&coverage_items else "PRECISION_BLIND" if row["listing_item_id"] in precision_items else "COVERAGE_BLIND",
                   "in_both_cohorts":row["listing_item_id"] in precision_items&coverage_items,"error_class":row["human_gold"],"likely_structural_cause":likely_cause(row)})
 forensic_path=OUT/"ebay_d3_v3_high_false_positive_forensics.csv"
 if forensic:write_csv(forensic_path,forensic)
 else:forensic_path.write_text("benchmark_row_id,listing_item_id,target_card,human_gold,matcher_state,matcher_reason,matcher_evidence,listing_title,condition,condition_id,category_id,localized_aspects_json,cohort_membership,in_both_cohorts,error_class,likely_structural_cause\n",encoding="utf-8")
 decision="EBAY_IDENTITY_MATCHER_V3_VALIDATED" if passed else "EBAY_IDENTITY_MATCHER_V3_NOT_VALIDATED"
 report=f"""# eBay D3 v3 final independent certification

Frozen v3 predictions were unsealed once and scored against frozen human gold. The
precision cohort has {precision_metrics['true_positives']} TP and {precision_metrics['false_positives']} FP across 300 HIGH rows:
precision {precision_metrics['precision']:.4%}, Wilson 95% CI [{precision_metrics['wilson_95'][0]:.4%}, {precision_metrics['wilson_95'][1]:.4%}].

The coverage cohort has {coverage_result['high_true_positives']} HIGH TP, {coverage_result['high_false_positives']} HIGH FP,
recall {coverage_result['recall']:.4%}, and covers {coverage_result['covered_cards']}/70 cards ({coverage_result['card_coverage']:.4%}).
Unique catastrophic HIGH errors: {sum(catastrophic.values())}. Gates: {json.dumps(gates,sort_keys=True)}.
Final result: **{'PASS' if passed else 'FAIL'}** (`{decision}`).

Authority is limited to HIGH-confidence active-listing identity filtering only when all
four gates pass. Active listings are offered supply/asking-price observations, not
completed sales. Asking-price authority, Fair Value, forecasting, recommendations, and
production pricing replacement are not validated here.
"""
 DOCS.mkdir(parents=True,exist_ok=True);(DOCS/"EBAY_D3_V3_FINAL_CERTIFICATION_REPORT.md").write_text(report,encoding="utf-8")
 manifest={"version":"ebay_d3_v3_final_certification_manifest_v1","matcher_fingerprint":EXPECTED["matcher"],
           "frozen_prediction_fingerprint":EXPECTED["prediction"],"benchmark_design_fingerprint":EXPECTED["design"],
           "precision_cohort_fingerprint":EXPECTED["precision"],"coverage_cohort_fingerprint":EXPECTED["coverage"],
           "review_queue_fingerprint":EXPECTED["review"],"human_gold_fingerprint":EXPECTED["gold"],
           "certification_metrics_fingerprint":file_hash(metrics_path),"final_result":decision,
           "final_result_fingerprint":hashlib.sha256(decision.encode()).hexdigest(),"evaluation_code_commit":code_commit,"evaluated_at":timestamp}
 manifest["manifest_fingerprint"]=hashlib.sha256(json.dumps(manifest,sort_keys=True,separators=(",",":")).encode()).hexdigest()
 (OUT/"ebay_d3_v3_final_certification_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
 print(json.dumps({"metrics":metrics,"manifest":manifest,"forensic_count":len(forensic)},indent=2))


if __name__=="__main__":main()
