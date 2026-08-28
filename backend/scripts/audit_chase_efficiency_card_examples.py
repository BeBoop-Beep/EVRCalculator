"""Real-data arithmetic audit for representative Chase Efficiency cards."""
from __future__ import annotations
import argparse, json
from backend.db.clients.supabase_client import create_service_role_client
from backend.db.services.chase_efficiency_service import load_candidate, validate_candidate
from backend.domain.pokemon.chase_efficiency import chase_efficiency


def run(client, market_date: str):
    candidate = load_candidate(client, market_date=market_date); rows = candidate["rows"]
    seen=set()
    def take(predicate):
        row=next(r for r in rows if r["card_variant_id"] not in seen and predicate(r));seen.add(row["card_variant_id"]);return row
    low=next(r for r in reversed(rows) if r["card_variant_id"] not in seen);seen.add(low["card_variant_id"])
    picks = [
        ("high_chase_efficiency", take(lambda r: True)),
        ("sir", take(lambda r: r.get("canonical_rarity") == "Special Illustration Rare")),
        ("ir", take(lambda r: r.get("canonical_rarity") == "Illustration Rare")),
        ("low_chase_efficiency", low),
        ("specialty_route_set", take(lambda r: all(x.get("product_family") != "booster_box" for x in r["verified_routes"]))),
        ("normal_booster_box_set", take(lambda r: any(x.get("product_family") == "booster_box" for x in r["verified_routes"]))),
    ]
    examples=[]
    for category,row in picks:
        key=row["card_variant_id"]
        reproduced=chase_efficiency(target_value=row["current_market_price"],pack_cost=row["best_verified_pack_equivalent_cost"],probability=row["probability"])
        threshold_checks={}
        for q in ("50","75","90","95"):
            actual=row["milestones"][q]["spend"]
            minimum=min(route["thresholds"][q]["spend"] for route in row["verified_routes"])
            threshold_checks[q]={"persistedCandidateSpend":actual,"minimumRouteSpend":minimum,"matches":actual==minimum}
        examples.append({"category":category,"cardVariantId":key,"cardName":row["card_name"],"rarity":row["canonical_rarity"],
            "setId":row["set_id"],"currentCardPrice":row["current_market_price"],"exactModeledProbability":row["probability"],
            "selectedRoutePrice":row["chosen_product_price"],"selectedRandomPackCount":row["chosen_random_pack_count"],
            "effectivePackCost":row["best_verified_pack_equivalent_cost"],"persistedCandidateChaseEfficiency":row["chase_efficiency"],
            "reproducedChaseEfficiency":reproduced,"ceMatches":reproduced==row["chase_efficiency"],
            "publishedCandidateGlobalRank":row["overall_rank"],"rankMatchesCandidateOrder":rows[row["overall_rank"]-1]["card_variant_id"]==key,
            "thresholds":threshold_checks})
    failures=validate_candidate(candidate)
    return {"marketDate":market_date,"candidateAudit":"PASS" if not failures else "FAIL","failures":failures,"examples":examples,
            "note":"Candidate authority only until Chase Efficiency migrations are deployed and atomically published."}


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument("--market-date",required=True);a=p.parse_args(argv)
    print(json.dumps(run(create_service_role_client(),a.market_date),indent=2));return 0
if __name__=="__main__":raise SystemExit(main())
