#!/usr/bin/env python3
"""Desirability-vs-Price card-level study (Prompt A, Stage 1) — standalone.

Read-only. Pulls one row per priced Pokemon card (price, pure-demand,
treatment, merged card-appeal) and computes pooled + within-band Spearman /
Pearson correlations. Reproduces docs/research/desirability-card-study-results.md.

It does NOT touch UI, scoring, or the database's writable state, and is not
wired into the app. Nothing is written back.

Usage:
    export DATABASE_URL='postgresql://USER:PASSWORD@HOST:5432/postgres'
    python docs/research/desirability_card_study.py

Requires: psycopg2-binary (or psycopg), numpy, scipy.
The scipy Spearman/Pearson use average-rank tie handling, matching the
tie-corrected ranks in the companion .sql file to 4 decimals.
"""
from __future__ import annotations

import math
import os
import sys

# Treatment rules mirror backend/desirability/card_appeal.py exactly (ordered).
TREATMENT_RULES = [
    ("special illustration rare", 96.0), ("special illustration", 96.0),
    ("illustration rare", 84.0), ("hyper rare", 82.0), ("gold", 82.0),
    ("ultra rare", 80.0), ("ace spec", 68.0), ("double rare", 62.0),
    ("rare holo", 45.0), ("holo rare", 45.0), ("rare", 36.0),
    ("uncommon", 22.0), ("common", 18.0),
]


def normalize_rarity(value):
    import re
    return re.sub(r"\s+", " ", str(value or "").strip().lower().replace("_", " ").replace("-", " "))


def treatment_score(rarity):
    norm = normalize_rarity(rarity)
    if not norm:
        return None
    for needle, score in TREATMENT_RULES:
        if needle in norm:
            return score
    return 30.0


def clamp(v):
    return max(0.0, min(float(v), 100.0))


def card_appeal(demand, treatment):
    """Shipped calculate_adjusted_card_appeal(demand, treatment, scarcity=None)."""
    if demand is None:
        return None
    if treatment is None:
        return clamp(demand)
    return (0.55 * clamp(demand) + 0.25 * clamp(treatment)) / 0.80


# One row per priced Pokemon card with its contribution-weighted subject demand.
PULL_SQL = """
WITH price AS (
  SELECT canonical_card_id, MAX(market_price) AS price
  FROM pokemon_canonical_card_market_prices_latest
  WHERE market_price > 0 GROUP BY canonical_card_id),
demand AS (
  SELECT l.pokemon_canonical_card_id AS card_id,
    SUM(cs.desirability_score * COALESCE(l.contribution_weight,1.0))
      / NULLIF(SUM(COALESCE(l.contribution_weight,1.0)),0) AS demand
  FROM pokemon_card_desirability_links l
  JOIN pokemon_desirability_composite_scores cs
    ON cs.pokemon_reference_id = l.pokemon_reference_id
  WHERE l.contribution_weight IS NULL OR l.contribution_weight > 0
  GROUP BY l.pokemon_canonical_card_id)
SELECT c.id::text, p.price::float8, d.demand::float8, c.rarity
FROM pokemon_canonical_cards c
JOIN price p  ON p.canonical_card_id = c.id
JOIN demand d ON d.card_id = c.id
WHERE c.supertype = 'Pokémon';
"""


def band_of(price):
    if price < 1:   return "a_under_1"
    if price < 5:   return "b_1_to_5"
    if price < 25:  return "c_5_to_25"
    if price < 100: return "d_25_to_100"
    return "e_100_plus"


def main():
    dsn = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")
    if not dsn:
        sys.exit("Set DATABASE_URL to a read connection string for the TheIndex Postgres.")
    try:
        import psycopg2 as driver  # type: ignore
    except ImportError:
        import psycopg as driver  # type: ignore
    import numpy as np
    from scipy import stats

    with driver.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(PULL_SQL)
        rows = cur.fetchall()

    prices, demands, treatments, appeals, bands = [], [], [], [], []
    for _cid, price, demand, rarity in rows:
        t = treatment_score(rarity)
        prices.append(price)
        demands.append(demand)
        treatments.append(t)
        appeals.append(card_appeal(demand, t))
        bands.append(band_of(price))

    prices = np.array(prices, float)
    demands = np.array(demands, float)
    appeals = np.array(appeals, float)
    log_price = np.log(prices)

    def report(name, x, y=prices, logy=log_price):
        mask = ~np.isnan(x)
        xr, yr, lr = x[mask], y[mask], logy[mask]
        sp = stats.spearmanr(xr, yr).statistic
        pr = stats.pearsonr(xr, yr).statistic
        plg = stats.pearsonr(xr, lr).statistic
        print(f"  {name:<18} n={mask.sum():>6}  Spearman={sp:+.4f}  Pearson(raw)={pr:+.4f}  Pearson(logP)={plg:+.4f}")

    print(f"\nPooled across all priced Pokemon cards (N={len(prices)}):")
    report("Pure Demand", demands)
    report("Treatment", np.array([t if t is not None else np.nan for t in treatments], float))
    report("Card Appeal", appeals)

    print("\nHeterogeneity — Pure Demand vs price WITHIN price bands:")
    bands_arr = np.array(bands)
    for b in ["a_under_1", "b_1_to_5", "c_5_to_25", "d_25_to_100", "e_100_plus"]:
        m = bands_arr == b
        sp = stats.spearmanr(demands[m], prices[m]).statistic
        print(f"  {b:<12} n={m.sum():>6}  Spearman(demand,price)={sp:+.4f}")


if __name__ == "__main__":
    main()
