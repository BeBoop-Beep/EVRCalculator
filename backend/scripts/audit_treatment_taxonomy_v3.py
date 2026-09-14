"""Read-only live census and frozen T2 cohort construction for Treatment taxonomy V3."""
from __future__ import annotations
import hashlib,json,statistics,sys
from collections import Counter,defaultdict
from datetime import datetime,timezone
from itertools import combinations
from pathlib import Path

from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from backend.desirability.treatment_taxonomy_v3 import ATTRIBUTE_DEFINITIONS,TAXONOMY_VERSION,as_json,resolve_treatment_v3,taxonomy_fingerprint

ART=ROOT/"backend/artifacts/treatment"; CFG=ROOT/"backend/config"; DOC=ROOT/"docs/research/treatment"
V7="pokemon_collector_appeal_v7_expanded_price_blind_v1"

def paged(factory):
    out=[];start=0;empty_retries=0
    while True:
        rows=factory().range(start,start+999).execute().data or [];out+=rows
        if not rows:
            empty_retries+=1
            if empty_retries>=3:return out
            continue
        empty_retries=0
        start+=len(rows)

def dump(path,payload):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(payload,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def run(client):
    current=client.table("pokemon_collector_appeal_current").select("model_run_id,model_version").eq("scope","pokemon").single().execute().data
    if current["model_version"]!=V7: raise RuntimeError("production Collector is not frozen V7")
    scores=paged(lambda:client.table("pokemon_card_collector_appeal_scores").select("pokemon_canonical_card_id,component_inputs_json").eq("model_run_id",current["model_run_id"]).order("pokemon_canonical_card_id"))
    expected_scores=client.table("pokemon_card_collector_appeal_scores").select("pokemon_canonical_card_id",count="exact").eq("model_run_id",current["model_run_id"]).limit(0).execute().count
    if len(scores)!=expected_scores:raise RuntimeError(f"incomplete Collector cohort read: {len(scores)} != {expected_scores}")
    eligible={str(x["pokemon_canonical_card_id"]) for x in scores}
    score_by_card={str(x["pokemon_canonical_card_id"]):x for x in scores}
    cards=paged(lambda:client.table("pokemon_canonical_cards").select("id,set_id,pokemon_tcg_api_card_id,name,number,rarity,artist,supertype,subtypes").order("id"))
    sets=paged(lambda:client.table("sets").select("id,name,era_id,release_date").order("id"));eras=paged(lambda:client.table("eras").select("id,name").order("id"))
    era_by={str(x["id"]):x["name"] for x in eras};set_by={str(x["id"]):x for x in sets}
    legacy=paged(lambda:client.table("cards").select("id,set_id,pokemon_tcg_api_id,name,card_number,rarity").order("id"))
    variants=paged(lambda:client.table("card_variants").select("id,card_id,printing_type,special_type,edition").order("id"))
    old_by_api={str(x.get("pokemon_tcg_api_id")):x for x in legacy if x.get("pokemon_tcg_api_id")};vars_by=defaultdict(list)
    for x in variants:vars_by[str(x["card_id"])].append(x)
    variant_by={str(x["id"]):x for x in variants}
    rows=[];unresolved=[];before=Counter();after=Counter();by_era=defaultdict(Counter);variant_total=variant_mapped=0
    for card in cards:
        if str(card["id"]) not in eligible:continue
        setrow=set_by[str(card["set_id"])];era=era_by[str(setrow["era_id"])]
        prior=score_by_card.get(str(card["id"]),{})
        prior_status=((prior.get("component_inputs_json") or {}).get("treatmentDiagnostic") or {}).get("status")
        before[prior_status or "unknown"]+=1
        old=old_by_api.get(str(card.get("pokemon_tcg_api_card_id"))); card_variants=vars_by.get(str((old or {}).get("id")),[])
        identities=[]
        for variant in card_variants or [None]:
            v=variant or {}; identity=resolve_treatment_v3(rarity=card.get("rarity"),era=era,printing_type=v.get("printing_type"),special_type=v.get("special_type"),edition=v.get("edition"))
            identities.append(identity)
            if variant: variant_total+=1;variant_mapped+=identity.treatment_key is not None
        identity=resolve_treatment_v3(rarity=card.get("rarity"),era=era)
        after[identity.resolution]+=1;by_era[era]["total"]+=1;by_era[era]["mapped" if identity.treatment_key else "unmapped"]+=1
        row={"canonical_card_id":str(card["id"]),"variant_ids":[str(x["id"]) for x in card_variants],"set_id":str(card["set_id"]),"set":setrow["name"],"era":era,"card_name":card["name"],"card_number":card.get("number"),"rarity":card.get("rarity"),"printing_types":sorted({str(x.get("printing_type")) for x in card_variants}),"special_types":sorted({str(x.get("special_type")) for x in card_variants}),"editions":sorted({str(x.get("edition")) for x in card_variants}),**as_json(identity)}
        rows.append(row)
        if not identity.treatment_key:unresolved.append(row)
    era_map=[]
    for era in sorted(by_era):
        labels=defaultdict(lambda:{"count":0,"attributes":set(),"treatmentKeys":set()})
        for x in rows:
            if x["era"]==era:
                z=labels[str(x["rarity"] or "<NULL>")];z["count"]+=1;z["attributes"].update(x["semantic_attributes"]);z["treatmentKeys"].add(x["treatment_key"])
        era_map.append({"era":era,**by_era[era],"labels":[{"label":k,"count":v["count"],"treatmentKeys":sorted(x for x in v["treatmentKeys"] if x),"semanticAttributes":sorted(v["attributes"]),"exactPullScarcity":"partial"} for k,v in sorted(labels.items())]})
    rates=paged(lambda:client.table("simulation_card_variant_pull_rates").select("id,card_variant_id,calculation_run_id,modeled_probability,effective_pull_rate,created_at").order("id"))
    latest={}
    for x in rates:
        vid=str(x["card_variant_id"])
        if vid not in latest or str(x["created_at"])>str(latest[vid]["created_at"]):latest[vid]=x
    candidate_rows=[]
    for x in rows:
        for vid in x["variant_ids"]:
            v=variant_by.get(vid,{});rate=latest.get(vid);prob=(rate or {}).get("modeled_probability") or (rate or {}).get("effective_pull_rate")
            ident=resolve_treatment_v3(rarity=x["rarity"],era=x["era"],printing_type=v.get("printing_type"),special_type=v.get("special_type"),edition=v.get("edition"))
            if ident.treatment_key and prob:
                candidate_rows.append({"canonical_card_id":x["canonical_card_id"],"variant_id":vid,"set_id":x["set_id"],"set":x["set"],"era":x["era"],"subject":x["card_name"],"artist":next((c.get("artist") for c in cards if str(c["id"])==x["canonical_card_id"]),None),"rarity":x["rarity"],"treatment":ident.treatment_key,"semantic_attributes":list(ident.semantic_attributes),"probability":prob,"scarcity_run_id":str(rate["calculation_run_id"])})
    candidates=[];groups=defaultdict(list)
    for x in candidate_rows:groups[(x["era"],x["set_id"],x["subject"])].append(x)
    for group in groups.values():
        for a,b in combinations(sorted(group,key=lambda z:z["variant_id"]),2):
            if a["semantic_attributes"]==b["semantic_attributes"]:continue
            ratio=max(a["probability"],b["probability"])/min(a["probability"],b["probability"])
            candidates.append({"cardIds":[a["canonical_card_id"],b["canonical_card_id"]],"variantIds":[a["variant_id"],b["variant_id"]],"set":a["set"],"era":a["era"],"subject":a["subject"],"artist":[a["artist"],b["artist"]],"treatmentA":a["treatment"],"treatmentB":b["treatment"],"semanticAttributesA":a["semantic_attributes"],"semanticAttributesB":b["semantic_attributes"],"probabilityA":a["probability"],"probabilityB":b["probability"],"scarcityRatio":ratio,"artworkIdentity":"same_canonical" if a["canonical_card_id"]==b["canonical_card_id"] else "same_subject","mechanicFormIdentity":"not_asserted","priceAvailable":"not_queried","identificationTier":"A" if a["canonical_card_id"]==b["canonical_card_id"] and ratio<=2 else "B"})
    edges=defaultdict(lambda:{"sameCard":0,"sameSubject":0,"eras":set()})
    for x in candidates:
        pair=tuple(sorted((x["treatmentA"],x["treatmentB"])));edges[pair]["sameCard"]+=x["identificationTier"]=="A";edges[pair]["sameSubject"]+=1;edges[pair]["eras"].add(x["era"])
    graph=[]
    for pair,v in sorted(edges.items()):
        status="DIRECTLY_IDENTIFIABLE" if v["sameCard"] else "LOCALLY_IDENTIFIABLE"
        graph.append({"treatmentA":pair[0],"treatmentB":pair[1],"status":status,"sameCardContrasts":v["sameCard"],"sameSubjectContrasts":v["sameSubject"],"eras":sorted(v["eras"])})
    treatment_keys=sorted({x["treatment_key"] for x in rows if x["treatment_key"]});observed=set(edges);adj=defaultdict(set)
    for a,b in observed:adj[a].add(b);adj[b].add(a)
    def connected(a,b):
        seen={a};stack=[a]
        while stack:
            node=stack.pop()
            if node==b:return True
            for nxt in adj[node]-seen:seen.add(nxt);stack.append(nxt)
        return False
    for a,b in combinations(treatment_keys,2):
        if (a,b) not in observed:
            graph.append({"treatmentA":a,"treatmentB":b,"status":"CONNECTED_ONLY_THROUGH_INTERMEDIATES" if connected(a,b) else "UNSUPPORTED","sameCardContrasts":0,"sameSubjectContrasts":0,"eras":[]})
    graph.sort(key=lambda x:(x["treatmentA"],x["treatmentB"]))
    cohorts={name:sorted([x for x in candidates if pred(x)],key=lambda z:(z["era"],z["set"],z["variantIds"])) for name,pred in {
        "best_same_card":lambda x:x["identificationTier"]=="A","best_same_subject":lambda x:x["identificationTier"]=="B",
        "best_scarcity_matched":lambda x:x["scarcityRatio"]<=1.25,"era_local":lambda x:True}.items()}
    cohort_manifest={k:{"count":len(v),"fingerprint":taxonomy_fingerprint(v)} for k,v in cohorts.items()}
    cohort_members={k:[{"variantIds":x["variantIds"],"identificationTier":x["identificationTier"]} for x in v] for k,v in cohorts.items()}
    scarcity_groups=defaultdict(list)
    for x in candidate_rows:scarcity_groups[(x["era"],x["treatment"])].append(x)
    scarcity_diagnostics=[]
    for (era,treatment),group in sorted(scarcity_groups.items()):
        ordered=sorted(group,key=lambda x:(x["probability"],x["variant_id"]));values=[x["probability"] for x in ordered]
        scarcity_diagnostics.append({"era":era,"treatment":treatment,"variantCount":len(group),"rarityDistribution":dict(Counter(str(x["rarity"]) for x in group)),"probability":{"min":min(values),"median":statistics.median(values),"max":max(values)},"withinTreatmentProbabilityRatio":max(values)/min(values),"scarcityExampleVariantIds":[ordered[0]["variant_id"],ordered[-1]["variant_id"]]})
    taxonomy={"taxonomyVersion":TAXONOMY_VERSION,"priceUsed":False,"attributes":ATTRIBUTE_DEFINITIONS,"definitions":{"era_local_label":"Publisher/API rarity designation interpreted only inside its era.","semantic_attributes":"Observable presentation properties; never an ordinal global ladder."},"manualOverrides":[],"detection":{"rarity":"deterministic normalized source metadata","printing_type":"deterministic variant metadata","special_type":"deterministic variant metadata","edition":"deterministic variant metadata","unassignedAttributes":"require future explicit metadata or versioned manual override"},"fingerprint":taxonomy_fingerprint({"rows":[(x["era"],x["rarity"],x["treatment_key"],x["semantic_attributes"]) for x in rows]})}
    def breakdown(field):
        groups=defaultdict(lambda:{"total":0,"mapped":0,"unmapped":0})
        for x in rows:
            values=x[field] if isinstance(x[field],list) else [x[field]]
            for value in values or [None]:groups[str(value or "<NULL>")]["total"]+=1;groups[str(value or "<NULL>")]["mapped" if x["treatment_key"] else "unmapped"]+=1
        return [{"value":k,**v} for k,v in sorted(groups.items())]
    coverage={"generatedAt":datetime.now(timezone.utc).isoformat(),"collectorModelRunId":current["model_run_id"],"collectorVersion":V7,"eligibleCanonicalCards":len(rows),"mappedBefore":before["mapped"],"unmappedBefore":before["unmapped_treatment"],"mappedAfter":sum(x["treatment_key"] is not None for x in rows),"unmappedAfter":len(unresolved),"ambiguous":after["GENUINELY_AMBIGUOUS"],"multiTreatment":sum(len(x["semantic_attributes"])>1 for x in rows),"unknownLegacy":after["UNSUPPORTED_LEGACY_STRUCTURE"],"dataQualityError":0,"structurallyUnsupported":after["UNSUPPORTED_LEGACY_STRUCTURE"],"legacyUnsupported":after["UNSUPPORTED_LEGACY_STRUCTURE"],"missingSourceMetadata":after["MISSING_SOURCE_METADATA"],"eligibleAssociatedVariants":variant_total,"mappedAssociatedVariants":variant_mapped,"liveTableCounts":{"pokemon_canonical_cards":len(cards),"cards":len(legacy),"card_variants":len(variants),"sets":len(sets),"eras":len(eras),"simulation_card_variant_pull_rates":len(rates)},"pokemonCardTreatmentScoresLive":False,"mappingAuthority":"read_only_code_and_config","scarcityDiagnostics":scarcity_diagnostics,"sameRarityDifferentTreatmentExamples":[x for x in candidates if x["treatmentA"]!=x["treatmentB"]][:25],"byEra":era_map,"bySet":breakdown("set"),"byRarity":breakdown("rarity"),"byPrintingType":breakdown("printing_types"),"bySpecialType":breakdown("special_types"),"byEdition":breakdown("editions")}
    dump(CFG/"treatment_taxonomy_v3.json",taxonomy);dump(CFG/"era_treatment_semantic_map_v1.json",era_map)
    dump(ART/"treatment_coverage_current.json",coverage);dump(ART/"treatment_unresolved_manifest.json",{"count":len(unresolved),"rows":unresolved})
    dump(ART/"treatment_pairwise_comparability.json",{"warning":"Graph connectivity does not authorize transitive preference inference.","edges":graph})
    dump(ART/"treatment_matched_contrast_candidates.json",{"priceUsedForEligibility":False,"count":len(candidates),"rows":candidates})
    dump(ART/"treatment_t2_research_cohorts.json",{"taxonomyVersion":TAXONOMY_VERSION,"collectorVersion":V7,"priceDerivedInclusion":False,"scarcityRunIds":sorted({x["scarcity_run_id"] for x in candidate_rows}),"cohortManifest":cohort_manifest,"cohortMembers":cohort_members,"candidateDetailArtifact":"treatment_matched_contrast_candidates.json","unsupportedComparisons":[x for x in graph if x["status"]=="UNSUPPORTED"]})
    summary={"status":"TREATMENT_TAXONOMY_V3_READY" if len(unresolved)==coverage["legacyUnsupported"]+coverage["missingSourceMetadata"] else "TREATMENT_TAXONOMY_V3_BLOCKED","coverage":coverage,"taxonomyFingerprint":taxonomy["fingerprint"],"cohortManifest":cohort_manifest,"pairCounts":Counter(x["identificationTier"] for x in candidates),"productionMutations":0}
    dump(ART/"treatment_taxonomy_v3_audit_summary.json",summary);return summary

def main():
    load_dotenv(ROOT/"backend/.env",override=False)
    from backend.db.clients.supabase_client import create_service_role_client
    print(json.dumps(run(create_service_role_client()),indent=2,default=dict));return 0
if __name__=="__main__":raise SystemExit(main())
