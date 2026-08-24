"""Capture before/after identity classifications for contextual mapping repairs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.db.clients.supabase_client import service_read_client
from backend.db.services.contextual_set_desirability_service import (
    _card_evidence, build_contextual_desirability_bundle,
)

TARGETS = ("Pitch Black", "Chaos Rising")


def _sets():
    rows = service_read_client.table("sets").select("id,name").in_("name", list(TARGETS)).execute().data or []
    return {str(row["id"]): row["name"] for row in rows}


def _runs(set_ids):
    rows = (service_read_client.table("explore_rip_statistics_latest")
            .select("set_id,calculation_run_id,run_at").in_("set_id", list(set_ids))
            .execute()).data or []
    return {str(row["set_id"]): row for row in rows}


def _classification(card):
    if card.get("mapping_status") == "intentional_non_pokemon":
        return "intentional_non_pokemon"
    if card.get("mapping_status") != "mapped_pokemon":
        return "unresolved"
    return "mapped_eligible_pokemon" if card.get("is_hit_eligible") is not False else "resolved_ineligible_pokemon"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("before", "after"), required=True)
    args = parser.parse_args()
    sets = _sets(); runs = _runs(sets)
    evidence = _card_evidence([row["calculation_run_id"] for row in runs.values()])
    bundle = build_contextual_desirability_bundle(max_unresolved_ev_share=1.0)["payloads"]
    current = {}
    for set_id, name in sets.items():
        run = runs[set_id]; cards = evidence.get(str(run["calculation_run_id"]), [])
        total = sum(float(card.get("ev_contribution") or 0) for card in cards)
        details = []
        for card in sorted(cards, key=lambda row: float(row.get("ev_contribution") or 0), reverse=True):
            ev = float(card.get("ev_contribution") or 0)
            classification = _classification(card)
            if classification == "unresolved" or args.phase == "after":
                details.append({"cardId": card.get("card_id"), "cardName": card.get("card_name"),
                                "evContribution": ev, "evShare": ev / total if total else None,
                                "classification": classification,
                                "pokemonReferenceId": card.get("pokemon_reference_id"),
                                "rarity": card.get("rarity") or card.get("rarity_bucket")})
        row = bundle[set_id]
        current[name] = {"setId": set_id, "calculationRunId": run["calculation_run_id"],
                         "diagnostics": row.get("chase_evidence"),
                         "unresolvedCards": details if args.phase == "before" else None,
                         "allFinalCards": details if args.phase == "after" else None}
    output = {"phase": args.phase, "sets": current}
    if args.phase == "after":
        before_path = Path("logs/contextual_mapping_repair_before.json")
        before = json.loads(before_path.read_text(encoding="utf-8")) if before_path.exists() else {"sets": {}}
        for name, row in current.items():
            final_by_name = {item["cardName"]: item for item in row["allFinalCards"]}
            row["previouslyUnresolvedFinalClassifications"] = [
                {**item, "finalClassification": (final_by_name.get(item["cardName"]) or {}).get("classification"),
                 "finalPokemonReferenceId": (final_by_name.get(item["cardName"]) or {}).get("pokemonReferenceId")}
                for item in (before.get("sets", {}).get(name, {}).get("unresolvedCards") or [])
            ]
            row.pop("allFinalCards", None)
    path = Path(f"logs/contextual_mapping_repair_{args.phase}.json")
    path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(path)
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
