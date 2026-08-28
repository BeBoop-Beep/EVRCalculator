"""Build the preregistered Card Treatment Prestige V2 study.

The default is a non-publishing dry run.  ``--commit`` persists a research or
rejected run; ``--approve`` is separate and is refused unless every gate passes.
"""
from __future__ import annotations

import argparse, hashlib, json, math, subprocess, time
import itertools
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from dotenv import load_dotenv

from backend.desirability.card_treatment_prestige_v2 import (
    METHODOLOGY_VERSION, TAXONOMY_VERSION, common_support_bounds,
    log_pull_odds, pairwise_superiority_scores, positive_log_price,
    resolve_treatment_identity,
)

SEED = 20260828
GATES = {"min_cards": 100, "min_sets": 5, "min_species": 20,
         "min_finish_matches": 50, "min_rank_spearman": .85,
         "max_abs_log_effect_shift": .50, "min_common_support_coverage": .50,
         "max_exact_canonical_join_failure_rate": .05, "max_unmapped_taxonomy_rate": .05}

FAILURE_CODES = {
    "authoritative_pull_source_unavailable", "insufficient_exact_scarcity_coverage",
    "insufficient_common_support", "insufficient_treatment_sample",
    "insufficient_set_diversity", "insufficient_era_diversity",
    "insufficient_matched_variant_coverage", "required_controls_unavailable",
    "excessive_canonical_join_failures", "excessive_unmapped_taxonomy_rate",
}

PAIRWISE_GATES = {"min_per_treatment":50,"min_inside_overlap_each":25,
                  "min_overlap_pct_each":.25,"min_sets":5,"min_species":20}


def paged(query, page=500):
    out=[]
    for start in range(0, 10_000_000, page):
        error=None
        for attempt in range(3):
            try: rows=list(query.range(start,start+page-1).execute().data or []); break
            except Exception as exc:
                error=exc
                if attempt<2: time.sleep(2*(attempt+1))
        else: raise RuntimeError(f"database read failed at offset {start}") from error
        out.extend(rows)
        if len(rows)<page: break
    return out


def chunks(values, n=150):
    values=list(values)
    for i in range(0,len(values),n): yield values[i:i+n]


def fetch_in(client, table, columns, key, values):
    return [row for part in chunks(values) for row in paged(client.table(table).select(columns).in_(key,part))]


def normalize_dimension(value):
    import re, unicodedata
    raw=unicodedata.normalize("NFKD",str(value or "")).encode("ascii","ignore").decode()
    text=re.sub(r"[^a-z0-9]+","_",raw.strip().lower()).strip("_")
    return text or None


def current_run_authority(client, supported_set_ids):
    """Narrow JSON projection; never downloads the large snapshot payload."""
    rows=[]
    for part in chunks(supported_set_ids,50):
        rows.extend(paged(client.table("pokemon_set_page_snapshot_latest").select(
            "set_id,source_run_id:payload_json->ripDecision->>sourceCalculationRunId"
        ).in_("set_id",part)))
    return {str(r["set_id"]):str(r["source_run_id"]) for r in rows if r.get("source_run_id")}


def distribution(values):
    if not values:return None
    a=np.asarray(values,float)
    return {"n":len(a),"min":float(a.min()),"p10":float(np.quantile(a,.10)),
        "p25":float(np.quantile(a,.25)),"median":float(np.median(a)),
        "p75":float(np.quantile(a,.75)),"p90":float(np.quantile(a,.90)),"max":float(a.max())}


def dimension_table(rows, field):
    groups=defaultdict(list)
    for row in rows:groups[str(row.get(field) or "__unknown__")].append(row)
    return [{"value":key,"observations":len(group),"pull_covered":sum(bool(r.get("exact_pull")) for r in group),
             "priced":sum(bool(r.get("priced")) for r in group),
             "unmapped":sum(bool(r.get("unmapped")) for r in group)} for key,group in sorted(groups.items())]


def support_audit(rows, field, scope_field=None):
    scopes=defaultdict(list)
    for row in rows:
        if row.get("exact_pull") is not None:scopes[str(row.get(scope_field) or "global")].append(row)
    output={}
    for scope,group in scopes.items():
        by=defaultdict(list)
        for row in group:by[str(row.get(field) or "__unknown__")].append(row["log_odds"])
        eligible={k:v for k,v in by.items() if len(v)>=5}
        bounds=common_support_bounds(eligible) if len(eligible)>=2 else None
        covered=sum(bounds[0]<=x<=bounds[1] for values in eligible.values() for x in values) if bounds else 0
        denominator=sum(map(len,eligible.values()))
        output[scope]={"groups":{k:distribution(v) for k,v in sorted(by.items())},
            "eligible_group_count":len(eligible),"common_support_bounds_log_odds":bounds,
            "common_support_coverage":covered/denominator if denominator else 0}
    return output


