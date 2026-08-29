"""V3 Round 3 temporal and production-contract research (no publication)."""

from __future__ import annotations

import argparse
import json
import math
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from dotenv import load_dotenv

from backend.desirability.treatment_market_prestige_v3 import centered_contributions, stable_json_hash
from backend.scripts.build_treatment_market_prestige_v3_round2 import (
    R1_ID, clean, fit, load_round1, load_exact, treatment_rows, wild_draws,
)

ROOT=Path("docs/research")
R2_ID="treatment-market-prestige-v3-r2-9439727344d3bbb5"
R2_STUDY=ROOT/"treatment_market_prestige_v3_round2_study.json"
OUT=ROOT/"treatment_market_prestige_v3_round3_temporal"
STUDY=ROOT/"treatment_market_prestige_v3_round3_study.json"
REPORT=ROOT/"TREATMENT_MARKET_PRESTIGE_V3_ROUND3_RESULTS.md"
SEED=20260831
CHECKPOINTS=(date(2026,8,29),date(2026,7,30),date(2026,6,30),date(2026,5,31))
UNIVERSES={"Mega Evolution":("illustration_rare","ultra_rare","double_rare"),"Scarlet and Violet":("illustration_rare","special_illustration_rare")}
TEMPORAL_GATES={"minimum_adequate_checkpoints":3,"minimum_cell_coverage_vs_current":.70,"minimum_sets":5,
 "required_sign_stability":1.0,"maximum_coefficient_range":1.0,"minimum_exact_order_preservation":.75,
 "minimum_top_identity_preservation":.75,"minimum_bottom_identity_preservation":.75,
 "strong_ordering_probability":.95,"minimum_strong_checkpoint_rate":.75}
EVIDENCE_CONTRACT={
 "standard":{"minimum_cards":50,"minimum_sets":5,"minimum_species":35},
 "composite_low_sample":{"minimum_cards":40,"minimum_sets":6,"minimum_species":35,"maximum_set_share":.25,
  "maximum_species_share":.10,"maximum_bootstrap_interval_width":.75,"leave_set_out_same_sign_rate":1.0,
  "requires_temporally_stable":True,"maximum_leave_set_coefficient_range":1.5,"requires_price_trim_rank_stability":True},
 "common_requirements":{"estimable":True,"bootstrap_interval_excludes_zero":True,"bootstrap_sign_stability":.95,
  "temporally_stable":True,"price_outlier_robust":True,"mechanic_robust":True},
 "statuses":["PRODUCTION_ELIGIBLE","RESEARCH_SUPPORTED_LOW_SAMPLE","ORDERING_UNRESOLVED","TEMPORALLY_UNSTABLE","INSUFFICIENT_SUPPORT"]}


def chunks(values:Sequence[str],size:int=75):
    for start in range(0,len(values),size):yield values[start:start+size]


def historical_prices(client:Any,variant_ids:list[str],condition_id:str,checkpoint:date,lookback_days:int=7)->dict[str,dict[str,Any]]:
    start=(checkpoint-timedelta(days=lookback_days-1)).isoformat(); end=(checkpoint+timedelta(days=1)).isoformat(); rows=[]
    for part in chunks(variant_ids):
        offset=0
        while True:
            last_error=None
            for attempt in range(3):
                try:
                    batch=(client.table("card_variant_price_observations").select("id,card_variant_id,condition_id,market_price,currency,source,captured_at,created_at")
                           .in_("card_variant_id",part).eq("condition_id",condition_id).gte("captured_at",start).lt("captured_at",end)
                           .range(offset,offset+999).execute().data or [])
                    break
                except Exception as exc:
                    last_error=exc
                    if attempt==2:raise
                    time.sleep(1+attempt)
            rows.extend(batch)
            if len(batch)<1000:break
            offset+=1000
    selected={}
    for row in rows:
        try: price=float(row.get("market_price"))
        except (TypeError,ValueError):continue
        currency=str(row.get("currency") or "").strip('"').upper()
        if price<=0 or not math.isfinite(price) or currency!="USD":continue
        vid=str(row["card_variant_id"]); rank=(str(row.get("captured_at") or ""),str(row.get("created_at") or ""),str(row.get("id") or ""))
        if vid not in selected or rank>selected[vid][0]:selected[vid]=(rank,row)
    return {vid:item[1] for vid,item in selected.items()}


