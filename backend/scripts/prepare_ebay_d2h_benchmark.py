"""Deterministically partition the immutable eBay D2 review queue."""
from __future__ import annotations
import csv, hashlib, json, re
from collections import Counter, defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/'backend/artifacts/index_fair_value'
SOURCE=OUT/'ebay_manual_gold_labels.csv'; VERSION='ebay_gold_taxonomy_v1'; TOOL='ebay_gold_reviewer_v1'
LABELS=('EXACT_TARGET_MATCH','RELATED_BUT_WRONG_VARIANT','WRONG_SET','WRONG_CARD_NUMBER','WRONG_LANGUAGE','GRADED','LOT_OR_BUNDLE','SEALED_OR_ACCESSORY','CONDITION_INELIGIBLE','AMBIGUOUS','OTHER')
EXTRA=('partition','reviewer_1_label','reviewer_1_confidence','reviewer_1_note','reviewer_1_id','reviewer_1_at','reviewer_2_label','reviewer_2_confidence','reviewer_2_note','reviewer_2_id','reviewer_2_at','adjudicated_label','adjudicator_id','adjudicated_at','adjudication_note')
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def stable(value): return hashlib.sha256(value.encode()).hexdigest()
def risks(row):
    title=row['listing_title'].lower(); treatment=row['target_treatment'].lower()
    return {'promo':bool(re.search(r'\bpromo\b|\bsv?p\d+\b',title)),'variant_risk':any(x in title+' '+treatment for x in ('reverse','stamped','parallel','pokemon center','illustration','secret')),'set_omitted':row['target_set_name'].lower() not in title,'number_omitted':not re.search(rf'(?<!\d){re.escape(row["target_card_number"])}(?!\d)',title),'graded':bool(re.search(r'\b(psa|bgs|cgc|sgc)\b|\bgraded\b',title)),'non_english':bool(re.search(r'\b(japanese|korean|chinese|german|french|spanish|italian)\b',title)),'lot_bundle':bool(re.search(r'\b(lot|bundle|playset|collection)\b',title)),'sealed_accessory':bool(re.search(r'\b(etb|booster box|sleeves?|binder|case|proxy|sealed)\b',title))}
def main():
    with SOURCE.open(encoding='utf-8',newline='') as f: rows=list(csv.DictReader(f));fields=list(rows[0])
    assert len(rows)==1050 and all(not r['gold_label'] for r in rows)
    groups=defaultdict(list)
    for r in rows: groups[r['canonical_card_id']].append(r)
    assigned=[]
    for card_index,card_id in enumerate(sorted(groups)):
        ordered=sorted(groups[card_id],key=lambda r:stable('d2h-v1|'+r['benchmark_row_id']+'|'+r['listing_item_id']))
        dev_n=7 if card_index<30 else 6; val_n=3 if card_index<30 else 4
        for i,r in enumerate(ordered):
            x=dict(r);x['partition']='DEVELOPMENT' if i<dev_n else 'VALIDATION' if i<dev_n+val_n else 'FINAL_BLIND_TEST'
            for c in EXTRA[1:]:x[c]=''
            assigned.append(x)
    names={'DEVELOPMENT':'ebay_gold_development.csv','VALIDATION':'ebay_gold_validation.csv','FINAL_BLIND_TEST':'ebay_gold_final_blind.csv'}
    for part,name in names.items():
        subset=sorted((r for r in assigned if r['partition']==part),key=lambda r:r['benchmark_row_id'])
        with (OUT/name).open('w',encoding='utf-8',newline='') as f:w=csv.DictWriter(f,fieldnames=fields+list(EXTRA));w.writeheader();w.writerows(subset)
    split_material='\n'.join(f"{r['benchmark_row_id']}:{r['partition']}" for r in sorted(assigned,key=lambda x:x['benchmark_row_id']))
    counts={p:sum(r['partition']==p for r in assigned) for p in names}; strat={}
    for p in names:
        c=Counter();subset=[r for r in assigned if r['partition']==p]
        for r in subset:
            for k,v in risks(r).items():c[k]+=int(v)
        strat[p]={'rows':len(subset),'cards':len({r['canonical_card_id'] for r in subset}),**dict(c)}
    manifest={'version':'ebay_gold_benchmark_manifest_v1','source':'ebay_manual_gold_labels.csv','sourceQueueFingerprint':sha(SOURCE),'sourceRows':len(rows),'sourceCards':len(groups),'splitMethod':'per-card stable SHA-256 ordering; first 30 cards 7/3/5, remaining 40 cards 6/4/5','partitionSizes':counts,'splitFingerprint':hashlib.sha256(split_material.encode()).hexdigest(),'stratificationCounts':strat,'labelTaxonomyVersion':VERSION,'labels':LABELS,'confidence':['HIGH','MEDIUM','LOW'],'reviewToolVersion':TOOL,'sourceImmutable':True,'finalBlindAccess':'Denied to matcher-development loader until frozen matcher commit and fingerprint manifest is supplied.'}
    (OUT/'ebay_gold_benchmark_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8');print(json.dumps(manifest,indent=2))
if __name__=='__main__':main()
