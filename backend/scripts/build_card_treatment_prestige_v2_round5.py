"""Diagnose Round 4 rank deficiency without refreshing its frozen cohort."""
from __future__ import annotations

import json, math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

STUDY_ID="card-treatment-b2-r4-7baa40c8c8fb299b"
MANIFEST_HASH="7baa40c8c8fb299b2251d2c2ec0363e137b5eab959beeaae7891723871cc4cdd"
MAPPING_HASH="7e0e9e2719aba8491fa777a1229cff52f23310e7fc49ca59f4a29e42fed29835"
STAGES=("treatment","scarcity","set_fe","species_fe","set_species_fe","full")


def _dummies(values, prefix):
    levels=sorted(set(values));return levels,[f"{prefix}:{x}" for x in levels[1:]]


def design(rows, treatment_b, stage):
    treatment=np.asarray([float(r["rarity_designation"]==treatment_b) for r in rows])
    cols=["intercept","treatment_b"];parts=[np.ones(len(rows)),treatment]
    if stage!="treatment":cols.append("log_odds");parts.append(np.asarray([r["log_odds"] for r in rows]))
    include_set=stage in {"set_fe","set_species_fe","full"}
    include_species=stage in {"species_fe","set_species_fe","full"}
    if include_set:
        levels,names=_dummies([r["set_id"] for r in rows],"set");cols+=names
        parts += [np.asarray([float(r["set_id"]==x) for r in rows]) for x in levels[1:]]
    if include_species:
        levels,names=_dummies([r["subject_ids"][0] for r in rows],"species");cols+=names
        parts += [np.asarray([float(r["subject_ids"][0]==x) for r in rows]) for x in levels[1:]]
    if stage=="full":
        levels,names=_dummies([str(r.get("mechanic_or_card_form") or "__unknown__") for r in rows],"mechanic");cols+=names
        parts += [np.asarray([float(str(r.get("mechanic_or_card_form") or "__unknown__")==x) for r in rows]) for x in levels[1:]]
    X=np.column_stack(parts);y=np.asarray([math.log(r["price"]) for r in rows]);s=np.linalg.svd(X,compute_uv=False)
    tolerance=max(X.shape)*s[0]*np.finfo(float).eps;rank=int(np.sum(s>tolerance))
    nuisance=np.delete(X,1,axis=1);residual=treatment-nuisance@np.linalg.lstsq(nuisance,treatment,rcond=None)[0]
    residual_variance=float(np.var(residual));estimable=float(residual@residual)>max(1e-10,1e-10*float(treatment@treatment))
    coefficient=float(np.linalg.lstsq(X,y,rcond=None)[0][1]) if estimable else None
    aliases=[]
    if rank<X.shape[1]:
        _,_,vh=np.linalg.svd(X,full_matrices=False)
        null=vh[rank:]
        involvement=np.max(np.abs(null),axis=0) if len(null) else np.zeros(X.shape[1])
        aliases=[cols[i] for i,x in enumerate(involvement) if x>.20]
    return {"stage":stage,"observations":len(rows),"columns_before_reference_reduction":2+(1 if stage!="treatment" else 0)
            +(len({r['set_id'] for r in rows}) if include_set else 0)
            +(len({r['subject_ids'][0] for r in rows}) if include_species else 0)
            +(len({str(r.get('mechanic_or_card_form') or '__unknown__') for r in rows}) if stage=='full' else 0),
        "columns_after_reference_reduction":X.shape[1],"rank":rank,"rank_deficiency":X.shape[1]-rank,
        "condition_number":float(s[0]/s[-1]) if s[-1]>tolerance else None,"treatment_variance":float(np.var(treatment)),
        "residual_treatment_variance":residual_variance,"treatment_estimable":bool(estimable),"diagnostic_coefficient":coefficient,
        "aliased_columns":aliases,"singular_values_largest":list(map(float,s[:5])),"singular_values_smallest":list(map(float,s[-5:]))}


def mixed_group(rows, keys):
    groups=defaultdict(list)
    for r in rows:groups[tuple(r[k] if k!="species" else r["subject_ids"][0] for k in keys)].append(r)
    mixed=[g for g in groups.values() if len({r["rarity_designation"] for r in g})==2]
    return {"mixed_groups":len(mixed),"observations_in_mixed_groups":sum(map(len,mixed)),
        "cohort_percentage":sum(map(len,mixed))/len(rows) if rows else 0}


