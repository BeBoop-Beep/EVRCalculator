"""Stage X - chase separability build. READ-ONLY, publishes nothing.

No sealed-product economic variable is read anywhere (Phase 15).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from backend.research.chase_separability_stage10 import (
    _responsibilities,
    evaluate_separability,
    fit_gmm,
)

OUT = Path("docs/research/chase_separability_stage10.json")

COHORT = [
    ("Base", "vintage"), ("Jungle", "vintage"), ("Fossil", "vintage"),
    ("Neo Destiny", "vintage"), ("Champion's Path", "swsh"),
    ("Evolving Skies", "swsh"), ("Crown Zenith", "swsh"),
    ("Cosmic Eclipse", "sm"), ("Paradox Rift", "sv"), ("Paldean Fates", "sv"),
    ("Phantasmal Flames", "sv"), ("Shrouded Fable", "sv"),
]


def fetch(client, name):
    """Universe A prices for one set. Paged - PostgREST caps at 1000 rows."""
    srow = client.table("sets").select("id,name").eq("name", name).eq(
        "is_subset", False).limit(1).execute()
    rows = getattr(srow, "data", srow) or []
    if not rows:
        return None, []
    set_id = rows[0]["id"]
    out, start = [], 0
    while True:
        page = client.table("pokemon_canonical_card_market_prices_latest").select(
            "market_price").eq("set_id", set_id).range(start, start + 999).execute()
        data = getattr(page, "data", page) or []
        out.extend(float(r["market_price"]) for r in data
                   if r.get("market_price") and float(r["market_price"]) > 0)
        if len(data) < 1000:
            break
        start += 1000
    return set_id, out


def core_members(values, k):
    x = np.log(np.asarray(values, dtype=float))
    f = fit_gmm(x, k)
    if f is None:
        return set()
    lab = _responsibilities(x, f["mu"], f["var"], f["w"]).argmax(axis=1)
    return {i for i, l in enumerate(lab) if l == k - 1}


def jaccard(a, b):
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b) if (a | b) else 1.0


def main() -> int:
    from backend.db.clients.supabase_client import create_service_role_client
    client = create_service_role_client()
    rng = np.random.default_rng(11)
    results = []

    print("%-22s %-8s %5s %-34s %4s %7s %6s" % (
        "set", "era", "n", "state", "K", "silvP", "core"))
    print("-" * 92)

    for name, era in COHORT:
        set_id, prices = fetch(client, name)
        if len(prices) < 20:
            print("%-22s %-8s   SKIPPED (%d priced cards)" % (name, era, len(prices)))
            continue
        r = evaluate_separability(prices, boot=150)
        core_n = (r["roster"] or {}).get("coreCount")
        print("%-22s %-8s %5d %-34s %4s %7.3f %6s" % (
            name, era, r["n"], r["state"], r["selectedK"], r["silvermanP"],
            core_n if core_n is not None else "-"))

        entry = {"set": name, "era": era, "setId": set_id, "n": r["n"],
                 "state": r["state"], "selectedK": r["selectedK"],
                 "bic": r["bic"], "silvermanP": r["silvermanP"],
                 "gates": {k: (round(v, 4) if isinstance(v, float) else v)
                           for k, v in r["gates"].items()},
                 "roster": r["roster"]}

        base = core_members(prices, r["selectedK"]) if r["selectedK"] > 1 else set()

        # Phase 10 - independent per-card price noise (NOT uniform scaling)
        noise = {}
        for pct in (0.02, 0.05, 0.10):
            js, states = [], []
            for _ in range(20):
                shocked = [p * (1.0 + rng.uniform(-pct, pct)) for p in prices]
                rr = evaluate_separability(shocked, boot=0)
                states.append(rr["state"])
                js.append(jaccard(base, core_members(shocked, rr["selectedK"])
                                  if rr["selectedK"] > 1 else set()))
            noise["+/-%d%%" % int(pct * 100)] = {
                "stateStable": round(sum(s == r["state"] for s in states) / len(states), 3),
                "coreJaccard": round(float(np.mean(js)), 3)}
        entry["priceNoise"] = noise

        # Phase 10 - uniform scaling MUST be exactly invariant
        uniform_ok = True
        for m in (0.5, 2.0, 10.0):
            rr = evaluate_separability([p * m for p in prices], boot=0)
            if (rr["state"] != r["state"] or rr["selectedK"] != r["selectedK"]
                    or (rr["roster"] or {}).get("coreCount") != core_n):
                uniform_ok = False
        entry["uniformScaleInvariant"] = uniform_ok

        # Phase 9 - bootstrap membership stability
        js = []
        n = len(prices)
        for _ in range(40):
            samp = list(np.asarray(prices)[rng.integers(0, n, n)])
            rr = evaluate_separability(samp, boot=0)
            js.append(jaccard(base, core_members(samp, rr["selectedK"])
                              if rr["selectedK"] > 1 else set()))
        entry["bootstrapCoreJaccard"] = round(float(np.mean(js)), 3)
        results.append(entry)

    payload = {
        "stage": "stage10-chase-separability-v1",
        "universe": "A - pokemon_canonical_card_market_prices_latest (canonical card)",
        "universeNote": (
            "Universe B (drawable card_variant) exists only for the 22 simulated "
            "modern sets and is 1.5-2.5x larger; it shifts 1/HHI by 1.4-53% but "
            "preserves rank order and shape class. Vintage sets have no Universe B."),
        "productInvariance": "no sealed-product price of any kind is read",
        "gates": {"minDeltaBic": 10.0, "minAshmanD": 2.0, "minPosterior": 0.80,
                  "minComponentFraction": 0.02, "minComponentCount": 3},
        "sets": results,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print("\nwrote %s (%d sets)" % (OUT, len(results)))
    print("uniform scale invariance: %d/%d sets exactly invariant" % (
        sum(1 for e in results if e["uniformScaleInvariant"]), len(results)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
