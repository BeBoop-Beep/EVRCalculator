"""Cluster Supporter titles and audit corrected C2.6 Trainer coverage."""
import json, sys
from collections import defaultdict
from pathlib import Path
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from backend.desirability.collector_identity import normalize_identity_text
from backend.desirability.rarity_buckets import HIT_POLICY_VERSION, PREMIUM_OR_MAJOR_BUCKETS, classify_rarity, is_hit_bucket
from backend.desirability.collector_source_quality import registry_gate
from backend.desirability.trainer_title_identity import CLASSIFIER_VERSION, classify_supporter_title

def paged(factory):
    rows=[];start=0
    while True:
        part=factory().range(start,start+999).execute().data;rows+=part
        if len(part)<1000:return rows
        start+=1000

def main():
    load_dotenv(ROOT/'backend/.env',override=False);from backend.db.clients.supabase_client import supabase
    entities=supabase.table('pokemon_collector_entity_reference').select('id,display_name,normalized_name').eq('entity_type','trainer').eq('active',True).execute().data
    known=[x['display_name'] for x in entities]
    cards=paged(lambda:supabase.table('pokemon_canonical_cards').select('id,name,subtypes,rarity,pokemon_tcg_api_card_id,source_payload').eq('supertype','Trainer'))
    links=paged(lambda:supabase.table('pokemon_card_collector_entity_links').select('pokemon_canonical_card_id').eq('link_role','subject').eq('active',True))
    linked={x['pokemon_canonical_card_id'] for x in links}; supporters=[x for x in cards if 'Supporter' in (x.get('subtypes') or [])]
    clusters=defaultdict(list)
    for card in supporters:clusters[normalize_identity_text(card['name'])].append(card)
    output=[]
    for key,group in sorted(clusters.items()):
        title=group[0]['name']; result=classify_supporter_title(title,known); resolved=all(x['id'] in linked for x in group)
        sets=[];eras=[]
        for x in group:
            set_data=(x.get('source_payload') or {}).get('set') or {}
            if set_data.get('id'):sets.append(set_data['id'])
            if set_data.get('series'):eras.append(set_data['series'])
        buckets=[classify_rarity(x.get('rarity')).bucket for x in group]
        output.append({'normalizedTitle':key,'title':title,'classification':result.classification,'subjects':list(result.subjects),'matchRule':result.rule,
          'cardCount':len(group),'premiumCardCount':sum(x in PREMIUM_OR_MAJOR_BUCKETS for x in buckets),'hitEligibleCardCount':sum(is_hit_bucket(x) for x in buckets),
          'sets':sorted(set(sets)),'eras':sorted(set(eras)),'explicitProperTrainerName':result.classification=='explicit_named_subject',
          'multiplePrintingsMayDepictDifferentCharacters':result.classification=='generic_card_with_variable_character','resolved':resolved})
    explicit=[x for x in output if x['classification']=='explicit_named_subject']; explicit_cards=sum(x['cardCount'] for x in explicit); explicit_resolved=sum(x['cardCount'] for x in explicit if x['resolved'])
    premium=sum(x['premiumCardCount'] for x in explicit); premium_resolved=sum(x['premiumCardCount'] for x in explicit if x['resolved'])
    hit=sum(x['hitEligibleCardCount'] for x in explicit);hit_resolved=sum(x['hitEligibleCardCount'] for x in explicit if x['resolved'])
    metrics={'namedCharacterCoverage':explicit_resolved/max(explicit_cards,1),'premiumNamedCoverage':premium_resolved/max(premium,1),'hitEligibleNamedCoverage':hit_resolved/max(hit,1)}
    counts={kind:sum(x['cardCount'] for x in output if x['classification']==kind) for kind in ('explicit_named_subject','generic_role_or_class','generic_card_with_variable_character','team_or_organization','ambiguous_title','requires_manual_review')}
    report={'classifierVersion':CLASSIFIER_VERSION,'hitPolicyVersion':HIT_POLICY_VERSION,'trainerEntities':len(entities),'allSupporterCards':len(supporters),'uniqueNormalizedSupporterTitles':len(output),
      'oldMetrics':{'namedCandidateCards':1033,'namedResolvedCards':202,'namedCoverage':202/1033,'premiumNamedCandidates':466,'premiumNamedResolved':92,'hitEligibleNamedCandidates':494,'hitEligibleNamedResolved':104},
      'correctedCounts':counts,'explicitNamedCards':explicit_cards,'resolvedExplicitNamedCards':explicit_resolved,'premiumExplicitNamedCards':premium,'premiumExplicitNamedResolved':premium_resolved,
      'hitEligibleExplicitNamedCards':hit,'hitEligibleExplicitNamedResolved':hit_resolved,'metrics':metrics,'qualityGate':registry_gate(metrics),
      'remainingManualReviewClusters':[x for x in output if x['classification'] in {'requires_manual_review','ambiguous_title'} or (x['classification']=='explicit_named_subject' and not x['resolved'])],
      'clusters':output}
    print(json.dumps(report,indent=2,ensure_ascii=False));return 0
if __name__=='__main__':raise SystemExit(main())