def species_detail(rows, a, b):
    groups=defaultdict(list)
    for r in rows:groups[r["subject_ids"][0]].append(r)
    out=[]
    for species,group in sorted(groups.items()):
        labels={r["rarity_designation"] for r in group};by=Counter(r["rarity_designation"] for r in group)
        same_set=any({r["rarity_designation"] for r in group if r["set_id"]==sid}=={a,b} for sid in {r["set_id"] for r in group})
        mechanics={label:sorted({str(r.get("mechanic_or_card_form") or "__unknown__") for r in group if r["rarity_designation"]==label}) for label in (a,b)}
        out.append({"species_id":species,"treatment_a":a in labels,"treatment_b":b in labels,"both_inside_overlap":labels=={a,b},
            "same_set_contrast":same_set,"mechanics_by_treatment":mechanics,"mechanics_comparable":bool(set(mechanics[a])&set(mechanics[b])),
            "valid_price_observations":len(group),"n_a":by[a],"n_b":by[b]})
    return out


def diagnose(mapping, round4):
    usable=[r for r in mapping["rows"] if r.get("price") and r["price"]>0 and r.get("log_odds") is not None and len(r.get("subject_ids") or [])==1]
    results=[];high=[]
    for pair in round4["pair_results"]:
        if pair["status"]=="PAIR_SUPPORT_FAILED":continue
        a,b=pair["treatment_a"],pair["treatment_b"];low,high_bound=pair["overlap_interval_log_odds"]
        rows=[r for r in usable if r["era_id"]==pair["era_id"] and r["rarity_designation"] in {a,b} and low<=r["log_odds"]<=high_bound]
        stages=[design(rows,b,s) for s in STAGES]
        within={"species":mixed_group(rows,("species",)),"set":mixed_group(rows,("set_id",)),
            "species_set":mixed_group(rows,("species","set_id")),"mechanic":mixed_group(rows,("mechanic_or_card_form",))}
        full=stages[-1];first_loss=next((s["stage"] for s in stages if not s["treatment_estimable"]),None)
        classification="scientific_nesting" if first_loss else "mathematical_redundancy" if full["rank_deficiency"] else "full_rank"
        cause=("treatment loses all residual variation after "+first_loss if first_loss else
            "nuisance fixed-effect columns are linearly dependent, but the treatment indicator remains estimable" if full["rank_deficiency"] else "no rank failure")
        item={"era":pair["era"],"era_id":pair["era_id"],"treatment_a":a,"treatment_b":b,"observations":len(rows),
            "sets":len({r["set_id"] for r in rows}),"species":len({r["subject_ids"][0] for r in rows}),"stages":stages,
            "within_group_variation":within,"first_control_block_removing_treatment_estimability":first_loss,
            "rank_failure_classification":classification,"rank_failure_reason":cause}
        results.append(item)
        if pair.get("product_relevance")=="high":high.append({**{k:item[k] for k in ("era","era_id","treatment_a","treatment_b","rank_failure_classification","rank_failure_reason")},
            "species_identification_table":species_detail(rows,a,b)})
    return results,high


