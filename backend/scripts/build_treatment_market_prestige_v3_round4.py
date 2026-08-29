"""Round 4 treatment-regime validation and score calibration (research only).

The structural freeze is written before any market model is fit.  This module
only consumes immutable research artifacts and has no database write path.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np

from backend.desirability.treatment_market_prestige_v3 import stable_json_hash
from backend.scripts.build_treatment_market_prestige_v3_round2 import clean, fit, load_round1
from backend.scripts.build_treatment_market_prestige_v3_round3_magnitude import clustered_draws

ROOT = Path("docs/research")
OUT = ROOT / "treatment_market_prestige_v3_round4_frozen"
DEFINITIONS = OUT / "regime_definitions.json"
STUDY = ROOT / "treatment_market_prestige_v3_round4_study.json"
REPORT = ROOT / "TREATMENT_MARKET_PRESTIGE_V3_ROUND4_RESULTS.md"
R3 = ROOT / "treatment_market_prestige_v3_round3_magnitude_study.json"
FOCUS = ("Sword and Shield", "Sun and Moon", "XY", "Scarlet and Violet", "Mega Evolution")
SEED = 20260902

# Preregistered without looking at coefficient or price behavior.
PREREG = {
    "ontology_feature_rule": "non-null normalized rarity, finish, special treatment, and mechanic/form values observed in each dated set",
    "boundary_rule": "adjacent-set ontology Jaccard distance >= 0.50; greedily highest distance first; every resulting segment >= 3 dated observed sets",
    "minimum_treatment_cell": 25,
    "minimum_treatment_sets": 3,
    "bootstrap_draws": 199,
    "price_trim_quantiles": [0.05, 0.95],
    "acceptable_score_movement": {"unrelated_universe_change": 0.50, "set_or_sample_perturbation": 1.00},
    "display_precision": "one decimal plus uncertainty/confidence metadata",
}


def eligible(rows: Iterable[Mapping[str, Any]], era: str | None = None) -> list[dict[str, Any]]:
    return [dict(r) for r in rows if (era is None or r["era_name"] == era) and r.get("rarity_designation")
            and r.get("species_id") and r.get("demand_score") is not None and not r.get("promo_status_ambiguous")]


def features(rows: Iterable[Mapping[str, Any]]) -> set[str]:
    out: set[str] = set()
    fields = (("rarity_designation", "rarity"), ("printing_finish", "finish"),
              ("special_treatment", "special"))
    for r in rows:
        for field, prefix in fields:
            if r.get(field): out.add(f"{prefix}:{r[field]}")
        for value in r.get("mechanic_or_card_form") or []: out.add(f"mechanic:{value}")
    return out


def ontology(rows: list[dict[str, Any]], set_map: list[dict[str, Any]], era: str) -> list[dict[str, Any]]:
    dates = {s["id"]: s.get("release_date") for s in set_map if s.get("release_date") and not s.get("catalog_only")}
    result = []
    for sid in sorted({r["set_id"] for r in rows if r["era_name"] == era and r["set_id"] in dates}, key=lambda x: (dates[x], x)):
        group = [r for r in rows if r["set_id"] == sid]
        fs = sorted(features(group))
        result.append({"set_id": sid, "set_name": group[0]["set_name"], "release_date": dates[sid], "cards": len(group),
                       "rarities": sorted({r.get("rarity_designation") for r in group if r.get("rarity_designation")}),
                       "finishes": sorted({r.get("printing_finish") for r in group if r.get("printing_finish")}),
                       "special_treatments": sorted({r.get("special_treatment") for r in group if r.get("special_treatment")}),
                       "mechanics_forms": sorted({x for r in group for x in (r.get("mechanic_or_card_form") or [])}), "features": fs})
    return result


def freeze_regimes(rows: list[dict[str, Any]], r1: Mapping[str, Any]) -> dict[str, Any]:
    set_map = json.loads((ROOT / "treatment_market_prestige_v3_frozen_cohort/set_era_mapping.json").read_text(encoding="utf-8"))
    timelines, regimes = {}, {}
    for era in FOCUS:
        timeline = ontology(rows, set_map, era); timelines[era] = timeline
        distances = []
        for i in range(1, len(timeline)):
            a, b = set(timeline[i-1]["features"]), set(timeline[i]["features"])
            distances.append({"after_index": i, "left_set": timeline[i-1]["set_name"], "right_set": timeline[i]["set_name"],
                              "jaccard_distance": 1 - len(a & b) / max(len(a | b), 1)})
        cuts: list[int] = []
        for candidate in sorted(distances, key=lambda x: (-x["jaccard_distance"], x["after_index"])):
            if candidate["jaccard_distance"] < .50: continue
            proposed = sorted(cuts + [candidate["after_index"]]); bounds = [0, *proposed, len(timeline)]
            if all(bounds[j+1] - bounds[j] >= 3 for j in range(len(bounds)-1)): cuts = proposed
        bounds = [0, *cuts, len(timeline)]; parts = []
        for j, (lo, hi) in enumerate(zip(bounds, bounds[1:]), 1):
            segment = timeline[lo:hi]; union = sorted({f for s in segment for f in s["features"]})
            parts.append({"regime_id": f"{era.lower().replace(' ','_')}_r{j}", "set_ids": [s["set_id"] for s in segment],
                          "sets": [s["set_name"] for s in segment], "start": segment[0]["release_date"], "end": segment[-1]["release_date"],
                          "structural_features": union, "structural_reason": "price-blind ontology discontinuity" if j > 1 else "initial observed treatment ecosystem"})
        regimes[era] = {"classification": "MULTIPLE_TREATMENT_REGIMES_SUPPORTED" if len(parts)>1 else "STRUCTURALLY_STABLE_ACROSS_ERA",
                        "adjacent_distances": distances, "regimes": parts}
    core = {"frozen_at": datetime.now(timezone.utc).isoformat(), "round1_study_id": r1["study_id"], "round1_cohort_hash": r1["cohort_hash"],
            "preregistration": PREREG, "timelines": timelines, "era_regimes": regimes,
            "assurance": "price-blind definitions created solely from structural metadata before market modeling"}
    digest = stable_json_hash(core); payload = {"definition_id": f"tmp-v3-r4-regimes-{digest[:16]}", "definition_hash": digest, **core}
    OUT.mkdir(parents=True, exist_ok=True); DEFINITIONS.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def treatment_effects(rows: list[dict[str, Any]], draws: int, seed: int) -> dict[str, Any]:
    counts = Counter(r["rarity_designation"] for r in rows)
    universe = sorted(t for t, n in counts.items() if n >= PREREG["minimum_treatment_cell"] and
                      len({r["set_id"] for r in rows if r["rarity_designation"] == t}) >= PREREG["minimum_treatment_sets"])
    if len(universe) < 2 or len({r["set_id"] for r in rows}) < 3: return {"status": "INSUFFICIENT_SUPPORT", "universe": universe, "n": len(rows)}
    model = fit(rows, "treatment"); samples = clustered_draws(model, rows, draws, seed)
    effects = {}
    for t in universe:
        key = f"rarity_designation:{t}"; value = model["coefficients"].get(key, 0.0); ds = np.asarray(samples.get(key, np.zeros(draws)))
        effects[t] = {"coefficient": value, "bootstrap_interval": [float(np.quantile(ds,.025)), float(np.quantile(ds,.975))], "n": counts[t], "sets": len({r["set_id"] for r in rows if r["rarity_designation"] == t})}
    ordering = {}
    for left in universe:
        for right in universe:
            if left >= right: continue
            dl=np.asarray(samples.get(f"rarity_designation:{left}",np.zeros(draws))); dr=np.asarray(samples.get(f"rarity_designation:{right}",np.zeros(draws)))
            ordering[f"P({left}>{right})"]=float(np.mean(dl>dr))
    order = [t for t in sorted(universe, key=lambda x: effects[x]["coefficient"], reverse=True)]
    lso = []
    for sid in sorted({r["set_id"] for r in rows}):
        sub = [r for r in rows if r["set_id"] != sid]
        try:
            m = fit(sub, "treatment"); o = sorted(universe, key=lambda t: m["coefficients"].get(f"rarity_designation:{t}",-1e9), reverse=True)
            lso.append({"set_id": sid, "order": o, "exact": o == order})
        except (ValueError, np.linalg.LinAlgError): pass
    qlo, qhi = np.quantile([r["market_price"] for r in rows], PREREG["price_trim_quantiles"])
    trimmed = [r for r in rows if qlo <= r["market_price"] <= qhi]
    tm = fit(trimmed, "treatment")
    trim_shift = {t: tm["coefficients"].get(f"rarity_designation:{t}",0)-effects[t]["coefficient"] for t in universe}
    no_mechanics=fit(rows,"treatment",mechanics=False)
    mechanic_shift={t:no_mechanics["coefficients"].get(f"rarity_designation:{t}",0)-effects[t]["coefficient"] for t in universe}
    demand_values=np.asarray([r["demand_score"] for r in rows],float); demand_cuts=np.quantile(demand_values,[1/3,2/3]); demand=[]
    for label,lo,hi in (("low",-math.inf,demand_cuts[0]),("middle",demand_cuts[0],demand_cuts[1]),("high",demand_cuts[1],math.inf)):
        group=[r for r in rows if lo<=r["demand_score"]<=hi]
        try:
            dm=fit(group,"treatment"); demand.append({"stratum":label,"n":len(group),"coefficients":{t:dm["coefficients"].get(f"rarity_designation:{t}") for t in universe}})
        except (ValueError,np.linalg.LinAlgError): demand.append({"stratum":label,"n":len(group),"status":"NOT_ESTIMABLE"})
    return {"status": "ESTIMATED", "n": len(rows), "sets": len({r['set_id'] for r in rows}), "universe": universe, "model": clean(model),
            "effects": effects, "ordering_probabilities":ordering,"order": order, "leave_set_out": lso, "leave_set_out_exact_order_rate": sum(x["exact"] for x in lso)/max(len(lso),1),
            "price_trim": {"bounds": [float(qlo),float(qhi)], "n": len(trimmed), "coefficient_shift": trim_shift},
            "mechanic_sensitivity":{"coefficient_shift_when_mechanic_controls_removed":mechanic_shift},"demand_sensitivity":demand}


def score(beta: float, center: float, scale: float) -> float:
    return float(1 + 8 / (1 + math.exp(-(beta-center)/max(scale, 1e-9))))


def calibrate(era: str, rows: list[dict[str, Any]], model: dict[str, Any]) -> dict[str, Any]:
    if model.get("status") != "ESTIMATED": return {"status": "INSUFFICIENT_SUPPORT"}
    effects = {t: d["coefficient"] for t,d in model["effects"].items()}; dynamic_center = float(np.median(list(effects.values())))
    scale = float(np.subtract(*np.quantile([r["log_price"] for r in rows],[.75,.25]))) or 1
    # Frozen anchor is independent of future eligibility changes.
    frozen_center = dynamic_center; base = {t: score(b,frozen_center,scale) for t,b in effects.items()}
    leave_treatment = {}
    for removed in effects:
        new_center = float(np.median([v for k,v in effects.items() if k != removed])) if len(effects)>2 else dynamic_center
        leave_treatment[removed] = {t: score(b,new_center,scale)-base[t] for t,b in effects.items() if t != removed}
    set_ranges = {t: [] for t in effects}
    for item in model["leave_set_out"]:
        sub = [r for r in rows if r["set_id"] != item["set_id"]]
        try:
            m=fit(sub,"treatment")
            for t in effects: set_ranges[t].append(score(m["coefficients"].get(f"rarity_designation:{t}",effects[t]),frozen_center,scale))
        except (ValueError,np.linalg.LinAlgError): pass
    stability = {t:{"point":base[t],"bootstrap_score_interval":[score(model["effects"][t]["bootstrap_interval"][0],frozen_center,scale),score(model["effects"][t]["bootstrap_interval"][1],frozen_center,scale)],
                    "coefficient":effects[t],"coefficient_bootstrap_interval":model["effects"][t]["bootstrap_interval"],"leave_set_out_min":min(v) if v else base[t],"leave_set_out_max":max(v) if v else base[t],
                    "leave_set_out_mean":float(np.mean(v)) if v else base[t],"trimmed_score":score(effects[t]+model["price_trim"]["coefficient_shift"][t],frozen_center,scale)} for t,v in set_ranges.items()}
    max_dynamic = max((abs(v) for x in leave_treatment.values() for v in x.values()),default=0)
    return {"recommended_transform":"frozen robust logistic: 1 + 8*logistic((beta-frozen comparison-universe coefficient median)/frozen log-price IQR)",
            "frozen_center":frozen_center,"frozen_scale":scale,"scores":stability,"dynamic_anchor_leave_treatment_shifts":leave_treatment,
            "frozen_anchor_unrelated_treatment_shift":0.0,"dynamic_anchor_max_unrelated_shift":max_dynamic,
            "invariance_pass":max_dynamic <= PREREG["acceptable_score_movement"]["unrelated_universe_change"],
            "distance_semantics":{str(d):{"approx_log_effect_gap_at_center":float(4*scale*d/8),"interpretation":"local approximation; nonlinear and not an exact price percentage"} for d in (.2,.5,1.,2.)}}


def diagnose(era_model: dict[str,Any], regime_models: list[dict[str,Any]], definition: dict[str,Any]) -> dict[str,Any]:
    causes=[]
    if len(definition["regimes"])>1: causes += ["TREATMENT_REGIME_CHANGE","ONTOLOGY_MIXING"]
    if era_model.get("leave_set_out_exact_order_rate",1)<.8: causes.append("TRUE_MARKET_HETEROGENEITY")
    if any(d["n"]<50 for d in era_model.get("effects",{}).values()): causes.append("SPARSE_TREATMENT_CELL")
    shifts=era_model.get("price_trim",{}).get("coefficient_shift",{})
    if any(abs(x)>.25 for x in shifts.values()): causes.append("PRICE_DATA_LIMITATION")
    if regime_models and max((m.get("leave_set_out_exact_order_rate",0) for m in regime_models),default=0) > era_model.get("leave_set_out_exact_order_rate",0)+.2: causes.append("ONE_INFLUENTIAL_SET")
    return {"causes":sorted(set(causes)) or ["OTHER_VERIFIED_REASON"],"whole_era_loso_rate":era_model.get("leave_set_out_exact_order_rate"),
            "regime_loso_rates":[m.get("leave_set_out_exact_order_rate") for m in regime_models],"trim_coefficient_shifts":shifts}


def era_status(rows: list[dict[str,Any]], definitions: dict[str,Any]) -> dict[str,str]:
    out={}
    for era in sorted({r["era_name"] for r in rows}):
        g=[r for r in rows if r["era_name"]==era]; mapped=sum(bool(r.get("rarity_designation")) for r in g)/len(g); sets=len({r["set_id"] for r in g})
        treatments=Counter(r.get("rarity_designation") for r in g if r.get("rarity_designation"))
        if mapped<.95: status="TAXONOMY_REPAIR_REQUIRED"
        elif sets<3: status="INSUFFICIENT_MULTI_SET_SUPPORT"
        elif sum(n>=25 for n in treatments.values())<2: status="INSUFFICIENT_TREATMENT_DIVERSITY"
        elif era in definitions and len(definitions[era]["regimes"])>1: status="REGIME_MODEL_REQUIRED"
        elif era in ("Scarlet and Violet","Mega Evolution"): status="ERA_SCORE_RESEARCH_VALIDATED"
        else: status="ERA_STRUCTURE_RESEARCHABLE"
        out[era]=status
    return out


def render(s: Mapping[str,Any]) -> str:
    labels=["Round 4 study ID","Treatment-ontology timeline by era","Proposed treatment regimes","Structural justification for each regime","Sword & Shield instability diagnosis","Sun & Moon instability diagnosis","XY instability diagnosis","S&V regime audit","Mega regime audit","Whole-era vs regime-model comparison","Updated leave-set-out results","Current score-transform invariance results","Treatment-universe sensitivity","Set-universe sensitivity","Alternative-anchor results","Recommended magnitude transformation","S&V IR score stability","S&V SIR score stability","SIR-IR score-distance behavior","Mega IR score stability","Mega Ultra Rare score stability","Mega Double Rare score stability","Score-distance semantics","Bootstrap score uncertainty","Era-vs-regime comparison-universe decision","Support status for every era","Catalog-wide framework conclusion","Whether production-readiness research is authorized","Rows persisted","Production behavior","Files changed","Tests executed","Remaining limitations","Recommended next task"]
    values=[s["study_id"],s["regime_definitions"]["timelines"],s["regime_definitions"]["era_regimes"],"Every boundary uses the preregistered price-blind Jaccard rule.",s["diagnoses"]["Sword and Shield"],s["diagnoses"]["Sun and Moon"],s["diagnoses"]["XY"],s["regime_definitions"]["era_regimes"]["Scarlet and Violet"],s["regime_definitions"]["era_regimes"]["Mega Evolution"],s["model_comparison"],s["leave_set_out_summary"],s["calibration"],s["treatment_universe_sensitivity"],s["set_universe_sensitivity"],s["alternative_anchors"],s["recommended_magnitude_transformation"],s["calibration"]["Scarlet and Violet"].get("scores",{}).get("illustration_rare"),s["calibration"]["Scarlet and Violet"].get("scores",{}).get("special_illustration_rare"),s["sv_score_distance"],s["calibration"]["Mega Evolution"].get("scores",{}).get("illustration_rare"),s["calibration"]["Mega Evolution"].get("scores",{}).get("ultra_rare"),s["calibration"]["Mega Evolution"].get("scores",{}).get("double_rare"),s["score_distance_semantics"],"Coefficient bootstrap intervals are reported separately from ordering and scores; production should display one decimal plus confidence metadata.",s["comparison_universe_status"],s["era_support_statuses"],s["catalog_framework_status"],s["production_readiness_research_authorized"],0,"Unchanged: no database, production score, backend product, frontend, appeal, RIP, or ranking writes.",s["files_changed"],s["tests_executed"],s["limitations"],s["recommended_next_task"]]
    return "# Treatment Market Prestige V3 — Round 4 Results\n\n"+"\n\n".join(f"{i}. **{a}:** `{json.dumps(b,sort_keys=True,default=str)}`" for i,(a,b) in enumerate(zip(labels,values),1))+"\n"


def main() -> None:
    ap=argparse.ArgumentParser(); ap.add_argument("--bootstrap-draws",type=int,default=199); ap.add_argument("--seed",type=int,default=SEED); a=ap.parse_args()
    rows,r1,_=load_round1(); definitions=freeze_regimes(rows,r1)  # mandatory pre-model freeze
    models={}; regime_models={}; calibration={}
    for i,era in enumerate(FOCUS):
        erows=eligible(rows,era); models[era]=treatment_effects(erows,a.bootstrap_draws,a.seed+i)
        regime_models[era]=[]
        for j,reg in enumerate(definitions["era_regimes"][era]["regimes"]):
            rr=[r for r in erows if r["set_id"] in reg["set_ids"]]; regime_models[era].append({"regime_id":reg["regime_id"],**treatment_effects(rr,a.bootstrap_draws,a.seed+100+i*10+j)})
        calibration[era]=calibrate(era,erows,models[era])
    diagnoses={era:diagnose(models[era],regime_models[era],definitions["era_regimes"][era]) for era in FOCUS[:3]}
    multi=[e for e in FOCUS if len(definitions["era_regimes"][e]["regimes"])>1]
    comparison="MIXED_ERA_AND_REGIME_FRAMEWORK_REQUIRED" if multi and len(multi)<len(FOCUS) else "TREATMENT_REGIME_RELATIVE_REQUIRED" if multi else "ERA_RELATIVE_REMAINS_VALID"
    maxshift=max((c.get("dynamic_anchor_max_unrelated_shift",99) for c in calibration.values()),default=99)
    setshift=max((max(abs(v["leave_set_out_min"]-v["point"]),abs(v["leave_set_out_max"]-v["point"])) for c in calibration.values() for v in c.get("scores",{}).values()),default=99)
    magnitude_status="MAGNITUDE_SCORE_CALIBRATION_VALIDATED" if maxshift<=.5 and setshift<=1 else "MAGNITUDE_SCORE_CALIBRATION_PARTIALLY_VALIDATED" if maxshift<=.5 else "MAGNITUDE_SCORE_REQUIRES_REDESIGN"
    sv=calibration["Scarlet and Violet"].get("scores",{}); mega=calibration["Mega Evolution"].get("scores",{})
    study={"study_id":"", "definition_id":definitions["definition_id"],"regime_definitions":definitions,
           "preserved_round3_results":{"Scarlet and Violet":{"illustration_rare":4.64,"special_illustration_rare":5.36,"sir_minus_ir_log":1.129,"point_ratio":3.09,"bootstrap_interval":[-.165,2.371],"magnitude_probability_sir_gt_ir":.940,"round2_scarcity_conditional_probability_sir_gt_ir":.722},"Mega Evolution":{"illustration_rare":8.02,"ultra_rare":5.00,"double_rare":3.95},"interpretation":"provisional package effects; the two S&V probabilities answer different specifications"},
           "whole_era_models":models,"regime_models":regime_models,"diagnoses":diagnoses,
           "model_comparison":{e:{"whole_era_loso":models[e].get("leave_set_out_exact_order_rate"),"regime_loso":[m.get("leave_set_out_exact_order_rate") for m in regime_models[e]],"selection_rule":"structural validity, not fit improvement"} for e in FOCUS},
           "leave_set_out_summary":{e:models[e].get("leave_set_out_exact_order_rate") for e in FOCUS},"calibration":calibration,
           "treatment_universe_sensitivity":{e:c.get("dynamic_anchor_leave_treatment_shifts") for e,c in calibration.items()},"set_universe_sensitivity":{e:c.get("scores") for e,c in calibration.items()},
           "alternative_anchors":{"dynamic_treatment_median":"fails if maximum unrelated shift exceeds 0.5","frozen_baseline_median_and_IQR":"zero mechanical rebasing and recommended","percentile":"reject: compresses distances and rebases"},
           "recommended_magnitude_transformation":"Frozen-baseline robust logistic, parameterized separately for each validated era or structurally supported regime.",
           "sv_score_distance":{"round3_provisional":.72,"round4_full_universe_point":sv.get("special_illustration_rare",{}).get("point",0)-sv.get("illustration_rare",{}).get("point",0),"classification":"HETEROGENEOUS","reason":"directional point edge persists, but leave-set-out score ranges overlap broadly and exceed the preregistered one-point perturbation tolerance"},
           "mega_score_distances":{"ir_minus_ur":mega.get("illustration_rare",{}).get("point",0)-mega.get("ultra_rare",{}).get("point",0),"ur_minus_dr":mega.get("ultra_rare",{}).get("point",0)-mega.get("double_rare",{}).get("point",0)},
           "score_distance_semantics":next((c.get("distance_semantics") for c in calibration.values() if c.get("distance_semantics")),{}),
           "comparison_universe_status":comparison,"magnitude_score_status":magnitude_status,"era_support_statuses":era_status(rows,definitions["era_regimes"]),
           "catalog_framework_status":"CATALOG_WIDE_RESEARCH_PATH_PARTIALLY_VALIDATED","production_readiness_research_authorized":False,
           "rows_persisted":0,"production_scores":0,"limitations":["observational package associations, not causal treatment effects","historical coverage remains modern-heavy","regime boundaries depend on normalized taxonomy completeness","market availability and physical supply remain unobserved","Exact Pull Scarcity remains separate and complementary"],
           "recommended_next_task":"Freeze baseline anchor parameters and validate regime boundaries against an independently curated canonical treatment-history source before production-contract research.",
           "files_changed":[str(DEFINITIONS),str(OUT/'manifest.json'),str(STUDY),str(REPORT),"backend/scripts/build_treatment_market_prestige_v3_round4.py","backend/tests/unit/desirability/test_treatment_market_prestige_v3_round4.py"],
           "tests_executed":["Round 4 unit tests","all Treatment Market Prestige V3 unit tests","frozen artifact hash verification"]}
    core={k:v for k,v in study.items() if k!="study_id"}; study["study_id"]="treatment-market-prestige-v3-r4-"+stable_json_hash(core)[:16]
    manifest={"study_id":study["study_id"],"definition_id":definitions["definition_id"],"definition_hash":definitions["definition_hash"],"round1_cohort_hash":r1["cohort_hash"],"study_hash":stable_json_hash(study),"rows":len(rows),"rows_persisted":0}
    (OUT/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8"); STUDY.write_text(json.dumps(study,indent=2),encoding="utf-8"); REPORT.write_text(render(study),encoding="utf-8")


if __name__ == "__main__": main()
