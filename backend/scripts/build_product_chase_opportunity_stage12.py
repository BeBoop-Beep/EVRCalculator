"""Stage XII build - Product Chase Opportunity contract on real sets. READ-ONLY.

No sealed-product price is read anywhere.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from backend.research.product_chase_opportunity_stage12 import (
    at_least_once,
    chase_significance,
    expected_significance,
    opportunity,
    per_pack_opportunity,
)

OUT = Path("docs/research/product_chase_opportunity_stage12.json")

#: Random pack counts spanning the real supported families (Phase 9).
PACK_COUNTS = (1, 3, 6, 9, 11, 18, 36)

FAMILY_PACKS = {"loose_booster_pack": 1, "sleeved_booster_pack": 1,
                "booster_bundle": 6, "elite_trainer_box": 9,
                "pokemon_center_elite_trainer_box": 11, "half_booster_box": 18,
                "booster_box": 36, "enhanced_booster_box": 36}


def _rows(r):
    return getattr(r, "data", r) or []


def spearman(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    ra, rb = np.empty(len(a)), np.empty(len(b))
    ra[np.argsort(a)] = np.arange(len(a))
    rb[np.argsort(b)] = np.arange(len(b))
    return float(np.corrcoef(ra, rb)[0, 1])


def fetch_set(client, name):
    s = _rows(client.table("sets").select("id").eq("name", name)
              .eq("is_subset", False).limit(1).execute())
    if not s:
        return None
    sid = s[0]["id"]
    lr = _rows(client.table("simulation_card_variant_pull_rates")
               .select("calculation_run_id,created_at").eq("set_id", sid)
               .order("created_at", desc=True).limit(1).execute())
    if not lr:
        return None
    run = lr[0]["calculation_run_id"]
    vals, ps, start = [], [], 0
    while True:
        page = _rows(client.table("simulation_card_variant_pull_rates")
                     .select("price_used,pull_count,modeled_probability")
                     .eq("calculation_run_id", run).eq("set_id", sid)
                     .range(start, start + 999).execute())
        for r in page:
            v, pc, mp = r.get("price_used"), r.get("pull_count"), r.get("modeled_probability")
            if not v or float(v) <= 0 or not pc or int(pc) <= 0:
                continue
            vals.append(float(v))
            ps.append(float(mp) if mp else 0.0)
        if len(page) < 1000:
            break
        start += 1000
    return {"setId": sid, "values": vals, "p": ps}


def main() -> int:
    from backend.db.clients.supabase_client import create_service_role_client
    client = create_service_role_client()
    rng = np.random.default_rng(31)

    names = [r["name"] for r in _rows(
        client.table("sets").select("name").eq("supports_opening_simulation", True)
        .eq("is_subset", False).execute())]
    out = []

    print("%-24s %5s %7s %8s | %s" % ("set", "n", "N_HC", "O/pack", "  ".join(
        "n=%d" % n for n in PACK_COUNTS)))
    print("-" * 108)

    for name in sorted(names):
        d = fetch_set(client, name)
        if not d or len(d["values"]) < 30:
            continue
        v = np.asarray(d["values"]); p = np.asarray(d["p"])
        hc = chase_significance(v)
        n_hc = 1.0 / float((hc ** 2).sum())
        opp = {n: opportunity(hc, at_least_once(p, n)) for n in PACK_COUNTS}
        exp = {n: expected_significance(hc, p, n) for n in PACK_COUNTS}
        o_pack = per_pack_opportunity(hc, p)

        order = np.argsort(-hc)
        a36 = at_least_once(p, 36)
        share_top1 = float(hc[order[0]] * a36[order[0]] / opp[36]) if opp[36] > 0 else 0.0
        share_top3 = float((hc[order[:3]] * a36[order[:3]]).sum() / opp[36]) if opp[36] > 0 else 0.0

        # Phase 12 - redundancy against EV-like quantities (per pack)
        ev_pack = float((v * p).sum())
        sq_pack = float(((v ** 2) * p).sum())

        print("%-24s %5d %7.2f %8.5f | %s" % (
            name, len(v), n_hc, o_pack,
            "  ".join("%.4f" % opp[n] for n in PACK_COUNTS)))

        entry = {"set": name, "n": len(v), "nHC": round(n_hc, 4),
                 "perPackOpportunity": round(o_pack, 8),
                 "opportunityByPacks": {str(n): round(opp[n], 6) for n in PACK_COUNTS},
                 "expectedSignificanceByPacks": {str(n): round(exp[n], 6) for n in PACK_COUNTS},
                 "marginalGain": {str(n): round(opp[n] - opp[m], 6)
                                  for m, n in zip(PACK_COUNTS, PACK_COUNTS[1:])},
                 "opportunityShareTop1_36": round(share_top1, 4),
                 "opportunityShareTop3_36": round(share_top3, 4),
                 "hcTop1": round(float(hc[order[0]]), 5),
                 "evPerPack": round(ev_pack, 4),
                 "squaredValueWeightedPerPack": round(sq_pack, 4),
                 "familyOpportunity": {f: round(opportunity(hc, at_least_once(p, k)), 6)
                                       for f, k in FAMILY_PACKS.items()}}

        # Phase 15 - price shocks (uniform must be exact; independent must be stable)
        base_hc = hc
        entry["uniformScaleExact"] = all(
            np.allclose(base_hc, chase_significance(v * m), rtol=0, atol=1e-12)
            and abs(opportunity(chase_significance(v * m), at_least_once(p, 36))
                    - opp[36]) < 1e-12
            for m in (0.5, 2.0, 10.0, 100.0))
        pn = {}
        for pct in (0.02, 0.05, 0.10):
            os_ = [opportunity(chase_significance(v * (1 + rng.uniform(-pct, pct, v.size))),
                               at_least_once(p, 36)) for _ in range(40)]
            pn["+/-%d%%" % int(pct * 100)] = {
                "meanO": round(float(np.mean(os_)), 6),
                "relSd": round(float(np.std(os_) / max(np.mean(os_), 1e-12)), 5)}
        entry["priceShock"] = pn

        # Phase 16 - pull-rate shocks, must be monotone-safe
        ps_ = {}
        for pct in (0.02, 0.05, 0.10):
            up = opportunity(hc, at_least_once(np.clip(p * (1 + pct), 0, 1), 36))
            dn = opportunity(hc, at_least_once(np.clip(p * (1 - pct), 0, 1), 36))
            ps_["+/-%d%%" % int(pct * 100)] = {
                "up": round(up, 6), "down": round(dn, 6),
                "monotone": bool(dn <= opp[36] <= up)}
        entry["pullShock"] = ps_
        out.append(entry)

    # Phase 12 - cross-set redundancy
    if len(out) >= 5:
        o36 = [e["opportunityByPacks"]["36"] for e in out]
        red = {
            "spearman_O36_vs_evPerPack": round(spearman(o36, [e["evPerPack"] for e in out]), 4),
            "spearman_O36_vs_sqValueWeighted": round(
                spearman(o36, [e["squaredValueWeightedPerPack"] for e in out]), 4),
            "spearman_O36_vs_nHC": round(spearman(o36, [e["nHC"] for e in out]), 4),
            "spearman_O36_vs_hcTop1": round(spearman(o36, [e["hcTop1"] for e in out]), 4),
            "spearman_Opack_vs_evPerPack": round(
                spearman([e["perPackOpportunity"] for e in out],
                         [e["evPerPack"] for e in out]), 4),
        }
    else:
        red = {}

    payload = {
        "stage": "stage12-product-chase-opportunity-v1",
        "candidate": "HC_WEIGHTED_AT_LEAST_ONCE_COVERAGE (research only, no version minted)",
        "formula": "O_p = sum_i HC_i * P(N_ip >= 1); HC_i = V_i^2 / sum_j V_j^2",
        "probabilityAuthority": (
            "simulation_card_variant_pull_rates.modeled_probability = per-pack "
            "P(N>=1) = pack_presence_count / simulation_count (1e6 sims). "
            "effective_pull_rate is 1-in-N ODDS, not a probability."),
        "iidNote": ("A_ip = 1-(1-p_i)^n inherits the simulator's own "
                    "pack_independence_assumption; it is not independently validated. "
                    "The SUM needs no cross-card independence (linearity of expectation)."),
        "productPriceIndependence": "no sealed-product price is read anywhere",
        "redundancy": red,
        "sets": out,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print("\nwrote %s (%d sets)" % (OUT, len(out)))
    print("uniform-scale exact: %d/%d" % (
        sum(1 for e in out if e["uniformScaleExact"]), len(out)))
    print("redundancy:", json.dumps(red, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
