import json,statistics,time
from pathlib import Path
from backend.db.clients.supabase_client import create_service_role_client
O='get_pokemon_market_explorer_filtered_cohort'; N='get_pokemon_market_explorer_filtered_cohort_daily_candidate'
S={'cel':['be7c981b-c55e-4f60-a1b8-be922531452d'],'fos':['c86889c9-ea25-4caa-b63c-7aa0b9796da8'],'fus':['8cd0a0f0-d17c-4a5c-bc52-47e1723e0699'],'evo':['93212749-ce0e-498e-975e-7d947a3448ce'],'chi':['1c7aa5c4-c8c9-4ae8-a1eb-d613f7e4b890']}; T=S['fus']+S['evo']+S['chi']
def p(ids,**x): return {**{'p_set_ids':ids,'p_start_date':'2026-04-11','p_end_date':'2026-08-28','p_card_ids':None,'p_segment_ids':None,'p_pokemon_ids':None,'p_price_segment_ids':None,'p_release_age_cohort_ids':None,'p_top_n':None},**x}
def main():
 c=create_service_role_client(); q={**{k+'Full':p(v) for k,v in S.items()},'full':p(T),'top10':p(T,p_top_n=10),'rare':p(T,p_segment_ids=['rareHolo']),'rareTop10':p(T,p_segment_ids=['rareHolo'],p_top_n=10),'premium':p(T,p_price_segment_ids=['premium']),'premiumTop10':p(T,p_price_segment_ids=['premium'],p_top_n=10),'established':p(T,p_release_age_cohort_ids=['established']),'pokemon':p(T,p_pokemon_ids=[898]),'pokemonRare':p(T,p_pokemon_ids=[898],p_segment_ids=['rareUltra']),'obtainable':p(T,p_price_segment_ids=['obtainable']),'obtainableTop10':p(T,p_price_segment_ids=['obtainable'],p_top_n=10),'establishedPremium':p(T,p_release_age_cohort_ids=['established'],p_price_segment_ids=['premium']),'compound':p(T,p_segment_ids=['rareUltra'],p_price_segment_ids=['premium'])}
 exact={k:c.rpc(O,v).execute().data==c.rpc(N,v).execute().data for k,v in q.items()}; pc={k:q[k] for k in ['full','top10','rare','rareTop10','premium','premiumTop10','established','pokemonRare','compound']}; pc['current']=p(T,p_start_date='2026-08-28'); pc['currentTop25']=p(T,p_start_date='2026-08-28',p_top_n=25); perf={}
 for k,v in pc.items():
  s=[]
  for _ in range(5): t=time.perf_counter(); c.rpc(N,v).execute(); s.append((time.perf_counter()-t)*1000)
  perf[k]={'median':statistics.median(s),'p95':max(s),'min':min(s),'max':max(s)}
 r={'correctness':exact,'allExact':all(exact.values()),'performance':perf}; out=Path('artifacts/market_explorer_acceptance/20260831_effort1j_acceptance.json'); out.write_text(json.dumps(r,indent=2)); print(json.dumps(r,indent=2))
if __name__=='__main__': main()
