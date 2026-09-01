"""Stage XIII - Chase Opportunity comparison frame. READ-ONLY.

Decides the ROLE of Chase Opportunity. No transform, no coefficient, no version.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from backend.calculations.evr.financial_rip_v3 import build_financial_rip_v3
from backend.calculations.evr.financial_rip_v4 import project_financial_rip_v4_from_v3_payload
from backend.research.product_chase_opportunity_stage12 import (
    at_least_once,
    chase_significance,
    opportunity,
    per_pack_opportunity,
)

OUT = Path("docs/research/chase_frame_stage13.json")
PACKS = (1, 3, 6, 9, 11, 18, 36)
SIMS = 60000


def _rows(r):
    return getattr(r, "data", r) or []


def fetch(client, name):
    s = _rows(client.table("sets").select("id").eq("name", name)
              .eq("is_subset", False).limit(1).execute())
    if not s:
        return None
    sid = s[0]["id"]
    lr = _rows(client.table("simulation_card_variant_pull_rates")
               .select("calculation_run_id").eq("set_id", sid)
               .order("created_at", desc=True).limit(1).execute())
    if not lr:
        return None
    run = lr[0]["calculation_run_id"]
    v, p, start = [], [], 0
    while True:
        page = _rows(client.table("simulation_card_variant_pull_rates")
                     .select("price_used,pull_count,modeled_probability")
                     .eq("calculation_run_id", run).eq("set_id", sid)
                     .range(start, start + 999).execute())
        for r in page:
            if not r.get("price_used") or float(r["price_used"]) <= 0:
                continue
            if not r.get("pull_count") or int(r["pull_count"]) <= 0:
                continue
            v.append(float(r["price_used"]))
            p.append(float(r.get("modeled_probability") or 0.0))
        if len(page) < 1000:
            break
        start += 1000
    return {"setId": sid, "values": np.asarray(v), "p": np.asarray(p)}


def simulate_pack_values(v, p, rng, sims):
    """Independent-Bernoulli pack value proxy from the authoritative marginals.

    This is a PROXY, not the production simulator: it reproduces each card's
    per-pack marginal exactly but assumes cross-card independence, which the real
    pack does not have. Used only to measure how Financial RIP responds to pack
    COUNT under proportional pricing - a comparison in which the same proxy is
    used at every n, so the assumption cancels.
    """
    hits = rng.random((sims, v.size)) < p
    return hits @ v


def main() -> int:
    from backend.db.clients.supabase_client import create_service_role_client
    client = create_service_role_client()
    rng = np.random.default_rng(1301)
    results = []

    SETS = ["Phantasmal Flames", "Paldean Fates", "Ascended Heroes",
            "Paradox Rift", "Shrouded Fable", "Prismatic Evolutions"]

    print("PHASE 3/4 - FINANCIAL RIP V4 vs PACK COUNT AT PROPORTIONAL PRICE")
    print("(pack cost fixed at EV/0.55; product cost = n x pack cost)\n")
    print("%-22s %6s | %8s %8s %8s %8s | %9s" % (
        "set", "n", "FinV4", "P(recov)", "median", "p95", "O_product"))
    print("-" * 88)

    for name in SETS:
        d = fetch(client, name)
        if d is None or d["values"].size < 30:
            continue
        v, p = d["values"], d["p"]
        hc = chase_significance(v)
        o_pack = per_pack_opportunity(hc, p)
        pack_vals = simulate_pack_values(v, p, rng, SIMS)
        ev_pack = float(pack_vals.mean())
        pack_cost = ev_pack / 0.55          # fixed value-to-cost ratio for every n

        entry = {"set": name, "n": int(v.size), "perPackOpportunity": round(o_pack, 8),
                 "evPerPack": round(ev_pack, 4), "packCost": round(pack_cost, 4),
                 "byPacks": {}}

        for n in PACKS:
            # n-fold convolution: sum of n independent pack draws
            idx = rng.integers(0, SIMS, (SIMS, n))
            prod_vals = pack_vals[idx].sum(axis=1)
            fin3 = build_financial_rip_v3(prod_vals, pack_cost * n,
                                          min_simulation_count=1000)
            fin4 = project_financial_rip_v4_from_v3_payload(fin3)
            o = opportunity(hc, at_least_once(p, n))
            recov = float((prod_vals >= pack_cost * n).mean())
            entry["byPacks"][str(n)] = {
                "financialV4": fin4.get("score"),
                "chanceToRecover": round(recov, 5),
                "medianValue": round(float(np.median(prod_vals)), 2),
                "p95": round(float(np.percentile(prod_vals, 95)), 2),
                "opportunity": round(o, 6),
                "linearOpportunity": round(n * o_pack, 6),
                "saturationRatio": round(o / (n * o_pack), 6) if o_pack > 0 else None,
            }
            print("%-22s %6d | %8s %8.4f %8.2f %8.2f | %9.5f" % (
                name, n, fin4.get("score"), recov,
                float(np.median(prod_vals)), float(np.percentile(prod_vals, 95)), o))
        print()
        results.append(entry)

    # Phase 2 - how much of O_p is explained by n alone, within a set
    print("\nPHASE 2 - WITHIN-SET: O_p explained by pack count alone")
    print("%-22s %10s %10s %12s" % ("set", "R2(O~n)", "Spearman", "max resid %"))
    print("-" * 58)
    for e in results:
        ns = np.array([int(k) for k in e["byPacks"]], dtype=float)
        os_ = np.array([e["byPacks"][k]["opportunity"] for k in e["byPacks"]])
        slope = float((ns * os_).sum() / (ns * ns).sum())     # through the origin
        pred = slope * ns
        ss_res = float(((os_ - pred) ** 2).sum())
        ss_tot = float(((os_ - os_.mean()) ** 2).sum())
        r2 = 1.0 - ss_res / ss_tot
        resid = float(np.abs((os_ - pred) / np.maximum(os_, 1e-12)).max()) * 100
        rho = float(np.corrcoef(np.argsort(np.argsort(ns)),
                                np.argsort(np.argsort(os_)))[0, 1])
        e["withinSetPackFit"] = {"r2ThroughOrigin": round(r2, 6),
                                 "spearman": round(rho, 6),
                                 "maxResidualPct": round(resid, 3)}
        print("%-22s %10.6f %10.4f %11.2f%%" % (name_of(e), r2, rho, resid))

    payload = {
        "stage": "stage13-chase-comparison-frame-v1",
        "question": "what comparison frame does Chase Opportunity belong to",
        "financialProbeNote": (
            "Pack values are an independent-Bernoulli proxy reproducing each card's "
            "authoritative per-pack marginal. It is NOT the production simulator and "
            "assumes cross-card independence the real pack lacks. Valid here only "
            "because the same proxy is used at every n, so the assumption cancels in "
            "the pack-count comparison."),
        "proportionalPricing": "product cost = n x pack cost, value-to-cost held at 0.55",
        "sets": results,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print("\nwrote %s" % OUT)
    return 0


def name_of(e):
    return e["set"]


if __name__ == "__main__":
    raise SystemExit(main())
