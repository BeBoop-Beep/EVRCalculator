"""Create Trainer entities deterministically identified by explicit Supporter titles."""
import argparse, json, sys
from pathlib import Path
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from backend.desirability.collector_identity import normalize_identity_text
from backend.desirability.trainer_title_identity import CLASSIFIER_VERSION, classify_supporter_title
from backend.scripts.sync_pokemon_collector_identities import CollectorIdentityRepository

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--commit',action='store_true');args=p.parse_args()
    load_dotenv(ROOT/'backend/.env',override=False); repo=CollectorIdentityRepository(); cards=repo.list_canonical_cards(); entities=repo.list_entities()
    known=[x['display_name'] for x in entities if x.get('entity_type')=='trainer']; desired={}
    for card in cards:
        if card.get('supertype')!='Trainer' or 'Supporter' not in (card.get('subtypes') or []): continue
        result=classify_supporter_title(card.get('name'),known)
        if result.classification!='explicit_named_subject': continue
        for subject in result.subjects:
            normalized=normalize_identity_text(subject); key='trainer:'+normalized
            desired.setdefault(key,{'entity_type':'trainer','canonical_key':key,'display_name':subject,'normalized_name':normalized,'active':True,
                'identity_metadata_json':{'registryVersion':CLASSIFIER_VERSION,'authoritativeSource':'pokemon_canonical_cards Supporter title / https://www.pokemon.com/us/pokemon-tcg/pokemon-cards/',
                'sourceIdentityName':subject,'matchMethod':result.rule,'confidence':result.confidence,'manualOverride':False}})
    existing={x.get('canonical_key') for x in entities}; inserts=[v for k,v in sorted(desired.items()) if k not in existing]
    if args.commit and inserts: repo.upsert_entities(inserts)
    print(json.dumps({'status':'committed' if args.commit else 'dry_run','classifierVersion':CLASSIFIER_VERSION,'explicitEntities':len(desired),'inserts':len(inserts),'entityNames':[x['display_name'] for x in inserts]},indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
