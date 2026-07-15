-- Desirability-vs-Price Card-Level Validation Study (Prompt A, Stage 1)
-- Standalone, read-only. Reproduces the pooled correlation numbers in
-- docs/research/desirability-card-study-results.md.
--
-- Database: Supabase project TheIndex (public schema).
-- Run each query independently (e.g. psql, Supabase SQL editor, or the MCP).
-- Nothing here writes, and no scoring/UI logic is modified.
--
-- Component definitions replicate the shipped backend exactly:
--   Pure Pokemon Demand = link-weighted avg of composite desirability_score
--       (backend/desirability/set_components.py:_weighted_card_subject_score)
--   Treatment Score     = get_treatment_score(rarity)
--       (backend/desirability/card_appeal.py:TREATMENT_SCORE_RULES)
--   Card Appeal (merged)= calculate_adjusted_card_appeal(demand, treatment, NULL)
--       shipped call passes scarcity=NULL, so it renormalizes to
--       0.6875*demand + 0.3125*treatment when treatment present, else demand.
-- Spearman uses tie-corrected average ranks: rank() + (tie_count-1)/2.

-- Shared building blocks (repeated inline per query so each runs standalone).
--   price(canonical_card_id, price): one positive market price per card
--   demand(card_id, demand): contribution-weighted subject desirability

-- =====================================================================
-- QUERY 1 — Pooled correlations for Pure Demand and merged Card Appeal
--            (all priced Pokemon cards; no rarity control)
-- =====================================================================
WITH price AS (
  SELECT canonical_card_id, MAX(market_price) AS price
  FROM pokemon_canonical_card_market_prices_latest
  WHERE market_price > 0
  GROUP BY canonical_card_id
),
demand AS (
  SELECT l.pokemon_canonical_card_id AS card_id,
    SUM(cs.desirability_score * COALESCE(l.contribution_weight,1.0))
      / NULLIF(SUM(COALESCE(l.contribution_weight,1.0)),0) AS demand
  FROM pokemon_card_desirability_links l
  JOIN pokemon_desirability_composite_scores cs
    ON cs.pokemon_reference_id = l.pokemon_reference_id
  WHERE l.contribution_weight IS NULL OR l.contribution_weight > 0
  GROUP BY l.pokemon_canonical_card_id
),
base AS (
  SELECT c.id, p.price, d.demand,
    btrim(regexp_replace(lower(replace(replace(COALESCE(c.rarity,''),'_',' '),'-',' ')),'\s+',' ','g')) AS norm
  FROM pokemon_canonical_cards c
  JOIN price p  ON p.canonical_card_id = c.id
  JOIN demand d ON d.card_id = c.id
  WHERE c.supertype = 'Pokémon'
),
data AS (
  SELECT id, price, demand,
    CASE
      WHEN norm = '' THEN NULL
      WHEN norm LIKE '%special illustration rare%' THEN 96
      WHEN norm LIKE '%special illustration%' THEN 96
      WHEN norm LIKE '%illustration rare%' THEN 84
      WHEN norm LIKE '%hyper rare%' THEN 82
      WHEN norm LIKE '%gold%' THEN 82
      WHEN norm LIKE '%ultra rare%' THEN 80
      WHEN norm LIKE '%ace spec%' THEN 68
      WHEN norm LIKE '%double rare%' THEN 62
      WHEN norm LIKE '%rare holo%' THEN 45
      WHEN norm LIKE '%holo rare%' THEN 45
      WHEN norm LIKE '%rare%' THEN 36
      WHEN norm LIKE '%uncommon%' THEN 22
      WHEN norm LIKE '%common%' THEN 18
      ELSE 30
    END AS treatment
  FROM base
),
data2 AS (
  SELECT id, price, demand, treatment,
    CASE WHEN treatment IS NULL THEN LEAST(GREATEST(demand,0),100)
         ELSE (0.55*LEAST(GREATEST(demand,0),100) + 0.25*LEAST(GREATEST(treatment,0),100))/0.80
    END AS appeal
  FROM data
),
ranked AS (
  SELECT price, demand, appeal,
    rank() OVER (ORDER BY price)  + (count(*) OVER (PARTITION BY price) -1)/2.0 AS rp,
    rank() OVER (ORDER BY demand) + (count(*) OVER (PARTITION BY demand)-1)/2.0 AS rd,
    rank() OVER (ORDER BY appeal) + (count(*) OVER (PARTITION BY appeal)-1)/2.0 AS ra
  FROM data2
)
SELECT count(*) AS n,
  round(corr(rd, rp)::numeric,4)            AS spearman_pure_demand,
  round(corr(demand, price)::numeric,4)     AS pearson_pure_raw,
  round(corr(demand, ln(price))::numeric,4) AS pearson_pure_logprice,
  round(corr(ra, rp)::numeric,4)            AS spearman_card_appeal,
  round(corr(appeal, price)::numeric,4)     AS pearson_appeal_raw,
  round(corr(appeal, ln(price))::numeric,4) AS pearson_appeal_logprice
FROM ranked;

