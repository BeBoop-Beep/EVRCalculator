"""Stage XI build - Hill spectrum, HC significance, EVT, EV-HHI. READ-ONLY."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from backend.research.chase_significance_stage11 import (
    concentration_contribution,
    contributor_effective_count,
    evt_tail,
    hc_profile,
    removal_influence,
    shares,
)

OUT = Path("docs/research/chase_significance_stage11.json")

COHORT = [
    ("Base", "vintage"), ("Jungle", "vintage"), ("Fossil", "vintage"),
    ("Neo Destiny", "vintage"), ("Champion's Path", "swsh"),
    ("Evolving Skies", "swsh"), ("Crown Zenith", "swsh"),
    ("Cosmic Eclipse", "sm"), ("Paradox Rift", "sv"), ("Paldean Fates", "sv"),
    ("Phantasmal Flames", "sv"), ("Shrouded Fable", "sv"),
    ("Ascended Heroes", "sv"), ("Prismatic Evolutions", "sv"),
]

# Universe B (drawable variant) exists only for simulated modern sets.
UNIVERSE_B_SETS = {
    "Evolving Skies", "Crown Zenith", "Paradox Rift", "Paldean Fates",
    "Phantasmal Flames", "Shrouded Fable", "Ascended Heroes",
    "Prismatic Evolutions",
}


def _rows(resp):
    return getattr(resp, "data", resp) or []


def set_id_for(client, name):
    r = _rows(client.table("sets").select("id").eq("name", name)
              .eq("is_subset", False).limit(1).execute())
    return r[0]["id"] if r else None


def universe_a(client, set_id):
    out, start = [], 0
    while True:
        page = _rows(client.table("pokemon_canonical_card_market_prices_latest")
                     .select("market_price").eq("set_id", set_id)
                     .range(start, start + 999).execute())
        out.extend(float(r["market_price"]) for r in page
                   if r.get("market_price") and float(r["market_price"]) > 0)
        if len(page) < 1000:
            return out
        start += 1000


def universe_b(client, set_id):
    """Drawable variants plus their pull rates, from the latest recorded run."""
    r = _rows(client.table("simulation_card_variant_pull_rates")
              .select("calculation_run_id,created_at").eq("set_id", set_id)
              .order("created_at", desc=True).limit(1).execute())
    if not r:
        return [], []
    run = r[0]["calculation_run_id"]
    vals, evs, start = [], [], 0
    while True:
        page = _rows(client.table("simulation_card_variant_pull_rates")
                     .select("price_used,pull_count,effective_pull_rate")
                     .eq("calculation_run_id", run).eq("set_id", set_id)
                     .range(start, start + 999).execute())
        for row in page:
            p, pc = row.get("price_used"), row.get("pull_count")
            if not p or float(p) <= 0 or not pc or int(pc) <= 0:
                continue
            vals.append(float(p))
            rate = row.get("effective_pull_rate")
            evs.append(float(p) * float(rate) if rate else 0.0)
        if len(page) < 1000:
            return vals, evs
        start += 1000


def spearman(a, b):
    def rank(x):
        order = np.argsort(-np.asarray(x))
        r = np.empty(len(x))
        r[order] = np.arange(len(x))
        return r
    ra, rb = rank(a), rank(b)
    return float(np.corrcoef(ra, rb)[0, 1])


def main() -> int:
    from backend.db.clients.supabase_client import create_service_role_client
    client = create_service_role_client()
    rng = np.random.default_rng(23)
    out = []

    print("%-22s %-8s %5s | %7s %7s %7s | %7s %7s %6s | %6s" % (
        "set", "era", "n", "D1", "D2", "D4", "N_HC", "hcTop1", "c50", "evtK"))
    print("-" * 104)

    for name, era in COHORT:
        sid = set_id_for(client, name)
        if not sid:
            continue
        a = universe_a(client, sid)
        if len(a) < 30:
            continue
        p = hc_profile(a)
        h = p["hill"]
        e = evt_tail(a)
        ek = e.get("tailK") if e.get("supported") else None
        print("%-22s %-8s %5d | %7.2f %7.2f %7.2f | %7.2f %7.3f %6d | %6s" % (
            name, era, p["n"], h["D1"], h["D2"], h["D4"], p["nHC"],
            p["hcTop1"], p["cardsFor50"], ek if ek else "-"))

        entry = {
            "set": name, "era": era, "universe": "A", "n": p["n"],
            "hhi": round(p["hhi"], 6),
            "hill": {k: round(v, 4) for k, v in h.items()},
            "nHC": round(p["nHC"], 4),
            "hcTop1": round(p["hcTop1"], 5), "hcTop3": round(p["hcTop3"], 5),
            "hcTop5": round(p["hcTop5"], 5), "hcTop10": round(p["hcTop10"], 5),
            "hcMedian": float("%.3e" % p["hcMedian"]),
            "hcTopOverMedian": round(p["hcTopOverMedian"], 1),
            "cardsFor25": p["cardsFor25"], "cardsFor50": p["cardsFor50"],
            "cardsFor75": p["cardsFor75"], "cardsFor90": p["cardsFor90"],
            "evt": {k: v for k, v in e.items() if k != "hillPlot"},
            "removalInfluenceTop5": removal_influence(a, top=5),
        }

        # Phase 14 - uniform scaling must leave HC values bit-identical
        base_hc = concentration_contribution(shares(a))
        entry["uniformScaleExact"] = all(
            np.allclose(base_hc, concentration_contribution(shares([x * m for x in a])),
                        rtol=0, atol=1e-12)
            for m in (0.5, 2.0, 10.0, 100.0))

        # Phase 14 - independent per-card price noise
        noise = {}
        for pct in (0.02, 0.05, 0.10):
            rhos, tops, moves = [], [], []
            for _ in range(30):
                sh = [x * (1.0 + rng.uniform(-pct, pct)) for x in a]
                hc2 = concentration_contribution(shares(sh))
                rhos.append(spearman(base_hc, hc2))
                t1 = set(np.argsort(-base_hc)[:10])
                t2 = set(np.argsort(-hc2)[:10])
                tops.append(len(t1 & t2) / 10.0)
                moves.append(float(np.abs(np.sort(base_hc)[::-1][:10]
                                          - np.sort(hc2)[::-1][:10]).max()))
            noise["+/-%d%%" % int(pct * 100)] = {
                "spearman": round(float(np.mean(rhos)), 5),
                "top10Overlap": round(float(np.mean(tops)), 3),
                "maxHcMove": round(float(np.mean(moves)), 5)}
        entry["priceNoise"] = noise

        # Phase 15 + 16 - Universe B and EV-HHI
        if name in UNIVERSE_B_SETS:
            bvals, bevs = universe_b(client, sid)
            if len(bvals) >= 30:
                pb = hc_profile(bvals)
                entry["universeB"] = {
                    "n": pb["n"], "hhi": round(pb["hhi"], 6),
                    "nHC": round(pb["nHC"], 4), "hcTop1": round(pb["hcTop1"], 5),
                    "D2": round(pb["hill"]["D2"], 4),
                    "cardsFor50": pb["cardsFor50"]}
                if sum(bevs) > 0:
                    ev = np.asarray(bevs, dtype=float)
                    ev = ev[ev > 0] / ev[ev > 0].sum()
                    entry["evHHI"] = {
                        "hhiEV": round(float((ev ** 2).sum()), 6),
                        "nEffEV": round(1.0 / float((ev ** 2).sum()), 3),
                        "nEffValueB": round(pb["hill"]["D2"], 3),
                        "nHC_EV": round(contributor_effective_count(
                            concentration_contribution(np.sort(ev)[::-1])), 4)}
        out.append(entry)

    payload = {
        "stage": "stage11-chase-significance-v1",
        "hcDefinition": "HC_i = s_i^2 / HHI ; sum(HC) = 1",
        "nHCIdentity": "N_HC = 1/sum(HC^2) = D4^3 / D2^2 (verified to machine precision)",
        "orderingCaveat": ("HC is a strictly increasing function of value share, so HC "
                           "ranking is IDENTICAL to price ranking. HC changes scale and "
                           "interpretation, never discrimination."),
        "productInvariance": "no sealed-product price of any kind is read",
        "sets": out,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print("\nwrote %s (%d sets)" % (OUT, len(out)))
    print("uniform-scale exact: %d/%d" % (
        sum(1 for e in out if e["uniformScaleExact"]), len(out)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