def main():
    root=Path("docs/research");freeze=root/"card_treatment_prestige_v2_frozen_cohort"
    manifest=json.loads((freeze/"manifest.json").read_text());mapping=json.loads((freeze/"canonical_mapping.json").read_text())
    prior=json.loads((root/"card_treatment_prestige_v2_study.json").read_text())
    assert manifest["study_id"]==STUDY_ID and manifest["manifest_hash"]==MANIFEST_HASH and manifest["canonical_mapping_hash"]==MAPPING_HASH
    diagnostics,high=diagnose(mapping,prior["round4"])
    treatment_estimable=sum(x["stages"][-1]["treatment_estimable"] for x in diagnostics)
    demand_audit=[{"candidate":"pokemon_desirability_composite_v1","source":"pokemon_desirability_composite_scores",
        "definition":"0.75 FavoritePokemon fan-popularity score + 0.25 Google Trends current 30-day relative search interest; fan score alone when trends missing",
        "uses_card_market_price":False,"uses_focal_outcome":False,"uses_rarity_or_treatment":False,
        "temporal_semantics":"the database audit found one 2026-06-11 composite build using fan snapshot 2 and trend snapshots 1/3, but no demand snapshot was frozen with the Round 4 cohort",
        "database_audit":{"score_rows":1025,"cohort_species":945,"covered_species":945,"coverage":1.0,
            "scoring_version":"pokemon_desirability_composite_v1","created_at":"2026-06-11T18:35:56.767591+00:00",
            "fan_snapshot_ids":[2],"trend_snapshot_ids":[1,3]},
        "leakage_assessment":"no direct focal-price or treatment leakage; possible measurement error, fan-site selection bias, search-term ambiguity, and temporal mismatch",
        "eligible_for_v2b":False,"ineligibility_reason":"Round 4 did not freeze a contemporaneous demand snapshot; querying current values would mix time authorities"},
        {"candidate":"V1 Treatment Score / card_appeal_v1","source":"application scoring rules","uses_card_market_price":False,
        "uses_focal_outcome":False,"uses_rarity_or_treatment":True,"eligible_for_v2b":False,"ineligibility_reason":"forbidden circular treatment control and not an independent species-demand measure"},
        {"candidate":"set/opening desirability and monetary chase measures","source":"derived set/product metrics","uses_card_market_price":True,
        "uses_focal_outcome":True,"uses_rarity_or_treatment":"may aggregate treated cards","eligible_for_v2b":False,"ineligibility_reason":"price leakage, aggregation mismatch, and endogeneity"}]
    future=[]
    for x in diagnostics:
        w=x["within_group_variation"];future.append({"era":x["era"],"treatment_a":x["treatment_a"],"treatment_b":x["treatment_b"],
            "new_identifying_variation_required":"new same-species observations across both designations inside shared scarcity support, preferably within the same set and comparable mechanic class",
            "current_mixed_species":w["species"]["mixed_groups"],"current_mixed_species_set_cells":w["species_set"]["mixed_groups"],
            "more_rows_in_existing_cells_help":False,"new_cross-treatment_cells_help":True})
    # Rank deficiency of the complete matrix is not automatically failure of the
    # treatment estimand. Round 4's full-rank gate was conservative and is retained.
    status="V2_ORIGINAL_ESTIMAND_REMAINS_PLAUSIBLY_IDENTIFIABLE_WITH_NEW_VARIATION" if treatment_estimable else "V2_ORIGINAL_ESTIMAND_STRUCTURALLY_UNIDENTIFIED"
    r5={"status":status,"round4_findings_preserved":True,"frozen_study_id":STUDY_ID,"manifest_hash":MANIFEST_HASH,
        "canonical_mapping_hash":MAPPING_HASH,"contrast_diagnostics":diagnostics,"high_product_relevance_deep_dive":high,
        "independent_demand_candidate_audit":demand_audit,"v2b_eligibility":{"passed":False,"coefficient_evaluation_permitted":False,
            "reason":"no eligible demand control frozen contemporaneously with the immutable cohort"},"v2b_results":None,
        "round4_common_rare_calibration":{"coefficient":0.4174,"price_association_pct":51.8,"comparison":"not run because V2B eligibility failed"},
        "future_identifying_variation":future,"treatment_estimable_in_rank_deficient_full_designs":treatment_estimable,
        "database_rows_persisted":0,"production_scores_published":0,"next_research_task":"preregister a new frozen cohort that includes an immutable independent-demand snapshot and collect new within-species cross-designation cells; do not enter V3 yet"}
    prior["round5"]=r5;prior["decision"]="DO_NOT_APPROVE_CARD_TREATMENT_PRESTIGE_V2";prior["publication"]={"committed":False,"approved":False,"study_run_id":None,"score_rows":0}
    (root/"card_treatment_prestige_v2_study.json").write_text(json.dumps(prior,indent=2),encoding="utf-8")
    print(json.dumps({"status":status,"contrasts":len(diagnostics),"treatment_estimable":treatment_estimable,"v2b_eligible":False},indent=2))


if __name__=="__main__":main()