-- =====================================================================
-- QUERY 2 — Pooled correlation for Treatment Score (rarity proxy)
--            (priced Pokemon cards with a resolvable rarity)
-- =====================================================================
WITH price AS (
  SELECT canonical_card_id, MAX(market_price) AS price
  FROM pokemon_canonical_card_market_prices_latest WHERE market_price > 0 GROUP BY canonical_card_id),
demand AS (
  SELECT l.pokemon_canonical_card_id AS card_id,
    SUM(cs.desirability_score * COALESCE(l.contribution_weight,1.0))/NULLIF(SUM(COALESCE(l.contribution_weight,1.0)),0) AS demand
  FROM pokemon_card_desirability_links l
  JOIN pokemon_desirability_composite_scores cs ON cs.pokemon_reference_id = l.pokemon_reference_id
  WHERE l.contribution_weight IS NULL OR l.contribution_weight > 0 GROUP BY l.pokemon_canonical_card_id),
base AS (
  SELECT c.id, p.price,
    btrim(regexp_replace(lower(replace(replace(COALESCE(c.rarity,''),'_',' '),'-',' ')),'\s+',' ','g')) AS norm
  FROM pokemon_canonical_cards c JOIN price p ON p.canonical_card_id=c.id JOIN demand d ON d.card_id=c.id
  WHERE c.supertype='Pokémon'),
data AS (
  SELECT id, price,
    CASE WHEN norm='' THEN NULL
      WHEN norm LIKE '%special illustration rare%' THEN 96 WHEN norm LIKE '%special illustration%' THEN 96
      WHEN norm LIKE '%illustration rare%' THEN 84 WHEN norm LIKE '%hyper rare%' THEN 82 WHEN norm LIKE '%gold%' THEN 82
      WHEN norm LIKE '%ultra rare%' THEN 80 WHEN norm LIKE '%ace spec%' THEN 68 WHEN norm LIKE '%double rare%' THEN 62
      WHEN norm LIKE '%rare holo%' THEN 45 WHEN norm LIKE '%holo rare%' THEN 45 WHEN norm LIKE '%rare%' THEN 36
      WHEN norm LIKE '%uncommon%' THEN 22 WHEN norm LIKE '%common%' THEN 18 ELSE 30 END AS treatment
  FROM base),
tr AS (
  SELECT price, treatment,
    rank() OVER (ORDER BY price)+(count(*) OVER (PARTITION BY price)-1)/2.0 AS rp,
    rank() OVER (ORDER BY treatment)+(count(*) OVER (PARTITION BY treatment)-1)/2.0 AS rt
  FROM data WHERE treatment IS NOT NULL)
SELECT count(*) AS n_treatment,
  round(corr(rt,rp)::numeric,4)                 AS spearman_treatment,
  round(corr(treatment,price)::numeric,4)       AS pearson_treatment_raw,
  round(corr(treatment, ln(price))::numeric,4)  AS pearson_treatment_logprice
FROM tr;

-- =====================================================================
-- QUERY 3 — Heterogeneity: Pure Demand vs price WITHIN price bands
--            (price band is a coarse proxy for rarity/price level;
--             the rigorous within-rarity-band study is Prompt C)
-- =====================================================================
WITH price AS (
  SELECT canonical_card_id, MAX(market_price) AS price
  FROM pokemon_canonical_card_market_prices_latest WHERE market_price > 0 GROUP BY canonical_card_id),
demand AS (
  SELECT l.pokemon_canonical_card_id AS card_id,
    SUM(cs.desirability_score * COALESCE(l.contribution_weight,1.0))/NULLIF(SUM(COALESCE(l.contribution_weight,1.0)),0) AS demand
  FROM pokemon_card_desirability_links l
  JOIN pokemon_desirability_composite_scores cs ON cs.pokemon_reference_id = l.pokemon_reference_id
  WHERE l.contribution_weight IS NULL OR l.contribution_weight > 0 GROUP BY l.pokemon_canonical_card_id),
data AS (
  SELECT c.id, p.price, d.demand,
    CASE WHEN p.price < 1 THEN 'a_under_1' WHEN p.price < 5 THEN 'b_1_to_5'
         WHEN p.price < 25 THEN 'c_5_to_25' WHEN p.price < 100 THEN 'd_25_to_100'
         ELSE 'e_100_plus' END AS band
  FROM pokemon_canonical_cards c JOIN price p ON p.canonical_card_id=c.id JOIN demand d ON d.card_id=c.id
  WHERE c.supertype='Pokémon'),
ranked AS (
  SELECT band, price, demand,
    rank() OVER (PARTITION BY band ORDER BY demand)+(count(*) OVER (PARTITION BY band, demand)-1)/2.0 AS rd,
    rank() OVER (PARTITION BY band ORDER BY price) +(count(*) OVER (PARTITION BY band, price) -1)/2.0 AS rp
  FROM data)
SELECT band, count(*) AS n,
  round(corr(rd, rp)::numeric,4)             AS spearman_demand_vs_price_within_band,
  round(corr(demand, ln(price))::numeric,4)  AS pearson_demand_logprice_within_band
FROM ranked GROUP BY band ORDER BY band;
