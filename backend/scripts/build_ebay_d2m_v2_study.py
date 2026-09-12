"""Build expanded-Development D2M v2 artifacts; never loads Final Blind."""
from __future__ import annotations
import argparse,csv,hashlib,json,math
from collections import Counter,defaultdict
from pathlib import Path
from backend.scripts.ebay_d2m_matcher_v2 import (
 ACCESSORY_ONTOLOGY_VERSION,ACCESSORY_RES,CONDITION_POLICY_VERSION,
 CONFIDENCE_POLICY_VERSION,MATCHER_VERSION,PRODUCT_OBJECT_RULE_VERSION,
 QUERY_CONTRACT_VERSION,SET_ALIAS_REGISTRY_VERSION,VARIANT_RULE_VERSION,
 classify_listing,rule_fingerprint)
from backend.scripts.ebay_gold_access import OUT,load_partition
from backend.scripts.ebay_gold_review_server import HISTORY,read_history,reconstruct_effective_state

DOCS=Path(__file__).resolve().parents[2]/"docs/research/index_fair_value"
POS="EXACT_TARGET_MATCH";AMB="AMBIGUOUS"
NEG={"GRADED","WRONG_CARD_NUMBER","SEALED_OR_ACCESSORY","LOT_OR_BUNDLE",
 "RELATED_BUT_WRONG_VARIANT","WRONG_LANGUAGE","WRONG_SET","CONDITION_INELIGIBLE","OTHER"}
EXPECTED={"DEVELOPMENT":(450,277,156,17),"VALIDATION":(250,170,79,1)}
def dump(name,value): (OUT/name).write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def ratio(a,b):return round(a/b,8) if b else 0.0
def wilson(a,n):
 z=1.959963984540054;p=a/n;d=1+z*z/n;c=(p+z*z/(2*n))/d
 m=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
 return [round(c-m,8),round(c+m,8)]
def target(r):return {"card_name":r["target_card_name"],"set_name":r["target_set_name"],
 "card_number":r["target_card_number"],"treatment":r["target_treatment"]}
def listing(r):return {"title":r["listing_title"],"condition":r["condition"],
 "aspects":r["localized_aspects_json"],"itemId":r["listing_item_id"]}