def pairwise_overlap(rows, field):
    groups=defaultdict(list)
    for row in rows:
        if row.get("log_odds") is not None and row.get(field):groups[str(row[field])].append(row)
    matrix=[]
    for a,b in itertools.combinations(sorted(groups),2):
        ga,gb=groups[a],groups[b];va=[r["log_odds"] for r in ga];vb=[r["log_odds"] for r in gb]
        low=max(min(va),min(vb));high=min(max(va),max(vb));has_overlap=low<=high
        ina=[r for r in ga if has_overlap and low<=r["log_odds"]<=high];inb=[r for r in gb if has_overlap and low<=r["log_odds"]<=high]
        card_a={r["canonical_card_id"] for r in ga};card_b={r["canonical_card_id"] for r in gb};matched=card_a&card_b
        sets={r["set_id"] for r in ina+inb};species={x for r in ina+inb for x in r.get("subject_ids",[])}
        direct=(len(ga)>=PAIRWISE_GATES["min_per_treatment"] and len(gb)>=PAIRWISE_GATES["min_per_treatment"]
            and len(ina)>=PAIRWISE_GATES["min_inside_overlap_each"] and len(inb)>=PAIRWISE_GATES["min_inside_overlap_each"]
            and len(ina)/len(ga)>=PAIRWISE_GATES["min_overlap_pct_each"] and len(inb)/len(gb)>=PAIRWISE_GATES["min_overlap_pct_each"]
            and len(sets)>=PAIRWISE_GATES["min_sets"] and len(species)>=PAIRWISE_GATES["min_species"])
        local=(not direct and has_overlap and len(ina)>=10 and len(inb)>=10 and len(sets)>=2)
        matrix.append({"treatment_a":a,"treatment_b":b,"n_a":len(ga),"n_b":len(gb),
            "distribution_a":distribution(va),"distribution_b":distribution(vb),
            "sets":len({r["set_id"] for r in ga+gb}),"eras":len({r["era_id"] for r in ga+gb}),
            "species":len({x for r in ga+gb for x in r.get("subject_ids",[])}),"matched_card_groups":len(matched),
            "overlap_interval_log_odds":[low,high] if has_overlap else None,"inside_overlap_a":len(ina),"inside_overlap_b":len(inb),
            "overlap_pct_a":len(ina)/len(ga),"overlap_pct_b":len(inb)/len(gb),
            "overlap_sets":len(sets),"overlap_species":len(species),
            "era_scope":sorted({r["era_id"] for r in ina+inb}),
            "classification":"directly_identifiable_pair" if direct else "locally_identifiable_pair" if local else "unsupported_pair",
            "depends_on_extrapolation":not direct})
    return matrix


def graph_summary(matrix):
    nodes=sorted({x[k] for x in matrix for k in ("treatment_a","treatment_b")});adj={n:set() for n in nodes};edges=[]
    for row in matrix:
        if row["classification"]=="directly_identifiable_pair":
            a,b=row["treatment_a"],row["treatment_b"];adj[a].add(b);adj[b].add(a);edges.append(row)
    components=[];seen=set()
    for node in nodes:
        if node in seen:continue
        stack=[node];component=[];seen.add(node)
        while stack:
            cur=stack.pop();component.append(cur)
            for other in adj[cur]-seen:seen.add(other);stack.append(other)
        components.append(sorted(component))
    component_by_node={node:i for i,component in enumerate(components) for node in component}
    direct_keys={tuple(sorted((x["treatment_a"],x["treatment_b"]))) for x in edges}
    indirect=[{"treatment_a":a,"treatment_b":b,"classification":"connected_only_through_other_treatments"}
        for a,b in itertools.combinations(nodes,2) if component_by_node[a]==component_by_node[b] and tuple(sorted((a,b))) not in direct_keys]
    return {"nodes":nodes,"direct_edges":edges,"connected_components":components,"indirect_only_pairs":indirect,
        "warning":"Connectivity through intermediate treatments is not a direct A-versus-C identification claim."}


def structural_diagnostic(rows, field):
    usable=[r for r in rows if r.get("log_odds") is not None and r.get(field)]
    if not usable:return {"n":0}
    y=np.asarray([r["log_odds"] for r in usable]);mean=float(y.mean());groups=defaultdict(list)
    for r in usable:groups[str(r[field])].append(r["log_odds"])
    between=sum(len(v)*(float(np.mean(v))-mean)**2 for v in groups.values());total=float(np.sum((y-mean)**2))
    return {"n":len(usable),"categories":len(groups),"eta_squared_treatment_to_log_scarcity":between/total if total else 1,
        "within_category_variance":float(np.mean([np.var(v) for v in groups.values()])),
        "interpretation":"Values near one indicate scarcity band is structurally determined by treatment."}


def matched_experiment_audit(rows):
    groups=defaultdict(list)
    for r in rows:
        if r.get("exact_pull") is not None and r.get("priced"):groups[r["canonical_card_id"]].append(r)
    pairs=[]
    for card_id,group in groups.items():
        for a,b in itertools.combinations(group,2):
            if a.get("combined_treatment_key")==b.get("combined_treatment_key"):continue
            ratio=max(a["exact_pull"],b["exact_pull"])/min(a["exact_pull"],b["exact_pull"])
            pairs.append({"canonical_card_id":card_id,"set_id":a["set_id"],"species_ids":a.get("subject_ids",[]),
                "card_name":a.get("card_name"),"card_number":a.get("card_number"),"artist":a.get("artist"),
                "mechanic_or_card_form":a.get("mechanic_or_card_form"),
                "treatment_a":a.get("combined_treatment_key"),"treatment_b":b.get("combined_treatment_key"),
                "probability_a":a["exact_pull"],"probability_b":b["exact_pull"],"relative_scarcity_ratio":ratio,
                "same_release_mechanics":a["current_run_id"]==b["current_run_id"],
                "assignment_probabilities_independently_known":True})
    repeated=Counter(tuple(sorted((p["treatment_a"],p["treatment_b"]))) for p in pairs)
    return {"candidate_pairs":len(pairs),"within_10_pct":sum(p["relative_scarcity_ratio"]<=1.10 for p in pairs),
        "within_25_pct":sum(p["relative_scarcity_ratio"]<=1.25 for p in pairs),
        "within_50_pct":sum(p["relative_scarcity_ratio"]<=1.50 for p in pairs),
        "repeated_comparisons":[{"pair":list(k),"n":v} for k,v in repeated.most_common()],"candidate_examples":pairs[:100],
        "quasi_experiment_status":"diagnostic_candidates_only_no_random_or_as_if_random_assignment",
        "note":"Shared canonical identity controls subject, artwork/card identity, set, release, number and mechanics where canonical mapping is correct; it does not make treatment assignment exogenous."}