def freeze_checkpoints(main_rows:list[dict[str,Any]],exact_rows:list[dict[str,Any]],r1_manifest:Mapping[str,Any],r2_manifest:Mapping[str,Any],client:Any)->tuple[list[dict[str,Any]],dict[str,Any]]:
    OUT.mkdir(parents=True,exist_ok=True); variant_ids=sorted({row["variant_id"] for row in exact_rows})
    conditions=client.table("conditions").select("id,name,abbreviation").execute().data or []
    nm=[row for row in conditions if row.get("name")=="Near Mint" or row.get("abbreviation")=="NM"]
    if not nm:raise RuntimeError("Near Mint condition unavailable")
    condition_id=str(nm[0]["id"]); snapshots=[]
    current={row["variant_id"]:row for row in main_rows}
    for checkpoint in CHECKPOINTS:
        rows=[]
        if checkpoint==CHECKPOINTS[0]:
            for base in exact_rows:
                row=dict(base); row["historical_market_price"]=row["market_price"]; row["historical_log_price"]=row["log_price"]
                row["historical_price_captured_at"]=row.get("price_captured_at"); row["historical_price_source"]=row.get("price_source"); rows.append(row)
            semantics="immutable Round 1 selected positive USD Near Mint price"
        else:
            prices=historical_prices(client,variant_ids,condition_id,checkpoint)
            for base in exact_rows:
                price=prices.get(base["variant_id"])
                if not price:continue
                row=dict(base); row["historical_market_price"]=float(price["market_price"]);row["historical_log_price"]=math.log(float(price["market_price"]))
                row["historical_price_captured_at"]=price.get("captured_at");row["historical_price_source"]=price.get("source");rows.append(row)
            semantics="latest observed positive USD Near Mint price on/before checkpoint within fixed 7-day lookback; no interpolation"
        rows.sort(key=lambda row:(row["set_id"],row["variant_id"]));cohort_hash=stable_json_hash(rows)
        core={"reference_date":checkpoint.isoformat(),"pricing_semantics":semantics,"near_mint_condition_id":condition_id,
              "taxonomy_version":r1_manifest["taxonomy_version"],"demand_snapshot_id":r1_manifest["demand_snapshot_id"],
              "canonical_mapping_authority":R1_ID,"exact_pull_authority":R2_ID,"cohort_hash":cohort_hash,"rows":len(rows)}
        manifest_hash=stable_json_hash(core);manifest={"checkpoint_id":f"tmp-v3-r3-{checkpoint.isoformat()}-{manifest_hash[:12]}","manifest_hash":manifest_hash,**core}
        folder=OUT/checkpoint.isoformat();folder.mkdir(parents=True,exist_ok=True)
        (folder/"cohort.json").write_text(json.dumps({"checkpoint_id":manifest["checkpoint_id"],"rows":rows},indent=2),encoding="utf-8")
        (folder/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
        snapshots.append({"manifest":manifest,"rows":rows})
    core={"frozen_at":datetime.now(timezone.utc).isoformat(),"methodology":"treatment_market_prestige_v3_round3",
          "round1_manifest_hash":r1_manifest["manifest_hash"],"round2_manifest_hash":r2_manifest["manifest_hash"],
          "checkpoint_manifest_hashes":[item["manifest"]["manifest_hash"] for item in snapshots]}
    digest=stable_json_hash(core);manifest={"study_id":f"treatment-market-prestige-v3-r3-{digest[:16]}","manifest_hash":digest,**core}
    (OUT/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    return snapshots,manifest


def load_checkpoints()->tuple[list[dict[str,Any]],dict[str,Any]]:
    overall=json.loads((OUT/"manifest.json").read_text(encoding="utf-8"));snapshots=[]
    for checkpoint in CHECKPOINTS:
        folder=OUT/checkpoint.isoformat();manifest=json.loads((folder/"manifest.json").read_text(encoding="utf-8"));payload=json.loads((folder/"cohort.json").read_text(encoding="utf-8"))
        if stable_json_hash(payload["rows"])!=manifest["cohort_hash"] or payload["checkpoint_id"]!=manifest["checkpoint_id"]:raise RuntimeError("Historical checkpoint hash failure")
        snapshots.append({"manifest":manifest,"rows":payload["rows"]})
    if [item["manifest"]["manifest_hash"] for item in snapshots]!=overall["checkpoint_manifest_hashes"]:raise RuntimeError("Round 3 manifest chain failure")
    return snapshots,overall


def checkpoint_analysis(snapshot:Mapping[str,Any],draw_count:int,seed:int)->dict[str,Any]:
    output={"reference_date":snapshot["manifest"]["reference_date"],"cohort_size":len(snapshot["rows"]),"cohort_hash":snapshot["manifest"]["cohort_hash"],"eras":{}}
    for era,universe in UNIVERSES.items():
        rows=[{**row,"market_price":row["historical_market_price"],"log_price":row["historical_log_price"]} for row in snapshot["rows"] if row["era_name"]==era and row.get("species_id") and row.get("demand_score") is not None and not row.get("promo_status_ambiguous") and row.get("rarity_designation")]
        cell={t:len(treatment_rows(rows,era,t)) for t in universe};sets={t:len({row["set_id"] for row in treatment_rows(rows,era,t)}) for t in universe}
        if len(rows)<100 or any(cell[t]<10 for t in universe):output["eras"][era]={"status":"INSUFFICIENT_HISTORY","n":len(rows),"cell_sizes":cell,"set_counts":sets};continue
        model=fit(rows,"combined");samples=wild_draws(model,rows,draw_count,seed+len(output["eras"]));coefficients={t:model["coefficients"].get(f"rarity_designation:{t}") for t in universe}
        uncertainty={t:([float(np.quantile(samples[f"rarity_designation:{t}"],.025)),float(np.quantile(samples[f"rarity_designation:{t}"],.975))] if f"rarity_designation:{t}" in samples else None) for t in universe}
        matrix={};scores={}
        for left in universe:
            matrix[left]={};a=np.asarray(samples.get(f"rarity_designation:{left}",[]))
            for right in universe:
                if left==right:matrix[left][right]=.5
                else:
                    b=np.asarray(samples.get(f"rarity_designation:{right}",[]));matrix[left][right]=float(np.mean(a>b)) if len(a) and len(b) else None
            scores[left]=10*float(np.mean([matrix[left][right] for right in universe if right!=left])) if len(universe)>1 else None
        order=sorted(universe,key=lambda t:coefficients[t] if coefficients[t] is not None else -math.inf,reverse=True)
        output["eras"][era]={"status":"ESTIMATED","n":len(rows),"sets":len({row["set_id"] for row in rows}),"species":len({row["species_id"] for row in rows}),
          "cell_sizes":cell,"set_counts":sets,"coefficients":coefficients,"bootstrap_intervals":uncertainty,"pairwise_superiority":matrix,"order":order,"research_scores":scores,"model":clean(model)}
    return output


def temporal_classification(results:list[dict[str,Any]])->dict[str,Any]:
    output={}
    for era,universe in UNIVERSES.items():
        checkpoints=[result for result in results if result["eras"].get(era,{}).get("status")=="ESTIMATED"]
        current=next((item for item in checkpoints if item["reference_date"]==CHECKPOINTS[0].isoformat()),None);details={}
        for treatment in universe:
            values=[item["eras"][era]["coefficients"].get(treatment) for item in checkpoints];values=[v for v in values if v is not None]
            coverage_ok=bool(current) and all(item["eras"][era]["cell_sizes"][treatment]>=TEMPORAL_GATES["minimum_cell_coverage_vs_current"]*current["eras"][era]["cell_sizes"][treatment] and item["eras"][era]["set_counts"][treatment]>=TEMPORAL_GATES["minimum_sets"] for item in checkpoints)
            sign_rate=max(np.mean(np.asarray(values)>0),np.mean(np.asarray(values)<0)) if values else 0;coefficient_range=max(values)-min(values) if values else None
            if len(checkpoints)<TEMPORAL_GATES["minimum_adequate_checkpoints"] or not coverage_ok:status="INSUFFICIENT_HISTORY"
            elif sign_rate==TEMPORAL_GATES["required_sign_stability"] and coefficient_range<=TEMPORAL_GATES["maximum_coefficient_range"]:status="TEMPORALLY_STABLE"
            elif sign_rate<.75 or coefficient_range>2*TEMPORAL_GATES["maximum_coefficient_range"]:status="TEMPORALLY_UNSTABLE"
            else:status="TEMPORALLY_UNCERTAIN"
            details[treatment]={"status":status,"checkpoint_count":len(checkpoints),"coverage_gate":coverage_ok,"sign_stability":float(sign_rate),"coefficient_range":coefficient_range,"coefficients":values}
        expected=list(universe);orders=[item["eras"][era]["order"] for item in checkpoints]
        exact_rate=np.mean([order==expected for order in orders]) if orders else 0;top_rate=np.mean([order[0]==expected[0] for order in orders]) if orders else 0;bottom_rate=np.mean([order[-1]==expected[-1] for order in orders]) if orders else 0
        pair_rates={}
        for i,left in enumerate(universe):
            for right in universe[i+1:]:
                probs=[item["eras"][era]["pairwise_superiority"][left][right] for item in checkpoints];pair_rates[f"{left}>{right}"]={"probabilities":probs,"strong_checkpoint_rate":float(np.mean(np.asarray(probs)>=TEMPORAL_GATES["strong_ordering_probability"])) if probs else 0}
        max_rank_move=0
        if orders:
            base={t:i for i,t in enumerate(orders[0])};max_rank_move=max(abs(base[t]-order.index(t)) for order in orders for t in universe)
        persistent=bool(len(checkpoints)>=TEMPORAL_GATES["minimum_adequate_checkpoints"] and exact_rate>=TEMPORAL_GATES["minimum_exact_order_preservation"] and top_rate>=TEMPORAL_GATES["minimum_top_identity_preservation"] and bottom_rate>=TEMPORAL_GATES["minimum_bottom_identity_preservation"] and all(v["strong_checkpoint_rate"]>=TEMPORAL_GATES["minimum_strong_checkpoint_rate"] for v in pair_rates.values()))
        output[era]={"treatments":details,"adequate_checkpoints":len(checkpoints),"exact_order_preservation":float(exact_rate),"top_identity_preservation":float(top_rate),"bottom_identity_preservation":float(bottom_rate),
          "pairwise_strong_rates":pair_rates,"maximum_rank_movement":max_rank_move,"observed_ordering_persistent":persistent,
          "ordering_temporally_stable":bool(persistent and all(value["status"]=="TEMPORALLY_STABLE" for value in details.values()))}
    return output


def representativeness(r1_study:Mapping[str,Any],r2_study:Mapping[str,Any],main_rows:Sequence[Mapping[str,Any]],exact_rows:Sequence[Mapping[str,Any]])->dict[str,Any]:
    broad_by_era={item["era_name"]:item for item in r1_study["era_heterogeneity"]};output={}
    for era,universe in UNIVERSES.items():
        broad=broad_by_era[era];exact=r2_study["era_comparisons"][era]["models"]["treatment"]
        rows=[]
        for treatment in universe:
            key=f"rarity_designation:{treatment}";b=broad["coefficients"].get(key);e=exact["coefficients"].get(key)
            bci=broad.get("bootstrap_stability",{}).get(key)
            broad_group=[row for row in main_rows if row["era_name"]==era and row.get("rarity_designation")==treatment and row.get("species_id") and row.get("demand_score") is not None and not row.get("promo_status_ambiguous")]
            exact_group=[row for row in exact_rows if row["era_name"]==era and row.get("rarity_designation")==treatment and row.get("species_id") and row.get("demand_score") is not None and not row.get("promo_status_ambiguous")]
            rows.append({"treatment":treatment,"broad_coefficient":b,"broad_bootstrap_interval":[bci["ci_low"],bci["ci_high"]] if bci else None,
                         "exact_subset_coefficient":e,"coefficient_difference_exact_minus_broad":e-b if b is not None and e is not None else None,
                         "same_sign":bool(b is not None and e is not None and np.sign(b)==np.sign(e)),
                         "broad_rows":len(broad_group),"exact_rows":len(exact_group),"broad_sets":len({row["set_id"] for row in broad_group}),"exact_sets":len({row["set_id"] for row in exact_group}),
                         "broad_species":len({row["species_id"] for row in broad_group}),"exact_species":len({row["species_id"] for row in exact_group}),
                         "set_overlap_rate":len({row["set_id"] for row in broad_group}&{row["set_id"] for row in exact_group})/max(len({row["set_id"] for row in broad_group}),1),
                         "species_overlap_rate":len({row["species_id"] for row in broad_group}&{row["species_id"] for row in exact_group})/max(len({row["species_id"] for row in broad_group}),1)})
        broad_order=sorted(universe,key=lambda t:broad["coefficients"].get(f"rarity_designation:{t}",-math.inf),reverse=True);exact_order=sorted(universe,key=lambda t:exact["coefficients"].get(f"rarity_designation:{t}",-math.inf),reverse=True)
        output[era]={"coefficients":rows,"broad_order":broad_order,"exact_subset_order":exact_order,"ordering_matches":broad_order==exact_order,
                     "scope":"representativeness only for the two exact-pull-supported eras; no 17-era generalization"}
    return output


def coverage_selection(main:list[dict[str,Any]],exact:list[dict[str,Any]],r1_study:Mapping[str,Any])->dict[str,Any]:
    covered={row["canonical_card_id"] for row in exact};set_map={row["id"]:row for row in json.loads((ROOT/"treatment_market_prestige_v3_frozen_cohort/set_era_mapping.json").read_text(encoding="utf-8"))}
    coefficients=r1_study["species_fe"]["coefficients"];contributions=centered_contributions(main,coefficients)
    records=[]
    for row,prestige in zip(main,contributions):
        release=(set_map.get(row["set_id"]) or {}).get("release_date")
        records.append({"covered":row["canonical_card_id"] in covered,"era":row["era_name"],"treatment":row.get("rarity_designation"),"price":row["market_price"],"demand":row.get("demand_score"),"release_date":release,"prestige":prestige,"mechanics":row.get("mechanic_or_card_form",[])})
    yes=[r for r in records if r["covered"]];no=[r for r in records if not r["covered"]]
    def summary(group):
        return {"n":len(group),"median_price":float(np.median([r["price"] for r in group])),"median_demand":float(np.median([r["demand"] for r in group if r["demand"] is not None])),"mean_round1_treatment_contribution":float(np.mean([r["prestige"] for r in group]))}
    era_rates=[]
    for era in sorted({r["era"] for r in records}):
        group=[r for r in records if r["era"]==era];era_rates.append({"era":era,"n":len(group),"coverage_rate":np.mean([r["covered"] for r in group])})
    mechanics=[]
    for flag in sorted({f for r in records for f in r["mechanics"]}):
        group=[r for r in records if flag in r["mechanics"]];mechanics.append({"mechanic":flag,"n":len(group),"coverage_rate":np.mean([r["covered"] for r in group])})
    return {"covered":summary(yes),"uncovered":summary(no),"era_coverage":era_rates,"mechanic_coverage":mechanics,
      "set_recency":{"covered_median_release_date":sorted([r["release_date"] for r in yes if r["release_date"]])[len([r for r in yes if r["release_date"]])//2],"uncovered_median_release_date":sorted([r["release_date"] for r in no if r["release_date"]])[len([r for r in no if r["release_date"]])//2]},
      "finding":"Exact Pull Scarcity coverage is structurally selected toward Scarlet & Violet and Mega Evolution sets; Round 2 incremental conclusions do not generalize to all 17 eras."}


def ultra_and_contract(exact:list[dict[str,Any]],r2:Mapping[str,Any],temporal:Mapping[str,Any],checkpoints:list[dict[str,Any]])->tuple[dict[str,Any],dict[str,Any]]:
    era="Mega Evolution";treatment="ultra_rare";rows=[row for row in exact if row["era_name"]==era and row.get("species_id") and row.get("rarity_designation")==treatment and not row.get("promo_status_ambiguous")]
    detail=next(item for item in r2["eligible_treatment_universes"][era]["details"] if item["treatment"]==treatment);by_set=Counter(row["set_id"] for row in rows);by_species=Counter(row["species_id"] for row in rows)
    current=[{**row,"market_price":row["historical_market_price"],"log_price":row["historical_log_price"]} for row in checkpoints[0]["rows"] if row["era_name"]==era and row.get("species_id") and not row.get("promo_status_ambiguous") and row.get("rarity_designation")]
    base=fit(current,"combined");point=base["coefficients"][f"rarity_designation:{treatment}"];lso=[]
    for sid in sorted({row["set_id"] for row in current}):
        model=fit([row for row in current if row["set_id"]!=sid],"combined");lso.append(model["coefficients"].get(f"rarity_designation:{treatment}"))
    prices=np.asarray([row["market_price"] for row in current]);lo,hi=np.quantile(prices,[.01,.99]);trim=fit([row for row in current if lo<=row["market_price"]<=hi],"combined")["coefficients"].get(f"rarity_designation:{treatment}")
    audit={"n":len(rows),"sets":len(by_set),"species":len(by_species),"maximum_set_share":max(by_set.values())/len(rows),"maximum_species_share":max(by_species.values())/len(rows),
      "bootstrap_interval":detail["bootstrap_ci"],"bootstrap_interval_width":detail["bootstrap_ci"][1]-detail["bootstrap_ci"][0],"pairwise_ordering_stability":"strong in Round 2",
      "leave_set_out_same_sign_rate":detail["leave_set_out"]["same_sign_rate"],"temporal_status":temporal[era]["treatments"][treatment]["status"],
      "leave_set_coefficient_range":max(lso)-min(lso),"price_trim_coefficient":trim,"price_trim_same_sign":np.sign(trim)==np.sign(point),"price_trim_absolute_change":abs(trim-point)}
    composite=EVIDENCE_CONTRACT["composite_low_sample"];common=EVIDENCE_CONTRACT["common_requirements"]
    gates={"minimum_cards":audit["n"]>=composite["minimum_cards"],"minimum_sets":audit["sets"]>=composite["minimum_sets"],"minimum_species":audit["species"]>=composite["minimum_species"],
      "set_concentration":audit["maximum_set_share"]<=composite["maximum_set_share"],"species_concentration":audit["maximum_species_share"]<=composite["maximum_species_share"],
      "uncertainty":audit["bootstrap_interval_width"]<=composite["maximum_bootstrap_interval_width"],"leave_set_out":audit["leave_set_out_same_sign_rate"]>=composite["leave_set_out_same_sign_rate"],
      "temporal":audit["temporal_status"]=="TEMPORALLY_STABLE","influence":audit["leave_set_coefficient_range"]<=composite["maximum_leave_set_coefficient_range"],"price_trim":audit["price_trim_same_sign"] and audit["price_trim_absolute_change"]<=.5}
    return audit,{"rule":"composite_low_sample","gates":gates,"status":"PRODUCTION_ELIGIBLE" if all(gates.values()) else "RESEARCH_SUPPORTED_LOW_SAMPLE"}


def contract_cells(r2:Mapping[str,Any],temporal:Mapping[str,Any],ultra_result:Mapping[str,Any])->dict[str,Any]:
    output={}
    for era,universe in UNIVERSES.items():
        output[era]={}
        for treatment in universe:
            detail=next((x for x in r2["eligible_treatment_universes"][era]["details"] if x["treatment"]==treatment),None)
            if era=="Mega Evolution" and treatment=="ultra_rare":status=ultra_result["status"]
            elif not detail or not detail["eligible"]:status="INSUFFICIENT_SUPPORT"
            elif temporal[era]["treatments"][treatment]["status"]!="TEMPORALLY_STABLE":status=temporal[era]["treatments"][treatment]["status"]
            elif not temporal[era]["ordering_temporally_stable"]:status="ORDERING_UNRESOLVED"
            else:status="PRODUCTION_ELIGIBLE"
            output[era][treatment]={"status":status,"no_cross_era_fallback":True,"unsupported_value":None}
    return output


def render(study:Mapping[str,Any])->str:
    temporal=study["temporal_results"];req=[
      f"1. Round 3 study ID: `{study['frozen_study']['study_id']}`.",f"2. Temporal checkpoints: {', '.join(x['reference_date'] for x in temporal)}.",
      f"3. Historical cohort sizes: `{json.dumps({x['reference_date']:x['cohort_size'] for x in temporal},sort_keys=True)}`.",f"4. Historical hashes: `{json.dumps({x['reference_date']:x['cohort_hash'] for x in temporal},sort_keys=True)}`.",
      f"5. Mega coefficients: `{json.dumps({x['reference_date']:x['eras'].get('Mega Evolution',{}).get('coefficients') for x in temporal},sort_keys=True)}`.",f"6. Mega ranking probabilities: `{json.dumps({x['reference_date']:x['eras'].get('Mega Evolution',{}).get('pairwise_superiority') for x in temporal},sort_keys=True)}`.",
      f"7. Mega ranking stability: `{json.dumps(study['temporal_classification']['Mega Evolution'],sort_keys=True)}`.",f"8. S&V coefficients: `{json.dumps({x['reference_date']:x['eras'].get('Scarlet and Violet',{}).get('coefficients') for x in temporal},sort_keys=True)}`.",
      f"9. S&V ordering probabilities: `{json.dumps({x['reference_date']:x['eras'].get('Scarlet and Violet',{}).get('pairwise_superiority') for x in temporal},sort_keys=True)}`.",f"10. S&V temporal conclusion: `{study['era_recommendations']['Scarlet and Violet']['temporal_result']}`.",
      f"11. Broad vs exact subset: `{json.dumps(study['representativeness'],sort_keys=True)}`.",f"12. Coverage selection: `{json.dumps(study['coverage_selection'],sort_keys=True)}`.",
      f"13. Evidence-quality contract: `{json.dumps(study['evidence_quality_contract'],sort_keys=True)}`.",f"14. Mega Ultra Rare audit: `{json.dumps(study['mega_ultra_rare_audit'],sort_keys=True)}`.",
      f"15. Mega Ultra Rare result: `{study['mega_ultra_rare_result']['status']}`.",f"16. Recommended representation: `{study['production_representation']}`.",
      f"17. Numeric recommendation: `{study['numeric_score_recommendation']}`.",f"18. Uncertainty rules: `{json.dumps(study['uncertainty_contract'],sort_keys=True)}`.",
      "19. Comparison universe: only other evidence-supported treatments in the same Pokémon era; never cross-era, physical scarcity, Exact Pull Scarcity, or causal value.",
      f"20. Mega decision: `{json.dumps(study['era_recommendations']['Mega Evolution'],sort_keys=True)}`.",f"21. S&V decision: `{json.dumps(study['era_recommendations']['Scarlet and Violet'],sort_keys=True)}`.",
      f"22. Overall status: `{study['research_status']}`.",f"23. Backend/database contract authorized next: {study['backend_contract_authorized_next']} (implementation only; publication still requires explicit authorization).",
      "24. Rows persisted: 0 approved database rows and 0 production scores.","25. Production behavior: unchanged; no V1/V2, appeals, RIP, rankings, Card Detail, backend contract, database view, or frontend changes.",
      f"26. Files changed: {', '.join(study['files_changed'])}.",f"27. Tests executed: {', '.join(study['tests_executed'])}.",
      "28. Limitations: only two eras have Exact Pull Scarcity; historical prices use a fixed seven-day availability window; older checkpoints may omit cards without observations; market residuals remain observational; printed/surviving population, total supply, and Secondary-Market Availability / Liquidity are unobserved.",
      f"29. Recommended next task: {study['recommended_next_task']}."]
    return "# Treatment Market Prestige V3 — Round 3 Results\n\n"+f"Status: `{study['research_status']}`\n\n"+"\n\n".join(req)+"\n"


def main()->None:
    parser=argparse.ArgumentParser();parser.add_argument("--bootstrap-draws",type=int,default=399);parser.add_argument("--seed",type=int,default=SEED);parser.add_argument("--use-existing-freeze",action="store_true");args=parser.parse_args()
    main_rows,r1_manifest,r1_study=load_round1();exact,r2_manifest=load_exact();r2=json.loads(R2_STUDY.read_text(encoding="utf-8"))
    if r2_manifest["study_id"]!=R2_ID or r2["frozen_study"]["study_id"]!=R2_ID:raise RuntimeError("Round 2 authority mismatch")
    if args.use_existing_freeze:snapshots,manifest=load_checkpoints()
    else:
        load_dotenv(Path("backend/.env"));from backend.db.clients.supabase_client import create_service_role_client
        snapshots,manifest=freeze_checkpoints(main_rows,exact,r1_manifest,r2_manifest,create_service_role_client())
    results=[checkpoint_analysis(item,args.bootstrap_draws,args.seed+i*100) for i,item in enumerate(snapshots)];temporal=temporal_classification(results)
    representative=representativeness(r1_study,r2,main_rows,exact);selection=coverage_selection(main_rows,exact,r1_study);ultra_audit,ultra_result=ultra_and_contract(exact,r2,temporal,snapshots);cells=contract_cells(r2,temporal,ultra_result)
    mega_ready=temporal["Mega Evolution"]["ordering_temporally_stable"] and all(cells["Mega Evolution"][t]["status"]=="PRODUCTION_ELIGIBLE" for t in UNIVERSES["Mega Evolution"])
    sv_ready=temporal["Scarlet and Violet"]["ordering_temporally_stable"] and all(cells["Scarlet and Violet"][t]["status"]=="PRODUCTION_ELIGIBLE" for t in UNIVERSES["Scarlet and Violet"])
    if mega_ready and sv_ready:status="V3_PRODUCTION_CONTRACT_RESEARCH_VALIDATED"
    elif mega_ready or sv_ready:status="V3_TARGETED_PRODUCTION_ONLY"
    elif any(cell["status"]=="INSUFFICIENT_HISTORY" for era in temporal.values() for cell in era["treatments"].values()) and not any(cell["status"]=="TEMPORALLY_UNSTABLE" for era in temporal.values() for cell in era["treatments"].values()):status="V3_VALID_BUT_MORE_TEMPORAL_EVIDENCE_REQUIRED"
    else:status="V3_SCORE_NOT_PRODUCTION_STABLE"
    study={"study_name":"Treatment Market Prestige V3 Round 3","frozen_study":manifest,"temporal_gates":TEMPORAL_GATES,"temporal_results":results,"temporal_classification":temporal,
      "representativeness":representative,"coverage_selection":selection,"evidence_quality_contract":EVIDENCE_CONTRACT,"cell_contract_results":cells,"mega_ultra_rare_audit":ultra_audit,"mega_ultra_rare_result":ultra_result,
      "production_representation":"Rank + tier (for example, High · #1 of 3 supported same-era treatments); omit numeric score from consumer display",
      "numeric_score_recommendation":"Keep probability-of-superiority 0–10 values internal/research-only; endpoints are relative ranks and would misleadingly imply no/perfect prestige",
      "uncertainty_contract":{"unresolved_ordering":"return null rank and numeric score; may retain internal premium-treatment evidence","unsupported_treatment":"return null","cross_era_fallback":False,"api_metadata":"methodology version, era universe, support status, checkpoint date","ui":"hide unsupported score; rank/tier only when production eligible"},
      "era_recommendations":{"Mega Evolution":{"eligible_treatments":[t for t in UNIVERSES["Mega Evolution"] if cells["Mega Evolution"][t]["status"]=="PRODUCTION_ELIGIBLE"],"temporal_result":"TEMPORALLY_STABLE" if temporal["Mega Evolution"]["ordering_temporally_stable"] else ("INSUFFICIENT_HISTORY" if any(v["status"]=="INSUFFICIENT_HISTORY" for v in temporal["Mega Evolution"]["treatments"].values()) else "TEMPORALLY_UNSTABLE_OR_UNCERTAIN"),"observed_ordering_persistent":temporal["Mega Evolution"]["observed_ordering_persistent"],"production_readiness":"TARGETED_READY" if mega_ready else "NOT_READY","recommended_representation":"rank + tier","ultra_rare":ultra_result["status"]},
                             "Scarlet and Violet":{"eligible_treatments":list(UNIVERSES["Scarlet and Violet"]),"temporal_result":"TEMPORALLY_STABLE_ORDERING" if temporal["Scarlet and Violet"]["ordering_temporally_stable"] else "ORDERING_UNRESOLVED","ordering_status":"ORDERING_UNRESOLVED" if not temporal["Scarlet and Violet"]["ordering_temporally_stable"] else "ORDERED","production_readiness":"READY" if sv_ready else "NO_SCORE","unsupported_behavior":"null score/rank; no cross-era fallback"}},
      "research_status":status,"backend_contract_authorized_next":status in {"V3_PRODUCTION_CONTRACT_RESEARCH_VALIDATED","V3_TARGETED_PRODUCTION_ONLY"},"database_rows_persisted":0,"production_scores_persisted":0,
      "files_changed":["backend/scripts/build_treatment_market_prestige_v3_round3.py","backend/tests/unit/desirability/test_treatment_market_prestige_v3_round3.py","docs/research/treatment_market_prestige_v3_round3_temporal/","docs/research/treatment_market_prestige_v3_round3_study.json","docs/research/TREATMENT_MARKET_PRESTIGE_V3_ROUND3_RESULTS.md"],
      "tests_executed":["Round 3 and preserved V3/V2 research unit suites","Round 1/Round 2/Round 3 manifest and cohort hash verification"],
      "recommended_next_task":"If authorized, implement only the scoped machine-readable backend/database contract with fail-closed nulls and research-derived rank+tier semantics; do not publish or change Card Detail/frontend without a separate explicit task."}
    study=json.loads(json.dumps(study,default=lambda value:value.item() if isinstance(value,np.generic) else str(value)))
    STUDY.write_text(json.dumps(study,indent=2),encoding="utf-8");REPORT.write_text(render(study),encoding="utf-8")
    print(json.dumps({"study_id":manifest["study_id"],"status":status,"checkpoint_sizes":{x["reference_date"]:x["cohort_size"] for x in results},"database_rows_persisted":0},indent=2))


if __name__=="__main__":main()
