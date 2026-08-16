"""Sensitivity audit for the two contextual chase membership parameters."""
import json
from pathlib import Path

from backend.db.services.contextual_set_desirability_service import build_contextual_desirability_bundle
from backend.desirability.weighted_rip import spearman


VARIANTS = ((0.005, 5), (0.01, 3), (0.01, 5), (0.01, 7), (0.02, 5))


def ordered(payloads):
    return sorted((x for x in payloads.values() if x.get("score") is not None), key=lambda x: (-x["score"], x["set_id"]))


def main():
    bundles = {(share, top): build_contextual_desirability_bundle(min_card_share=share, always_include_top_n=top)["payloads"] for share, top in VARIANTS}
    baseline = bundles[(0.01, 5)]
    base_rows = ordered(baseline)
    base_ids = [x["set_id"] for x in base_rows]
    report = []
    for (share, top), payloads in bundles.items():
        rows = ordered(payloads)
        by_id = {x["set_id"]: x for x in rows}
        common = [set_id for set_id in base_ids if set_id in by_id]
        cases = {}
        for name in ("Paldea Evolved", "Ascended Heroes", "Journey Together"):
            row = next(x for x in payloads.values() if x.get("set_name") == name)
            pika = next((x for x in row.get("modeled_pokemon", []) if x.get("name") == "Pikachu"), None)
            cases[name] = {"score": row.get("score"), "pikachuRole": (pika or {}).get("role")}
        report.append({"minCardShare": share, "alwaysIncludeTopN": top, "cohortSize": len(rows),
                       "spearmanVsBaseline": spearman([baseline[x]["score"] for x in common], [by_id[x]["score"] for x in common]),
                       "top5OverlapVsBaseline": len(set(base_ids[:5]) & {x["set_id"] for x in rows[:5]}),
                       "top10OverlapVsBaseline": len(set(base_ids[:10]) & {x["set_id"] for x in rows[:10]}),
                       "sanityCases": cases})
    path = Path("logs/contextual_roster_v4_sensitivity.json")
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(path)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