def build_round2_audit(client, as_of):
    sets=paged(client.table("sets").select("id,name,era_id,supports_opening_simulation").eq("supports_opening_simulation",True))
    set_by_id={str(r["id"]):r for r in sets};snapshot_run_by_set=current_run_authority(client,set_by_id)
    published_exact=paged(client.table("simulation_card_variant_pull_rates").select("set_id,calculation_run_id,created_at"))
    newest_exact={}
    for row in published_exact:
        sid=str(row.get("set_id"));stamp=str(row.get("created_at") or "")
        if sid in set_by_id and (sid not in newest_exact or stamp>newest_exact[sid][0]):
            newest_exact[sid]=(stamp,str(row.get("calculation_run_id")))
    # Mirrors Card Detail: newest published exact run, then set-page snapshot.
    run_by_set={sid:(newest_exact.get(sid) or (None,snapshot_run_by_set.get(sid)))[1] for sid in set_by_id
                if (newest_exact.get(sid) or (None,snapshot_run_by_set.get(sid)))[1]}
    run_ids=list(run_by_set.values()); exact=[]; inputs=[]
    for part in chunks(run_ids,50):
        exact.extend(paged(client.table("simulation_card_variant_pull_rates").select(
            "calculation_run_id,set_id,card_id,card_variant_id,printing_type,special_type,modeled_probability,effective_pull_rate,status,model_source,model_version"
        ).in_("calculation_run_id",part)))
        inputs.extend(paged(client.table("simulation_input_cards").select(
            "calculation_run_id,card_id,card_variant_id,condition_id,effective_pull_rate,rarity_bucket"
        ).in_("calculation_run_id",part)))
    exact_by_variant={str(r["card_variant_id"]):r for r in exact if r.get("card_variant_id") and log_pull_odds(r.get("modeled_probability") or r.get("effective_pull_rate")) is not None}
    conditions=paged(client.table("conditions").select("id,name").eq("name","Near Mint"))
    exact_prices=stable_prices(client,exact_by_variant,str(conditions[0]["id"]),as_of,30) if conditions else {}
    variants=[]
    legacy=[]
    for part in chunks(set_by_id,20):legacy.extend(paged(client.table("cards").select("id,set_id,pokemon_tcg_api_id,name,rarity").in_("set_id",part)))
    legacy_by_id={str(r["id"]):r for r in legacy};legacy_ids=list(legacy_by_id)
    for part in chunks(legacy_ids,100):variants.extend(paged(client.table("card_variants").select("id,card_id,printing_type,special_type,edition").in_("card_id",part)))
    canonical=[]
    for part in chunks(set_by_id,20):canonical.extend(paged(client.table("pokemon_canonical_cards").select(
        "id,set_id,pokemon_tcg_api_card_id,name,number,printed_number,rarity,supertype,subtypes,artist").in_("set_id",part)))
    canon_by_api={(str(r["set_id"]),str(r.get("pokemon_tcg_api_card_id"))):r for r in canonical}
    market=[]
    for part in chunks(set_by_id,20):market.extend(paged(client.table("pokemon_canonical_card_market_prices_latest").select(
        "canonical_card_id,card_variant_id,market_price,condition_id,set_id").in_("set_id",part)))
    priced_variants={str(r["card_variant_id"]) for r in market if r.get("card_variant_id") and positive_log_price(r.get("market_price")) is not None}
    links=paged(client.table("pokemon_card_desirability_links").select("pokemon_canonical_card_id,pokemon_reference_id"));link_by_card=defaultdict(list)
    for link in links:link_by_card[str(link["pokemon_canonical_card_id"])].append(link)
    rows=[];join_failures=Counter()
    for variant in variants:
        old=legacy_by_id.get(str(variant.get("card_id")))
        card=canon_by_api.get((str((old or {}).get("set_id")),str((old or {}).get("pokemon_tcg_api_id")))) if old else None
        if not old:join_failures["variant_to_legacy"]+=1;continue
        if not card:join_failures["legacy_to_canonical"]+=1;continue
        treatment=resolve_treatment_identity(rarity=card.get("rarity") or old.get("rarity"),printing_type=variant.get("printing_type"),
            special_type=variant.get("special_type"),edition=variant.get("edition"))
        exact_row=exact_by_variant.get(str(variant["id"]));probability=(exact_row or {}).get("modeled_probability") or (exact_row or {}).get("effective_pull_rate")
        rows.append({"set_id":str(old["set_id"]),"set_name":set_by_id[str(old["set_id"])]["name"],
            "era_id":str(set_by_id[str(old["set_id"])].get("era_id") or ""),"variant_id":str(variant["id"]),
            "canonical_card_id":str(card["id"]),"rarity_raw":card.get("rarity") or old.get("rarity"),
            "rarity_designation":treatment.rarity_key or normalize_dimension(card.get("rarity") or old.get("rarity")),
            "printing_finish_raw":variant.get("printing_type"),"printing_finish":treatment.printing_type or normalize_dimension(variant.get("printing_type")),
            "special_treatment_raw":variant.get("special_type"),"special_treatment":treatment.special_type or normalize_dimension(variant.get("special_type")),
            "edition_status_raw":variant.get("edition"),"edition_status":treatment.edition or normalize_dimension(variant.get("edition")),
            "mechanic_or_card_form_raw":card.get("subtypes") or [],
            "mechanic_or_card_form":"|".join(sorted(normalize_dimension(x) for x in card.get("subtypes") or [] if normalize_dimension(x))) or None,
            "card_name":card.get("name"),"card_number":card.get("printed_number") or card.get("number"),"artist":card.get("artist"),
            "combined_treatment_key":treatment.treatment_key,"unmapped":treatment.status!="mapped",
            "priced":str(variant["id"]) in priced_variants or str(variant["id"]) in exact_prices,
            "price_basis":"trailing_30d_nm" if str(variant["id"]) in exact_prices else ("canonical_latest" if str(variant["id"]) in priced_variants else None),
            "exact_pull":probability if log_pull_odds(probability) is not None else None,
            "log_odds":log_pull_odds(probability),"subject_ids":[str(x["pokemon_reference_id"]) for x in link_by_card.get(str(card["id"]),[])],
            "current_run_id":run_by_set.get(str(old["set_id"])),
            "snapshot_run_id":snapshot_run_by_set.get(str(old["set_id"])),
            "exact_run_precedence_used":str(old["set_id"]) in newest_exact})
    exact_joined={r["variant_id"] for r in rows if r.get("exact_pull") is not None}
    join_failures["exact_variant_without_canonical_join"]=len(set(exact_by_variant)-exact_joined)
    per_set=[]
    for sid,s in set_by_id.items():
        group=[r for r in rows if r["set_id"]==sid];covered=[r for r in group if r.get("exact_pull") is not None]
        multi=defaultdict(set)
        for r in covered:multi[r["canonical_card_id"]].add(r["combined_treatment_key"])
        per_set.append({"set_id":sid,"set_name":s["name"],"era_id":str(s.get("era_id") or ""),"current_run_id":run_by_set.get(sid),
            "snapshot_run_id":snapshot_run_by_set.get(sid),"exact_run_precedence_used":sid in newest_exact,
            "run_ids_differ":bool(sid in newest_exact and newest_exact[sid][1]!=snapshot_run_by_set.get(sid)),
            "canonical_priced_cards":len({r["canonical_card_id"] for r in group if r["priced"]}),"canonical_variants":len(group),
            "exact_pull_covered_variants":len(covered),"pull_coverage_pct":100*len(covered)/len(group) if group else 0,
            "subject_linked_observations":sum(bool(r["subject_ids"]) for r in group),
            "treatment_classes":len({r["combined_treatment_key"] for r in group if r["combined_treatment_key"]}),
            "species_in_multiple_treatments":len({sp for sp in {x for r in covered for x in r["subject_ids"]}
                if len({r["combined_treatment_key"] for r in covered if sp in r["subject_ids"]})>1}),
            "matched_cards":sum(len(v)>=2 for v in multi.values()),"unmapped_treatment_count":sum(r["unmapped"] for r in group)})
    dimensions={field:{"unique_values":len({r.get(field) for r in rows}),"frequency":dimension_table(rows,field)} for field in
        ("rarity_designation","printing_finish","special_treatment","edition_status","mechanic_or_card_form","combined_treatment_key")}
    cells=Counter(r.get("combined_treatment_key") or "__unmapped__" for r in rows);sizes=list(cells.values())
    matched=defaultdict(list)
    for r in rows:
        if r.get("exact_pull") is not None and r["priced"]:matched[r["canonical_card_id"]].append(r)
    matched_groups={k:v for k,v in matched.items() if len({r["variant_id"] for r in v})>=2 and len({r["combined_treatment_key"] for r in v})>=2}
    failures=[]
    exact_sets=len({r["set_id"] for r in rows if r.get("exact_pull") is not None});exact_eras=len({r["era_id"] for r in rows if r.get("exact_pull") is not None})
    if len(run_by_set)<len(set_by_id):failures.append("authoritative_pull_source_unavailable")
    if exact_sets<5:failures.append("insufficient_set_diversity")
    if exact_eras<2:failures.append("insufficient_era_diversity")
    if len(exact_by_variant)<100:failures.append("insufficient_exact_scarcity_coverage")
    combined_support=support_audit(rows,"combined_treatment_key").get("global",{})
    if combined_support.get("common_support_coverage",0)<GATES["min_common_support_coverage"]:failures.append("insufficient_common_support")
    if len(matched_groups)<GATES["min_finish_matches"]:failures.append("insufficient_matched_variant_coverage")
    exact_join_failure_rate=join_failures["exact_variant_without_canonical_join"]/len(exact_by_variant) if exact_by_variant else 1
    unmapped_rate=sum(r["unmapped"] for r in rows)/len(rows) if rows else 1
    authority_fingerprint=hashlib.sha256(json.dumps({
        "runs":sorted(run_by_set.items()),
        "exact_variants":sorted((variant_id,str(row.get("calculation_run_id")),row.get("modeled_probability"),row.get("effective_pull_rate"))
            for variant_id,row in exact_by_variant.items()),
    },sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
    if exact_join_failure_rate>GATES["max_exact_canonical_join_failure_rate"]:failures.append("excessive_canonical_join_failures")
    if unmapped_rate>GATES["max_unmapped_taxonomy_rate"]:failures.append("excessive_unmapped_taxonomy_rate")
    pairwise={field:pairwise_overlap(rows,field) for field in
        ("rarity_designation","printing_finish","special_treatment","edition_status","combined_treatment_key")}
    graphs={field:graph_summary(matrix) for field,matrix in pairwise.items()}
    era_values=sorted({r["era_id"] for r in rows if r.get("exact_pull") is not None})
    pairwise_by_era={era:{field:pairwise_overlap([r for r in rows if r["era_id"]==era],field) for field in pairwise}
        for era in era_values}
    graphs_by_era={era:{field:graph_summary(matrix) for field,matrix in fields.items()} for era,fields in pairwise_by_era.items()}
    direct_pairs=sum(len(graph["direct_edges"]) for fields in graphs_by_era.values() for graph in fields.values())
    return {"authoritative_pull_source":{"current_run_relation":"pokemon_set_page_snapshot_latest",
        "current_run_expression":"payload_json.ripDecision.sourceCalculationRunId","card_level_relation":"simulation_input_cards",
        "exact_variant_relation":"simulation_card_variant_pull_rates","probability_field":"modeled_probability",
        "denominator_field":"effective_pull_rate","identity_keys":["calculation_run_id","set_id","card_id","card_variant_id"],
        "semantics":"run-scoped exact card-variant pack-presence frequency from authoritative V2 simulator"},
        "read_path":{"status":"repaired","root_cause":"entire large snapshot payload_json downloaded to extract one run id",
        "repair":"PostgREST projects the snapshot run id server-side and mirrors Card Detail precedence: newest published exact-variant run, then snapshot run",
        "sets_using_exact_run_precedence":len(newest_exact),"sets_where_exact_and_snapshot_run_differ":sum(newest_exact[s][1]!=snapshot_run_by_set.get(s) for s in newest_exact)},
        "authority_cohort_fingerprint":authority_fingerprint,
        "data_state":{"authoritative_run_ids":"available","exact_variant_data":"available_but_incomplete_by_set",
            "card_level_data":"available_at_insufficient_printing_granularity","query_path":"repaired"},
        "supported_sets":len(set_by_id),"current_run_ids":len(run_by_set),"card_level_input_rows":len(inputs),
        "exact_variant_rows":len(exact_by_variant),"taxonomy_rows":len(rows),"dimensions":dimensions,
        "combined_cell_sparsity":{"cells":len(cells),"median_observations":float(np.median(sizes)) if sizes else 0,
            "below_5":sum(n<5 for n in sizes),"below_10":sum(n<10 for n in sizes),"below_25":sum(n<25 for n in sizes),"below_50":sum(n<50 for n in sizes)},
        "per_set":per_set,"per_era":[{"era_id":era,"sets":len({x["set_id"] for x in per_set if x["era_id"]==era}),
            "canonical_variants":sum(x["canonical_variants"] for x in per_set if x["era_id"]==era),
            "exact_pull_covered_variants":sum(x["exact_pull_covered_variants"] for x in per_set if x["era_id"]==era)} for era in sorted({x["era_id"] for x in per_set})],
        "join_failures":dict(join_failures),"exact_canonical_join_failure_rate":exact_join_failure_rate,
        "unmapped_total":sum(r["unmapped"] for r in rows),"unmapped_rate":unmapped_rate,
        "common_support":{"combined_global":support_audit(rows,"combined_treatment_key"),"combined_by_era":support_audit(rows,"combined_treatment_key","era_id"),
            "rarity_global":support_audit(rows,"rarity_designation"),"rarity_by_era":support_audit(rows,"rarity_designation","era_id"),
            "finish_global":support_audit(rows,"printing_finish"),"finish_by_set":support_audit(rows,"printing_finish","set_id")},
        "matched_variant":{"pull_covered_priced_groups":len(matched_groups),"minimum_gate":GATES["min_finish_matches"]},
        "pairwise_gates":PAIRWISE_GATES,"pairwise_overlap":pairwise,"support_graphs":graphs,
        "pairwise_overlap_by_era":pairwise_by_era,"support_graphs_by_era":graphs_by_era,
        "matched_natural_experiment":matched_experiment_audit(rows),
        "structural_scarcity":{field:structural_diagnostic(rows,field) for field in
            ("rarity_designation","printing_finish","special_treatment","combined_treatment_key")},
        "final_v2_status":"V2_LOCAL_IDENTIFICATION_EXISTS" if direct_pairs else "RETIRE_PURE_TREATMENT_PRESTIGE_V2",
        "directly_identifiable_pair_count":direct_pairs,
        "v3_redefinition_gate":{"entered":False if direct_pairs else True,
            "reason":"Status A requires review before V3" if direct_pairs else "pure V2 retired"},
        "pre_model_gate":{"passed":not failures,"failure_reasons":failures,"regression_executed":False},
        "recommended_specification":{"representation":"decomposed additive effects only where support passes",
            "included":["species fixed effects","log exact pull odds","set fixed effects","mechanic controls"],
            "candidate_dimensions":["rarity_designation","printing_finish","edition_status"],
            "excluded":"special/edition interactions until cell and common-support gates pass"},
        "recommended_score_universe":"not_scoreable_with_current_evidence"}


def latest_exact_rates(client):
    rows=paged(client.table("simulation_card_variant_pull_rates").select("*"))
    newest={}
    for row in rows:
        sid=str(row.get("set_id")); stamp=str(row.get("created_at") or "")
        if sid not in newest or stamp>newest[sid][0]: newest[sid]=(stamp,str(row.get("calculation_run_id")))
    return [r for r in rows if newest.get(str(r.get("set_id")),("",None))[1]==str(r.get("calculation_run_id"))
            and log_pull_odds(r.get("modeled_probability") or r.get("effective_pull_rate")) is not None]


def stable_prices(client, variant_ids, condition_id, as_of, days):
    start=(as_of-timedelta(days=days-1)).isoformat(); end=(as_of+timedelta(days=1)).isoformat()
    values=defaultdict(list)
    for part in chunks(variant_ids,75):
        q=client.table("card_variant_price_observations").select("card_variant_id,condition_id,market_price,captured_at") \
            .in_("card_variant_id",part).eq("condition_id",condition_id).gte("captured_at",start).lt("captured_at",end)
        for row in paged(q):
            price=row.get("market_price")
            if positive_log_price(price) is not None: values[str(row["card_variant_id"])].append(float(price))
    return {key:float(np.median(prices)) for key,prices in values.items() if prices}


def build_cohort(client, as_of, window=30):
    conditions=paged(client.table("conditions").select("id,name").eq("name","Near Mint"))
    if not conditions: raise RuntimeError("Near Mint condition is unavailable")
    condition_id=str(conditions[0]["id"]); rates=latest_exact_rates(client)
    variant_ids={str(r["card_variant_id"]) for r in rates if r.get("card_variant_id")}
    variants={str(r["id"]):r for r in fetch_in(client,"card_variants","id,card_id,printing_type,special_type,edition", "id",variant_ids)}
    card_ids={str(r["card_id"]) for r in variants.values() if r.get("card_id")}
    legacy={str(r["id"]):r for r in fetch_in(client,"cards","id,set_id,pokemon_tcg_api_id,name,rarity", "id",card_ids)}
    sets={str(r["id"]):r for r in paged(client.table("sets").select("id,name,era_id,release_date,supports_opening_simulation"))}
    canonical=paged(client.table("pokemon_canonical_cards").select("id,set_id,pokemon_tcg_api_card_id,name,rarity,supertype,subtypes,artist"))
    canonical_by_api={(str(r.get("set_id")),str(r.get("pokemon_tcg_api_card_id"))):r for r in canonical}
    links=paged(client.table("pokemon_card_desirability_links").select("pokemon_canonical_card_id,pokemon_reference_id,contribution_weight"))
    by_canon=defaultdict(list)
    for link in links: by_canon[str(link["pokemon_canonical_card_id"])].append(link)
    prices=stable_prices(client,variant_ids,condition_id,as_of,window)
    rows=[]; dropped=Counter()
    for rate in rates:
        vid=str(rate.get("card_variant_id")); variant=variants.get(vid); old=legacy.get(str((variant or {}).get("card_id")))
        if not variant or not old: dropped["identity_join"]+=1; continue
        card=canonical_by_api.get((str(old.get("set_id")),str(old.get("pokemon_tcg_api_id"))))
        if not card: dropped["canonical_join"]+=1; continue
        identity=resolve_treatment_identity(rarity=card.get("rarity") or old.get("rarity"),
            printing_type=variant.get("printing_type"),special_type=variant.get("special_type"),edition=variant.get("edition"))
        if not identity.treatment_key: dropped[identity.status]+=1; continue
        price=prices.get(vid); lp=positive_log_price(price); odds=log_pull_odds(rate.get("modeled_probability") or rate.get("effective_pull_rate"))
        subjects=by_canon.get(str(card["id"]),[])
        if lp is None: dropped["no_30d_nm_price"]+=1; continue
        if odds is None: dropped["no_exact_pull_probability"]+=1; continue
        rows.append({"variant_id":vid,"legacy_card_id":str(old["id"]),"canonical_card_id":str(card["id"]),
            "set_id":str(old["set_id"]),"era_id":str((sets.get(str(old["set_id"])) or {}).get("era_id") or ""),
            "treatment":identity.treatment_key,"rarity_key":identity.rarity_key,"printing_type":identity.printing_type,
            "special_type":identity.special_type,"edition":identity.edition,"supertype":card.get("supertype"),
            "species":str(subjects[0].get("pokemon_reference_id")) if len(subjects)==1 else None,
            "subject_count":len(subjects),"subtypes":card.get("subtypes") or [],"artist":card.get("artist"),
            "price":price,"log_price":lp,"log_odds":odds,"probability":math.exp(-odds),
            "run_id":str(rate.get("calculation_run_id")),"price_observations":None})
    return rows,dict(dropped),{"condition_id":condition_id,"rates":len(rates),"prices":len(prices),"sets":sets}


def build_primary_cohort(client, as_of, window=30):
    """Study A: canonical cards with analytic set/rarity pull assumptions."""
    conditions=paged(client.table("conditions").select("id,name").eq("name","Near Mint"))
    condition_id=str(conditions[0]["id"])
    supported=paged(client.table("sets").select("id").eq("supports_opening_simulation",True))
    snapshots=[]
    for item in supported:
        snapshots.extend(paged(client.table("pokemon_set_page_snapshot_latest").select("set_id,payload_json").eq("set_id",item["id"]),page=5))
    odds_by_set={}; raw_assumptions=0
    for snap in snapshots:
        payload=snap.get("payload_json") or {}; assumptions=payload.get("pull_rate_assumptions") or payload.get("pullRateAssumptions") or {}
        mapping={}
        for entry in assumptions.get("rows") or []:
            rarity=resolve_treatment_identity(rarity=entry.get("rarity")).rarity_key
            denominator=entry.get("specific_card_odds_denominator")
            try: denominator=float(denominator)
            except (TypeError,ValueError): continue
            if rarity and denominator>0: mapping.setdefault(rarity,1/denominator);raw_assumptions+=1
        if mapping:odds_by_set[str(snap["set_id"])]=mapping
    set_ids=set(odds_by_set); cards=[]
    for part in chunks(set_ids,30):cards.extend(paged(client.table("pokemon_canonical_cards").select("id,set_id,name,rarity,supertype,subtypes,artist").in_("set_id",part)))
    market=[]
    for part in chunks(set_ids,10):market.extend(paged(client.table("pokemon_canonical_card_market_prices_latest").select("canonical_card_id,card_variant_id,condition_id,set_id").in_("set_id",part)))
    market_by_card={str(r["canonical_card_id"]):r for r in market if r.get("card_variant_id")}
    variant_ids={str(r["card_variant_id"]) for r in market_by_card.values()}; prices=stable_prices(client,variant_ids,condition_id,as_of,window)
    links=paged(client.table("pokemon_card_desirability_links").select("pokemon_canonical_card_id,pokemon_reference_id,contribution_weight"));by_canon=defaultdict(list)
    for link in links:by_canon[str(link["pokemon_canonical_card_id"])].append(link)
    sets={str(r["id"]):r for r in paged(client.table("sets").select("id,era_id"))};rows=[];dropped=Counter()
    for card in cards:
        identity=resolve_treatment_identity(rarity=card.get("rarity"))
        if not identity.treatment_key:dropped[identity.status]+=1;continue
        probability=(odds_by_set.get(str(card["set_id"])) or {}).get(identity.rarity_key)
        market_row=market_by_card.get(str(card["id"]));price=prices.get(str((market_row or {}).get("card_variant_id")))
        if positive_log_price(price) is None:dropped["no_30d_nm_price"]+=1;continue
        if log_pull_odds(probability) is None:dropped["no_analytic_pull_probability"]+=1;continue
        subjects=by_canon.get(str(card["id"]),[])
        rows.append({"variant_id":str(market_row["card_variant_id"]),"canonical_card_id":str(card["id"]),"legacy_card_id":None,
            "set_id":str(card["set_id"]),"era_id":str((sets.get(str(card["set_id"])) or {}).get("era_id") or ""),
            "treatment":identity.treatment_key,"rarity_key":identity.rarity_key,"printing_type":None,"special_type":None,"edition":None,
            "supertype":card.get("supertype"),"species":str(subjects[0]["pokemon_reference_id"]) if len(subjects)==1 else None,
            "subject_count":len(subjects),"subtypes":card.get("subtypes") or [],"artist":card.get("artist"),"price":price,
            "log_price":positive_log_price(price),"log_odds":log_pull_odds(probability),"probability":probability,
            "run_id":"pokemon_set_page_snapshot_latest","price_observations":None})
    return rows,dict(dropped),{"condition_id":condition_id,"assumption_rows":raw_assumptions,"sets":len(set_ids),"prices":len(prices)}


def design(rows, *, treatment_keys=None, artist=False):
    treatments=treatment_keys or sorted({r["treatment"] for r in rows}); base=treatments[0]
    sets=sorted({r["set_id"] for r in rows}); species=sorted({r["species"] for r in rows if r.get("species")})
    mechanics=sorted({str(x).lower() for r in rows for x in r.get("subtypes",[]) if str(x).lower() in {"ex","v","vmax","vstar","gx"}})
    artists=sorted({str(r.get("artist")) for r in rows if r.get("artist")}) if artist else []
    columns=["intercept","log_odds"]+["t:"+x for x in treatments[1:]]+["set:"+x for x in sets[1:]]+["species:"+x for x in species[1:]]+["mechanic:"+x for x in mechanics]+["artist:"+x for x in artists[1:]]
    X=[]
    for r in rows:
        X.append([1,r["log_odds"]]+[int(r["treatment"]==x) for x in treatments[1:]]+
            [int(r["set_id"]==x) for x in sets[1:]]+[int(r.get("species")==x) for x in species[1:]]+
            [int(x in {str(v).lower() for v in r.get("subtypes",[])}) for x in mechanics]+[int(str(r.get("artist"))==x) for x in artists[1:]])
    return np.asarray(X,float),np.asarray([r["log_price"] for r in rows]),columns,base,treatments


def fit(rows, **kwargs):
    if len(rows)<3:return None
    X,y,columns,base,treatments=design(rows,**kwargs); beta=np.linalg.lstsq(X,y,rcond=None)[0]
    coefs={base:0.0}; coefs.update({name[2:]:float(beta[i]) for i,name in enumerate(columns) if name.startswith("t:")})
    return {"coefficients":coefs,"rank":int(np.linalg.matrix_rank(X)),"columns":len(columns),"n":len(rows)}


def bootstrap(rows, draws, seed):
    rng=np.random.default_rng(seed); by_set=defaultdict(list)
    for r in rows:by_set[r["set_id"]].append(r)
    set_ids=sorted(by_set); treatment_keys=sorted({r["treatment"] for r in rows}); samples={k:[] for k in treatment_keys}
    for _ in range(draws):
        sample=[]
        for i,sid in enumerate(rng.choice(set_ids,len(set_ids),replace=True)):
            sample.extend({**r,"set_id":f"{sid}__{i}"} for r in by_set[sid])
        model=fit(sample,treatment_keys=treatment_keys)
        if model:
            for key in treatment_keys:samples[key].append(model["coefficients"].get(key,0.0))
    return samples


def summarize(rows, samples):
    point=fit(rows); scores=pairwise_superiority_scores(samples); output=[]
    by_t=defaultdict(list)
    for r in rows:by_t[r["treatment"]].append(r)
    for key,group in sorted(by_t.items()):
        draws=np.asarray(samples.get(key,[])); beta=point["coefficients"].get(key,0.0)
        other_keys=[x for x in samples if x!=key]; score_draws=np.asarray([10*np.mean([draws[i]>samples[o][i] for o in other_keys]) for i in range(len(draws))]) if other_keys and len(draws) else np.array([])
        output.append({"treatment_key":key,"coefficient_log_price":beta,"adjusted_premium_pct":100*math.expm1(beta),
            "adjusted_premium_ci_low":100*math.expm1(float(np.quantile(draws,.025))) if len(draws) else None,
            "adjusted_premium_ci_high":100*math.expm1(float(np.quantile(draws,.975))) if len(draws) else None,
            "treatment_score_10":scores.get(key),"score_ci_low":float(np.quantile(score_draws,.025)) if len(score_draws) else None,
            "score_ci_high":float(np.quantile(score_draws,.975)) if len(score_draws) else None,
            "card_count":len({r["canonical_card_id"] for r in group}),"variant_count":len(group),
            "set_count":len({r["set_id"] for r in group}),"species_count":len({r["species"] for r in group if r.get("species")}),
            "median_odds":float(np.median([math.exp(r["log_odds"]) for r in group]))})
    return output


def audit_counts(client):
    result={}
    for table in ("pokemon_canonical_cards","pokemon_canonical_card_market_prices_latest","card_variants","sets","simulation_card_variant_pull_rates"):
        try:result[table]=client.table(table).select("id",count="exact").limit(1).execute().count
        except Exception:result[table]=None
    priced=paged(client.table("pokemon_canonical_card_market_prices_latest").select("set_id,canonical_card_id,card_variant_id"))
    cards=paged(client.table("pokemon_canonical_cards").select("id,rarity"))
    result.update({"priced_canonical_cards":len(priced),"priced_sets":len({r["set_id"] for r in priced}),
        "raw_rarity_labels":len({r.get("rarity") for r in cards}),"priced_variants":len({r.get("card_variant_id") for r in priced if r.get("card_variant_id")})})
    return result


def fingerprint(rows):
    payload=[(r["variant_id"],r["treatment"],round(r["price"],6),round(r["probability"],12),r["run_id"]) for r in sorted(rows,key=lambda x:x["variant_id"])]
    return hashlib.sha256(json.dumps(payload,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument("--study-as-of",type=date.fromisoformat,default=date.today())
    p.add_argument("--bootstrap-draws",type=int,default=1000);p.add_argument("--seed",type=int,default=SEED)
    p.add_argument("--commit",action="store_true");p.add_argument("--approve",action="store_true");p.add_argument("--dry-run",action="store_true")
    args=p.parse_args(); load_dotenv(Path("backend/.env"))
    from backend.db.clients.supabase_client import create_service_role_client
    client=create_service_role_client(); audit=audit_counts(client); round2=build_round2_audit(client,args.study_as_of)
    gate=round2["pre_model_gate"]
    decision="APPROVE_CARD_TREATMENT_PRESTIGE_V2" if gate["passed"] else "DO_NOT_APPROVE_CARD_TREATMENT_PRESTIGE_V2"
    report={"study":METHODOLOGY_VERSION,"study_round":"identification_taxonomy_exact_scarcity_round_2",
        "generated_at":datetime.now(timezone.utc).isoformat(),"study_as_of_date":args.study_as_of.isoformat(),
        "decision":decision,"acceptance_gates":GATES,"data_audit":audit,"round2":round2,
        "regression_results":None,"robustness_results":None,"bootstrap":{"seed":args.seed,"draws_requested":args.bootstrap_draws,"executed":False},
        "publication":{"committed":False,"approved":False,"study_run_id":None,"score_rows":0},
        "next_task":("review_local_v2_estimands" if round2["final_v2_status"]=="V2_LOCAL_IDENTIFICATION_EXISTS"
            else "additional_pull_rate_data_engineering" if "insufficient_set_diversity" in gate["failure_reasons"]
            else "abandonment_or_redefinition" if "insufficient_common_support" in gate["failure_reasons"]
            else "taxonomy_repair" if "excessive_unmapped_taxonomy_rate" in gate["failure_reasons"] else "model_execution")}
    out=Path("docs/research/card_treatment_prestige_v2_study.json");out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2),encoding="utf-8")
    if args.approve and decision!="APPROVE_CARD_TREATMENT_PRESTIGE_V2": raise SystemExit("Approval refused: preregistered gates did not pass")
    if args.commit: raise SystemExit("Migration must be applied before database publication; no partial run was written")
    print(json.dumps({"decision":decision,"pre_model_gate":gate,"supported_sets":round2["supported_sets"],
        "exact_variant_rows":round2["exact_variant_rows"],"matched_variant":round2["matched_variant"],
        "next_task":report["next_task"]},indent=2));return 0

if __name__=="__main__":raise SystemExit(main())