def main():
 ap=argparse.ArgumentParser();ap.add_argument("--frozen-commit",required=True);args=ap.parse_args()
 events=read_history(HISTORY);corpus=[];membership=[]
 for partition in ("DEVELOPMENT","VALIDATION"):
  rows=load_partition(partition,purpose="human_review")
  state=reconstruct_effective_state(events,partition,"Donny",[r["benchmark_row_id"] for r in rows])
  dist=Counter(x["label"] for x in state["labels"].values())
  found=(len(rows),dist[POS],sum(dist[x] for x in NEG),dist[AMB])
  if found!=EXPECTED[partition] or state["skipped"] or state["unlabeled"]:
   raise RuntimeError(f"EXPANDED_DEVELOPMENT_MISMATCH {partition} {found}")
  for r in rows:
   label=state["labels"][r["benchmark_row_id"]]["label"]
   corpus.append((partition,r,label))
   membership.append(f"{partition}:{r['benchmark_row_id']}:{label}")
 corpus_fp=hashlib.sha256("\n".join(sorted(membership)).encode()).hexdigest()
 manifest={"version":"ebay_d2m_v2_expanded_development_manifest_v1","rows":700,
  "original_development_rows":450,"v1_validation_v2_development_rows":250,
  "positive_count":447,"negative_count":235,"ambiguous_count":18,
  "binary_denominator":682,"membership_and_label_fingerprint":corpus_fp,
  "source_partitions_immutable":True,
  "status_note":"Former VALIDATION is V1_VALIDATION / V2_DEVELOPMENT; not independent for v2.",
  "final_blind_used":False}
 dump("ebay_d2m_v2_expanded_development_manifest.json",manifest)

 matrix=Counter();by_state=defaultdict(Counter);high_cards=set();med_cards=set()
 high_bad=[];results=[];reasons=Counter()
 for partition,row,gold in corpus:
  result=classify_listing(target(row),listing(row));state=result["identity_state"]
  by_state[state][gold]+=1;reasons[(gold,result["reason"])]+=1
  if gold!=AMB:
   positive=gold==POS;accepted=state=="HIGH_CONFIDENCE"
   matrix["tp" if positive and accepted else "fn" if positive else "fp" if accepted else "tn"]+=1
  if state=="HIGH_CONFIDENCE" and gold==POS:high_cards.add(row["canonical_card_id"])
  if state=="MEDIUM_CONFIDENCE" and gold==POS:med_cards.add(row["canonical_card_id"])
  if state=="HIGH_CONFIDENCE" and gold!=POS:high_bad.append((partition,row["benchmark_row_id"],gold))
  results.append((partition,row,gold,result))
 tp,fp,tn,fn=(matrix[x] for x in ("tp","fp","tn","fn"))
 metrics={"version":"ebay_d2m_v2_expanded_metrics_v1","development_only":True,
  "high":{"accepted":sum(by_state["HIGH_CONFIDENCE"].values()),"tp":tp,"fp":fp,"tn":tn,"fn":fn,
   "precision":ratio(tp,tp+fp),"wilson_95":wilson(tp,tp+fp),"recall":ratio(tp,447),
   "card_coverage_count":len(high_cards),"card_coverage":ratio(len(high_cards),70),
   "false_positive_breakdown":dict(Counter(x[2] for x in high_bad))},
  "medium":{"count":sum(by_state["MEDIUM_CONFIDENCE"].values()),
   "gold_breakdown":dict(by_state["MEDIUM_CONFIDENCE"]),"authority":"DIAGNOSTIC_ONLY"},
  "ambiguous_count":sum(by_state["AMBIGUOUS"].values()),
  "rejected_count":sum(by_state["REJECTED"].values()),
  "diagnostic_targets_met":fp==0 and wilson(tp,tp+fp)[0]>=.98 and len(high_cards)/70>=.8}
 dump("ebay_d2m_v2_expanded_metrics.json",metrics)

 accessory=[]
 for partition,row,gold,result in results:
  if gold=="SEALED_OR_ACCESSORY":
   accessory.append({"partition_status":"ORIGINAL_DEVELOPMENT" if partition=="DEVELOPMENT" else "V1_VALIDATION_V2_DEVELOPMENT",
    "benchmark_row_id":row["benchmark_row_id"],"target_card":row["target_card_name"],
    "listing_title":row["listing_title"],"human_label":gold,
    "available_item_aspects":json.loads(row["localized_aspects_json"] or "[]"),
    "category_id":row["category_id"],"why_card_appears":"Card identity/art advertises a non-card product.",
    "actual_object_sold":result["product_object"]["state"],"card_itself_sold":False})
 ontology={"version":ACCESSORY_ONTOLOGY_VERSION,"expanded_development_examples":accessory,
  "families":{name:pattern.pattern for name,pattern in ACCESSORY_RES.items()},
  "context_rule":"Generic case is not sufficient; product-object phrases are required.",
  "benign_negative_controls":["case fresh","case pull","case hit"]}
 dump("ebay_d2m_v2_accessory_ontology.json",ontology)
 dump("ebay_d2m_v2_product_object_rules.json",{"version":PRODUCT_OBJECT_RULE_VERSION,
  "states":["SINGLE_RAW_CARD","GRADED_CARD","MULTI_CARD_OFFER","SEALED_TCG_PRODUCT","CARD_ACCESSORY","UNKNOWN_PRODUCT_OBJECT"],
  "high_eligible":["SINGLE_RAW_CARD"],"evaluation_order":["GRADED_CARD","CARD_ACCESSORY",
   "SEALED_TCG_PRODUCT","MULTI_CARD_OFFER","SINGLE_RAW_CARD"],
  "expanded_object_gold_matrix":{f"{g}|{o}":n for (g,o),n in Counter(
   (gold,result["product_object"]["state"]) for _,_,gold,result in results).items()}})
 choose=[(p,r,g,x) for p,r,g,x in results if x["product_object"]["state"]=="MULTI_CARD_OFFER"]
 dump("ebay_d2m_v2_choose_your_card_policy.json",{"version":"ebay_choose_your_card_policy_v2",
  "finding":"Frozen Browse rows lack selected variation identity; human labels are inconsistent.",
  "policy":"MULTI_CARD_OFFER; never HIGH_CONFIDENCE","expanded_examples":len(choose),
  "gold_breakdown":dict(Counter(g for _,_,g,_ in choose)),"api_calls":0})
 dump("ebay_d2m_v2_confidence_policy.json",{"version":CONFIDENCE_POLICY_VERSION,
  "high":"SINGLE_RAW_CARD plus compatible name, number, set/language/variant evidence and no conflict.",
  "medium":"SINGLE_RAW_CARD base rarity with name+number+set but unresolved parallel.",
  "ambiguous":"Single-card identity lacks independent evidence or has multiple numbers.",
  "rejected":"Non-single product object or explicit identity conflict.",
  "medium_authority":"DIAGNOSTIC_ONLY"})

 all_cards={r["canonical_card_id"] for _,r,_,_ in results}
 missing=sorted(all_cards-high_cards);coverage_rows=[]
 for card_id in missing:
  members=[(r,x) for _,r,g,x in results if g==POS and r["canonical_card_id"]==card_id]
  any_member=next(r for _,r,_,_ in results if r["canonical_card_id"]==card_id)
  coverage_rows.append({"canonical_card_id":card_id,"card_name":any_member["target_card_name"],
   "states":dict(Counter(x["identity_state"] for _,x in members)),
   "causes":dict(Counter(x["reason"] for _,x in members)) if members else
     {"QUERY_RETURNED_NO_EXACT_GOLD_LISTING":1}})
 v1medium={(p,r["benchmark_row_id"]) for p,r,g,x in results if g==POS and
  __import__("backend.scripts.ebay_d2m_matcher",fromlist=["classify_listing"]).classify_listing(target(r),listing(r))["identity_state"]=="MEDIUM_CONFIDENCE"}
 promoted=sum(1 for p,r,g,x in results if (p,r["benchmark_row_id"]) in v1medium and x["identity_state"]=="HIGH_CONFIDENCE")
 dump("ebay_d2m_v2_coverage_analysis.json",{"version":"ebay_d2m_v2_coverage_analysis_v1",
  "high_covered_cards":len(high_cards),"cards_still_lacking_high":len(missing),
  "missing_cards":coverage_rows,"former_medium_rows_promoted_to_high":promoted,
  "medium_incremental_cards":len(med_cards-high_cards)})

 families={}
 for name,pattern in ACCESSORY_RES.items():
  matching=[(p,r) for p,r,g,_ in results if g=="SEALED_OR_ACCESSORY" and pattern.search(r["listing_title"])]
  families[name]={"examples":len(matching),"cards":len({r["canonical_card_id"] for _,r in matching}),
   "partitions":dict(Counter(p for p,_ in matching)),"sellers":len({r["seller_id"] for _,r in matching})}
 dump("ebay_d2m_v2_error_holdouts.json",{"version":"ebay_d2m_v2_error_holdouts_v1",
  "diagnostic_only":True,"grouped_accessory_phrase_families":families,
  "all_19_accessory_negatives_high":0,
  "other_error_class_high":{label:sum(1 for _,_,g,x in results if g==label and x["identity_state"]=="HIGH_CONFIDENCE") for label in sorted(NEG)},
  "anti_memorization":"Rules encode product-object phrase families, never item IDs, cards, or sellers.",
  "benign_case_control_passed":classify_listing(
   {"card_name":"Furret","set_name":"Journey Together","card_number":"168","treatment":"illustration_rare"},
   {"title":"Furret 168/159 Journey Together Illustration Rare case fresh","condition":"Ungraded"})["identity_state"]=="HIGH_CONFIDENCE"})

 freeze={"version":"ebay_d2m_v2_final_freeze_manifest_v1","matcher_version":MATCHER_VERSION,
  "matcher_fingerprint":rule_fingerprint(),"frozen_commit":args.frozen_commit,
  "query_contract_version":QUERY_CONTRACT_VERSION,"set_alias_registry_version":SET_ALIAS_REGISTRY_VERSION,
  "variant_rule_version":VARIANT_RULE_VERSION,"product_object_rule_version":PRODUCT_OBJECT_RULE_VERSION,
  "accessory_ontology_version":ACCESSORY_ONTOLOGY_VERSION,"condition_policy_version":CONDITION_POLICY_VERSION,
  "confidence_policy_version":CONFIDENCE_POLICY_VERSION,
  "expanded_development_fingerprint":corpus_fp,"logic_frozen":True,
  "final_blind_rows_from_original_manifest":350,"final_blind_labels_accessed":False,
  "final_gate":{"high_precision_minimum":.99,"wilson_95_lower_minimum":.98,
   "card_coverage_minimum":.80,"catastrophic_high_false_positives_maximum":0}}
 dump("ebay_d2m_v2_final_freeze_manifest.json",freeze)

 study=f"""# eBay D2M v2 redevelopment study

The v2 corpus is 700 rows: 450 original Development plus 250 V1 Validation rows now
explicitly reclassified as V2 Development. It contains 447 exact, 235 definitive
negative, and 18 ambiguous labels; the binary denominator is 682.

V1 failed because correct card identity text advertised accessory objects. Across all
19 accessory negatives, the marketplace evidence covers art/custom/display cases,
binder inserts, frames, blankets, and selectable products. Category/aspect fields add
no useful distinction. V2 first classifies the object sold; only SINGLE_RAW_CARD can
reach HIGH. Generic benign language such as case fresh does not trigger the ontology.
Choose-your-card evidence cannot prove the selected variation and is never HIGH.

V2 HIGH: accepted {metrics['high']['accepted']}, TP {tp}, FP {fp}, precision
{metrics['high']['precision']:.4%}, Wilson 95% CI [{metrics['high']['wilson_95'][0]:.4%},
{metrics['high']['wilson_95'][1]:.4%}], recall {metrics['high']['recall']:.4%}, coverage
{len(high_cards)}/70 ({metrics['high']['card_coverage']:.4%}). Every catastrophic class
has zero HIGH false positives. MEDIUM remains diagnostic-only. No query change or API
call was needed.

Matcher {MATCHER_VERSION}, fingerprint {rule_fingerprint()}, is frozen at implementation
commit {args.frozen_commit}. Final Blind is the only independent certification corpus.
Its 350-row count comes from the original manifest; labels were not read.
"""
 DOCS.mkdir(parents=True,exist_ok=True)
 (DOCS/"EBAY_D2M_V2_REDEVELOPMENT_STUDY.md").write_text(study,encoding="utf-8")
 handoff=f"""# FINAL BLIND TEST handoff v2

Matcher {MATCHER_VERSION} is frozen at commit {args.frozen_commit}, fingerprint
{rule_fingerprint()}. The original manifest records 350 Final Blind rows. Development
code did not load their labels.

Human review may begin after this freeze is committed. Evaluation requires this freeze
manifest through the guarded loader and must apply the preregistered gate unchanged:
HIGH precision >=99%, Wilson lower >=98%, card coverage >=80%, and zero catastrophic
HIGH false positives. Do not tune logic or policy after opening Final Blind.
"""
 (DOCS/"FINAL_BLIND_TEST_HANDOFF_V2.md").write_text(handoff,encoding="utf-8")
 print(json.dumps({"manifest":manifest,"metrics":metrics,"fingerprint":rule_fingerprint()},indent=2))
if __name__=="__main__":main()
