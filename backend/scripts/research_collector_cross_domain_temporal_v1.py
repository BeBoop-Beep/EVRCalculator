"""Independent temporal validation for frozen ANCHOR25 Collector calibration.

Research-only: historical reads plus local artifact writes. No DB persistence path.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

import numpy as np
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.research.collector_appeal_market_validation.stats import prediction_metrics
from backend.scripts.research_collector_cross_domain_calibration_v1 import (
    TARGETS,
    authorities,
    build_candidates,
    controlled_cohort,
    cv_metrics,
    joined_market,
    map_trainers,
    pair_diagnostics,
    preservation,
    raw_within_set,
)
from backend.scripts.research_collector_appeal_market_validation import _paged_select
from backend.scripts.validate_frozen_collector_appeal_v7 import (
    CARD_FINGERPRINT,
    MODEL_FINGERPRINT,
    MODEL_RUN_ID,
    MODEL_VERSION,
    SET_FINGERPRINT,
    verify_frozen_artifact,
)

CANDIDATE = "ANCHOR25"
BASELINE_DATE = "2026-09-11"
TEMPORAL_DATES = ("2026-09-14", "2026-09-17", "2026-09-20", "2026-09-23", "2026-09-26")
EXPECTED_COUNTS = {
    "candidateCards": 4355,
    "modeledRows": 4331,
    "modeledSets": 22,
    "dropped": {"no_modeled_pull_probability": 24},
}
GUARDRAILS = {
    "weightedWithinSetRho": -0.005,
    "controlledOosR2": -0.002,
    "heldOutSpearman": -0.010,
    "pairConcordance": 0.0,
}
BASE_SEED = 20260929
FORMULA_FINGERPRINT = "06f5660047b9b8a4d7349d04b79547b1314c2be3720c245ba8780890db1c114b"
PARENT_SHA = "012e38b1e9a85491ba2ba72b746f8baead6112ea"

PHASE1_PRICE_AUTHORITY = "phase1_sql_20260928204424_market_explorer_root_standard_frozen_roster_v2"
PHASE1_PRICE_SQL = r"""
WITH root AS (
  SELECT %(root_set_id)s::uuid root_set_id
),
members AS (
  SELECT r.root_set_id,r.root_set_id member_set_id FROM root r
  UNION ALL
  SELECT r.root_set_id,c.id
  FROM root r
  JOIN public.sets c
    ON c.parent_opening_set_id=r.root_set_id
   AND c.counts_toward_parent_set_value=true
),
near_mint AS (
  SELECT id
  FROM public.conditions
  WHERE name='Near Mint' AND abbreviation='NM'
  ORDER BY id
  LIMIT 1
),
base_cards AS MATERIALIZED (
  SELECT
    m.root_set_id,
    m.member_set_id,
    pcc.id canonical_card_id,
    pcc.pokemon_tcg_api_card_id,
    pcc.name,
    pcc.number,
    pcc.printed_number,
    pcc.rarity
  FROM members m
  JOIN public.pokemon_canonical_cards pcc
    ON pcc.set_id=m.member_set_id
   AND pcc.set_value_eligible=true
),
manual_identity AS (
  SELECT
    pcc.root_set_id,pcc.member_set_id,pcc.canonical_card_id,pcc.rarity,
    link.legacy_card_id,-1 identity_rank
  FROM base_cards pcc
  JOIN public.pokemon_canonical_card_legacy_identity_links link
    ON link.canonical_card_id=pcc.canonical_card_id
),
parent_api_identity AS (
  SELECT
    pcc.root_set_id,pcc.member_set_id,pcc.canonical_card_id,pcc.rarity,
    c.id legacy_card_id,0 identity_rank
  FROM base_cards pcc
  JOIN public.cards c
    ON c.set_id=pcc.member_set_id
   AND c.pokemon_tcg_api_id=pcc.pokemon_tcg_api_card_id
),
variant_api_identity AS (
  SELECT
    pcc.root_set_id,pcc.member_set_id,pcc.canonical_card_id,pcc.rarity,
    c.id legacy_card_id,1 identity_rank
  FROM base_cards pcc
  JOIN public.card_variants mv
    ON mv.pokemon_tcg_api_id=pcc.pokemon_tcg_api_card_id
  JOIN public.cards c
    ON c.id=mv.card_id
   AND c.set_id=pcc.member_set_id
  WHERE NOT EXISTS (
    SELECT 1 FROM parent_api_identity p WHERE p.canonical_card_id=pcc.canonical_card_id
  )
),
name_number_identity AS (
  SELECT
    pcc.root_set_id,pcc.member_set_id,pcc.canonical_card_id,pcc.rarity,
    c.id legacy_card_id,2 identity_rank
  FROM base_cards pcc
  JOIN public.cards c
    ON c.set_id=pcc.member_set_id
   AND lower(regexp_replace(trim(c.name),'\s+',' ','g'))=
       lower(regexp_replace(trim(pcc.name),'\s+',' ','g'))
   AND regexp_replace(split_part(lower(coalesce(c.card_number,'')),'/',1),'^0+','')
       IN (
         regexp_replace(split_part(lower(coalesce(pcc.number,'')),'/',1),'^0+',''),
         regexp_replace(split_part(lower(coalesce(pcc.printed_number,'')),'/',1),'^0+','')
       )
  WHERE NOT EXISTS (
    SELECT 1 FROM parent_api_identity p WHERE p.canonical_card_id=pcc.canonical_card_id
  )
    AND NOT EXISTS (
      SELECT 1 FROM variant_api_identity v WHERE v.canonical_card_id=pcc.canonical_card_id
    )
),
resolved AS (
  SELECT * FROM manual_identity
  UNION ALL SELECT * FROM parent_api_identity
  UNION ALL SELECT * FROM variant_api_identity
  UNION ALL SELECT * FROM name_number_identity
),
variants AS MATERIALIZED (
  SELECT DISTINCT
    r.root_set_id,r.member_set_id,r.canonical_card_id,r.rarity,r.identity_rank,
    cv.id card_variant_id,cv.printing_type,cv.special_type
  FROM resolved r
  JOIN public.card_variants cv ON cv.card_id=r.legacy_card_id
),
event_intervals AS MATERIALIZED (
  SELECT
    e.card_variant_id,
    e.market_price,
    e.effective_date valid_from,
    lead(e.effective_date) OVER (
      PARTITION BY e.card_variant_id ORDER BY e.effective_date
    ) valid_to
  FROM public.card_variant_price_events_v2 e
  JOIN variants v ON v.card_variant_id=e.card_variant_id
  CROSS JOIN near_mint nm
  WHERE e.condition_id=nm.id
    AND e.source='TCGPlayer'
    AND e.currency='USD'
)
SELECT DISTINCT
  v.root_set_id,v.member_set_id,v.canonical_card_id,v.rarity,v.identity_rank,
  v.card_variant_id,v.printing_type,v.special_type,ei.market_price
FROM variants v
JOIN event_intervals ei
  ON ei.card_variant_id=v.card_variant_id
 AND ei.valid_from<=%(market_date)s::date
 AND (ei.valid_to IS NULL OR %(market_date)s::date<ei.valid_to)
 AND ei.market_price>0
ORDER BY v.canonical_card_id,v.identity_rank,v.card_variant_id
"""
PHASE1_PRICE_SQL_FINGERPRINT = hashlib.sha256(PHASE1_PRICE_SQL.encode("utf-8")).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def canonical_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def fold_seed(market_date: str) -> int:
    return BASE_SEED + int(market_date.replace("-", ""))



def _printing_rank(rarity: str | None, printing_type: str | None, special_type: str | None) -> int:
    rarity = str(rarity or "")
    printing_type = str(printing_type or "")
    if rarity in {"Common", "Uncommon"} and printing_type == "non-holo":
        return 0
    if rarity in {"Common", "Uncommon"} and printing_type == "holo":
        return 1
    if rarity in {"Common", "Uncommon"} and printing_type == "reverse-holo" and special_type is None:
        return 2
    if printing_type == "holo":
        return 0
    if printing_type == "non-holo":
        return 1
    if printing_type == "reverse-holo" and special_type is None:
        return 2
    return 9


def _iso_date(value: Any) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def historical_prices_phase1_sql(conn, service_client, root_set_ids: Sequence[str], market_date: str):
    raw_rows = []
    with conn.cursor() as cur:
        for root_set_id in sorted(root_set_ids):
            cur.execute(
                PHASE1_PRICE_SQL,
                {"root_set_id": root_set_id, "market_date": market_date},
            )
            columns = [desc.name for desc in cur.description]
            raw_rows.extend(dict(zip(columns, values)) for values in cur.fetchall())

    nm_rows = service_client.table("conditions").select("id").eq(
        "name", "Near Mint"
    ).eq("abbreviation", "NM").order("id").limit(1).execute().data or []
    if not nm_rows:
        raise RuntimeError("TEMPORAL_V1_NEAR_MINT_CONDITION_MISSING")
    near_mint_id = str(nm_rows[0]["id"])
    variant_ids = sorted({str(row["card_variant_id"]) for row in raw_rows})
    observation_rows = []
    for index in range(0, len(variant_ids), 250):
        chunk = variant_ids[index:index + 250]
        observation_rows.extend(
            _paged_select(
                lambda chunk=chunk: service_client.table("card_variant_price_observation_ranges_v2")
                .select("card_variant_id,observed_from,observed_through")
                .in_("card_variant_id", chunk)
                .eq("condition_id", near_mint_id)
                .eq("source", "TCGPlayer")
                .eq("currency", "USD")
                .lte("observed_from", market_date)
            )
        )

    cutoff = date.fromisoformat(market_date)
    latest_observed: dict[str, date] = {}
    for row in observation_rows:
        variant_id = str(row["card_variant_id"])
        observed_from = _iso_date(row.get("observed_from"))
        observed_through = _iso_date(row.get("observed_through"))
        if observed_from is None or observed_from > cutoff or observed_through is None:
            continue
        candidate_date = min(observed_through, cutoff)
        previous = latest_observed.get(variant_id)
        if previous is None or candidate_date > previous:
            latest_observed[variant_id] = candidate_date

    grouped = defaultdict(list)
    for row in raw_rows:
        variant_id = str(row["card_variant_id"])
        obs = latest_observed.get(variant_id)
        grouped[str(row["canonical_card_id"])].append(
            {**row, "observed_date": obs.isoformat() if obs else None}
        )

    selected = []
    for card_id in sorted(grouped):
        def sort_key(row):
            obs = _iso_date(row.get("observed_date"))
            return (
                int(row["identity_rank"]),
                obs is None,
                -(obs.toordinal() if obs else 0),
                0 if row.get("special_type") is None else 1,
                _printing_rank(row.get("rarity"), row.get("printing_type"), row.get("special_type")),
                str(row["card_variant_id"]),
            )
        chosen = min(grouped[card_id], key=sort_key)
        selected.append({
            "root_set_id": chosen["root_set_id"],
            "member_set_id": chosen["member_set_id"],
            "canonical_card_id": chosen["canonical_card_id"],
            "card_variant_id": chosen["card_variant_id"],
            "market_price": chosen["market_price"],
            "observed_date": chosen["observed_date"],
            "printing_type": chosen["printing_type"],
            "special_type": chosen["special_type"],
            "source": "canonical_price_events_v2_root_standard_v1",
        })

    by_card = {}
    for row in selected:
        card_id = str(row["canonical_card_id"])
        if card_id in by_card:
            raise RuntimeError(f"duplicate canonical historical price: {card_id}")
        by_card[card_id] = float(row["market_price"])
    return by_card, selected

def attach_prices(membership_rows: Sequence[Mapping[str, Any]], prices: Mapping[str, float]):
    rows, missing = [], []
    for row in membership_rows:
        card_id = str(row["card_id"])
        price = prices.get(card_id)
        if price is None or not math.isfinite(float(price)) or float(price) <= 0:
            missing.append(card_id)
        else:
            rows.append({**row, "market_price": float(price), "log_price": math.log(float(price))})
    return rows, sorted(missing)


def lineage_summary(rows: Sequence[Mapping[str, Any]], market_date: str) -> dict[str, Any]:
    pairs = sorted(
        (str(r.get("canonical_card_id") or ""), float(r["market_price"]))
        for r in rows
        if r.get("canonical_card_id") and r.get("market_price") is not None
    )
    return {
        "marketDate": market_date,
        "returnedRows": len(rows),
        "observedDateCounts": dict(sorted(Counter(str(r.get("observed_date") or "") for r in rows).items())),
        "sourceCounts": dict(sorted(Counter(str(r.get("source") or "") for r in rows).items())),
        "priceStateFingerprint": canonical_hash(pairs),
    }


def metric_delta(candidate: Mapping[str, Any], control: Mapping[str, Any], key: str):
    a, b = candidate.get(key), control.get(key)
    return None if a is None or b is None else float(a) - float(b)


def fold_pass(data_valid: bool, deltas: Mapping[str, float | None]) -> bool:
    return data_valid and all(
        deltas.get(metric) is not None and float(deltas[metric]) >= floor
        for metric, floor in GUARDRAILS.items()
    )


def decide(structural_valid: bool, folds: Sequence[Mapping[str, Any]]) -> str:
    if not structural_valid:
        return "ANCHOR25_TEMPORAL_VALIDATION_INVALID"
    valid = sum(bool(x.get("dataValid")) for x in folds)
    passed = sum(bool(x.get("passed")) for x in folds)
    if valid < 4:
        return "ANCHOR25_TEMPORAL_AUTHORITY_INSUFFICIENT"
    return "ANCHOR25_TEMPORAL_VALIDATION_PASS" if passed >= 4 else "ANCHOR25_TEMPORAL_VALIDATION_FAIL"


def interval(values: Sequence[float]) -> dict[str, Any]:
    arr = np.asarray([float(x) for x in values if math.isfinite(float(x))], dtype=float)
    if not len(arr):
        return {"n": 0, "mean": None, "median": None, "ci95": [None, None]}
    return {
        "n": int(len(arr)),
        "mean": float(np.mean(arr)),
        "median": float(np.median(arr)),
        "ci95": [
            float(np.quantile(arr, 0.025, method="linear")),
            float(np.quantile(arr, 0.975, method="linear")),
        ],
    }


def bootstrap_fold(rows, pairs, cvs, *, draws: int, seed: int) -> dict[str, Any]:
    by_set = defaultdict(list)
    for row in rows:
        by_set[str(row["set_id"])].append(row)
    ids = sorted(by_set)
    pred = {}
    for label in ("CONTROL", CANDIDATE):
        grouped = defaultdict(list)
        for row in cvs[label].get("_predictions", []):
            grouped[str(row["set_id"])].append(row)
        pred[label] = grouped

    out = defaultdict(list)
    rng = np.random.default_rng(seed)
    for _ in range(draws):
        picked = [ids[int(i)] for i in rng.choice(len(ids), len(ids), replace=True)]
        sampled = [row for sid in picked for row in by_set[sid]]
        summaries = {label: raw_within_set(sampled, f"score_{label}")["summary"] for label in ("CONTROL", CANDIDATE)}
        out["weightedWithinSetRho"].append(
            float(summaries[CANDIDATE]["weightedMeanRho"]) - float(summaries["CONTROL"]["weightedMeanRho"])
        )
        out["medianWithinSetRho"].append(
            float(summaries[CANDIDATE]["medianRho"]) - float(summaries["CONTROL"]["medianRho"])
        )

        def pc(label):
            vals = [v for sid in picked for v in pairs[label]["_bySet"].get(sid, [])]
            return float(np.mean(vals)) if vals else math.nan

        out["pairConcordance"].append(pc(CANDIDATE) - pc("CONTROL"))

        def pm(label):
            vals = [p for sid in picked for p in pred[label].get(sid, [])]
            if not vals:
                return {"r2": math.nan, "spearman": math.nan, "mae": math.nan, "rmse": math.nan}
            return prediction_metrics([p["actual"] for p in vals], [p["predicted"] for p in vals])

        control, candidate = pm("CONTROL"), pm(CANDIDATE)
        for key, source in (("controlledOosR2", "r2"), ("heldOutSpearman", "spearman"), ("oosMae", "mae"), ("oosRmse", "rmse")):
            out[key].append(float(candidate[source]) - float(control[source]))

    return {
        "seed": seed,
        "draws": draws,
        "method": "whole-Set resampling with aligned held-out predictions",
        "deltas": {key: interval(values) for key, values in out.items()},
    }


def baseline_lock(conn, service_client, set_ids, membership_rows, candidate_rows, expected_sets):
    prices, lineage = historical_prices_phase1_sql(conn, service_client, set_ids, BASELINE_DATE)
    priced, missing = attach_prices(membership_rows, prices)
    joined = joined_market(priced, candidate_rows)
    replay = raw_within_set(joined, "score_CONTROL")
    expected = {str(x["setId"]): (int(x["n"]), float(x["spearmanLogPrice"])) for x in expected_sets}
    observed = {str(x["setId"]): (int(x["n"]), float(x["spearmanLogPrice"])) for x in replay["sets"]}
    set_checks = []
    for sid in sorted(expected):
        actual = observed.get(sid)
        set_checks.append({
            "setId": sid,
            "nMatch": actual is not None and actual[0] == expected[sid][0],
            "rhoError": None if actual is None else abs(actual[1] - expected[sid][1]),
        })
    summary = replay["summary"]
    global_errors = {
        "medianRho": abs(float(summary["medianRho"]) - TARGETS["medianRho"]),
        "weightedMeanRho": abs(float(summary["weightedMeanRho"]) - TARGETS["weightedMeanRho"]),
        "positivePct": abs(float(summary["positivePct"]) - TARGETS["positivePct"]),
    }
    passed = (
        not missing
        and len(joined) == EXPECTED_COUNTS["modeledRows"]
        and len(set_checks) == EXPECTED_COUNTS["modeledSets"]
        and all(x["nMatch"] and x["rhoError"] is not None and x["rhoError"] <= 1e-12 for x in set_checks)
        and max(global_errors.values()) <= 1e-12
    )
    return {
        "passed": passed,
        "pricedRows": len(joined),
        "missingCount": len(missing),
        "maxPerSetRhoError": max((x["rhoError"] for x in set_checks if x["rhoError"] is not None), default=None),
        "globalErrors": global_errors,
        "setChecks": set_checks,
        "priceLineage": lineage_summary(lineage, BASELINE_DATE),
    }


def evaluate_fold(conn, service_client, market_date, set_ids, membership_rows, candidate_rows, bootstrap_draws):
    prices, lineage = historical_prices_phase1_sql(conn, service_client, set_ids, market_date)
    priced, missing = attach_prices(membership_rows, prices)
    joined = joined_market(priced, candidate_rows)
    represented = len({str(x["set_id"]) for x in joined})
    data_valid = not missing and len(joined) == EXPECTED_COUNTS["modeledRows"] and represented == EXPECTED_COUNTS["modeledSets"]
    base = {
        "marketDate": market_date,
        "dataValid": data_valid,
        "coverage": {
            "expectedRows": EXPECTED_COUNTS["modeledRows"],
            "pricedRows": len(joined),
            "missingRows": len(missing),
            "representedSets": represented,
            "missingCardIds": missing,
        },
        "priceLineage": lineage_summary(lineage, market_date),
    }
    if not data_valid:
        return {**base, "passed": False, "metrics": None, "deltas": None}, {
            "marketDate": market_date, "seed": fold_seed(market_date), "draws": 0, "status": "NOT_RUN_INVALID_COVERAGE"
        }

    within = {label: raw_within_set(joined, f"score_{label}") for label in ("CONTROL", CANDIDATE)}
    pairs = {label: pair_diagnostics(joined, f"score_{label}") for label in ("CONTROL", CANDIDATE)}
    cv_private = {label: cv_metrics(joined, f"score_{label}", private=True) for label in ("CONTROL", CANDIDATE)}
    cv_public = {label: {k: v for k, v in payload.items() if k != "_predictions"} for label, payload in cv_private.items()}
    deltas = {
        "weightedWithinSetRho": float(within[CANDIDATE]["summary"]["weightedMeanRho"]) - float(within["CONTROL"]["summary"]["weightedMeanRho"]),
        "medianWithinSetRho": float(within[CANDIDATE]["summary"]["medianRho"]) - float(within["CONTROL"]["summary"]["medianRho"]),
        "pairConcordance": float(pairs[CANDIDATE]["directionalConcordance"]) - float(pairs["CONTROL"]["directionalConcordance"]),
        "controlledOosR2": metric_delta(cv_public[CANDIDATE], cv_public["CONTROL"], "r2"),
        "heldOutSpearman": metric_delta(cv_public[CANDIDATE], cv_public["CONTROL"], "spearman"),
        "oosMae": metric_delta(cv_public[CANDIDATE], cv_public["CONTROL"], "mae"),
        "oosRmse": metric_delta(cv_public[CANDIDATE], cv_public["CONTROL"], "rmse"),
    }
    public_pairs = {label: {k: v for k, v in payload.items() if k != "_bySet"} for label, payload in pairs.items()}
    metrics = {"withinSet": within, "pairs": public_pairs, "oos": cv_public}
    boot = bootstrap_fold(joined, pairs, cv_private, draws=bootstrap_draws, seed=fold_seed(market_date))
    boot["marketDate"] = market_date
    return {**base, "passed": fold_pass(data_valid, deltas), "metrics": metrics, "deltas": deltas}, boot


def report_text(decision, structural, folds, draws):
    lines = [
        "# Collector Cross-Domain Calibration V1 — Independent Temporal Validation",
        "",
        "Decision: " + decision["decision"],
        "",
        "## Authority",
        "",
        "- Parent Phase 1 SHA: " + PARENT_SHA,
        "- Frozen Collector control: " + MODEL_VERSION + " / " + MODEL_RUN_ID,
        "- Candidate: ANCHOR25 only",
        "- Historical price authority: pinned Phase 1 SQL from 20260928204424_market_explorer_root_standard_frozen_roster_v2",
        "- Production mutations: NONE",
        "",
        "## Structural lock",
        "",
        f"- Frozen artifact valid: {structural['artifactVerified']}",
        f"- Sep-11 exact baseline replay: {structural['baselineReplay']['passed']}",
        f"- Cohort contract: {structural['cohortContract']}",
        f"- Pokemon unchanged: {structural['pokemonUnchanged']}",
        f"- Trainer Spearman >= 0.995: {structural['trainerSpearmanGte995']}",
        "",
        "## Fixed temporal folds",
        "",
        "| Date | Coverage | Pass | delta weighted rho | delta OOS R2 | delta held-out rho | delta pair concordance |",
        "|---|---:|:---:|---:|---:|---:|---:|",
    ]
    for row in folds:
        d = row.get("deltas") or {}
        def fmt(k):
            return "n/a" if d.get(k) is None else f"{float(d[k]):+.6f}"
        lines.append(
            f"| {row['marketDate']} | {row['coverage']['pricedRows']}/{EXPECTED_COUNTS['modeledRows']} | "
            f"{'YES' if row.get('passed') else 'NO'} | {fmt('weightedWithinSetRho')} | "
            f"{fmt('controlledOosR2')} | {fmt('heldOutSpearman')} | {fmt('pairConcordance')} |"
        )
    lines += [
        "",
        "## Gate",
        "",
        f"- Data-valid folds: {decision['dataValidFolds']}/5",
        f"- Passing folds: {decision['passingFolds']}/5",
        "- Required: at least 4 of 5 complete fold passes.",
        f"- Bootstrap: {draws} deterministic whole-Set draws per data-valid fold.",
        "",
        "A PASS supports only a research-only Collector V8 shadow. It does not change current Collector V7 or publish Overall RIP.",
        "",
        decision["decision"],
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", type=Path, default=ROOT / "backend/artifacts/collector_appeal_v7_expanded_candidate_v1.json")
    ap.add_argument("--output-dir", type=Path, default=ROOT / "docs/research/collector_appeal/cross_domain_temporal_v1")
    ap.add_argument("--bootstrap-draws", type=int, default=1000)
    args = ap.parse_args()

    frozen = read_json(args.artifact)
    artifact = verify_frozen_artifact(frozen)
    if frozen["manifest"].get("formulaFingerprint") != FORMULA_FINGERPRINT:
        raise RuntimeError("TEMPORAL_V1_FORMULA_AUTHORITY_MISMATCH")

    pokemon, trainers = authorities(frozen["cards"])
    anchors = map_trainers(trainers, pokemon)
    candidate_rows, equivalence = build_candidates(frozen["cards"], anchors)
    preserve = preservation(candidate_rows)

    expected_sets = read_json(ROOT / "docs/research/collector_appeal_v7_price_validation/within_set_results.json")["card_appeal_v7"]["sets"]
    set_ids = [str(x["setId"]) for x in expected_sets]

    load_dotenv(ROOT / "backend/.env", override=False)
    vm_env = Path("/home/ubuntu/repos/EVRCalculator/backend/.env")
    if vm_env.exists():
        load_dotenv(vm_env, override=False)
    from backend.db.clients.supabase_client import service_read_client
    import psycopg

    database_url = os.environ.get("ACTIONS_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("TEMPORAL_V1_DATABASE_URL_REQUIRED")

    membership, excluded = controlled_cohort(
        service_read_client,
        set_ids,
        price_source="frozen Phase 1 structural membership",
        membership_only=True,
    )
    counts = membership["manifest"]["counts"]
    cohort_contract = counts == EXPECTED_COUNTS and len(excluded) == EXPECTED_COUNTS["dropped"]["no_modeled_pull_probability"]
    with psycopg.connect(database_url, connect_timeout=15, autocommit=True) as sql_conn:
        baseline = baseline_lock(sql_conn, service_read_client, set_ids, membership["rows"], candidate_rows, expected_sets)
    structural = {
        "artifactVerified": bool(artifact.get("verified")),
        "modelVersion": MODEL_VERSION,
        "modelRunId": MODEL_RUN_ID,
        "modelFingerprint": MODEL_FINGERPRINT,
        "cardFingerprint": CARD_FINGERPRINT,
        "setFingerprint": SET_FINGERPRINT,
        "liftEquivalence": equivalence,
        "cohortContract": cohort_contract,
        "cohortCounts": counts,
        "cohortCardFingerprint": canonical_hash(sorted(str(x["card_id"]) for x in membership["rows"])),
        "pokemonUnchanged": preserve["pokemon"][CANDIDATE]["maxScoreDelta"] == 0,
        "trainerSpearman": preserve["trainer"][CANDIDATE]["spearman"],
        "trainerSpearmanGte995": preserve["trainer"][CANDIDATE]["spearman"] >= 0.995,
        "baselineReplay": baseline,
        "historicalPriceAuthority": PHASE1_PRICE_AUTHORITY,
        "historicalPriceSqlFingerprint": PHASE1_PRICE_SQL_FINGERPRINT,
    }
    structural_valid = all([
        structural["artifactVerified"],
        structural["cohortContract"],
        structural["pokemonUnchanged"],
        structural["trainerSpearmanGte995"],
        structural["baselineReplay"]["passed"],
        bool(equivalence.get("passed")),
    ])

    folds, boots = [], []
    if structural_valid:
        with psycopg.connect(database_url, connect_timeout=15, autocommit=True) as sql_conn:
            for market_date in TEMPORAL_DATES:
                fold, boot = evaluate_fold(
                    sql_conn, service_read_client, market_date, set_ids, membership["rows"], candidate_rows, args.bootstrap_draws
                )
                folds.append(fold)
                boots.append(boot)
    else:
        for market_date in TEMPORAL_DATES:
            folds.append({
                "marketDate": market_date,
                "dataValid": False,
                "passed": False,
                "coverage": {"expectedRows": EXPECTED_COUNTS["modeledRows"], "pricedRows": 0, "missingRows": EXPECTED_COUNTS["modeledRows"], "representedSets": 0, "missingCardIds": []},
                "priceLineage": None,
                "metrics": None,
                "deltas": None,
                "status": "NOT_RUN_STRUCTURAL_INVALID",
            })

    decision_name = decide(structural_valid, folds)
    decision = {
        "decision": decision_name,
        "candidate": CANDIDATE,
        "alpha": 0.25,
        "temporalDates": list(TEMPORAL_DATES),
        "dataValidFolds": sum(bool(x.get("dataValid")) for x in folds),
        "passingFolds": sum(bool(x.get("passed")) for x in folds),
        "requiredPassingFolds": 4,
        "guardrails": GUARDRAILS,
        "structuralValid": structural_valid,
        "productionMutations": "NONE",
        "nextStep": "COLLECTOR_V8_SHADOW_ONLY" if decision_name == "ANCHOR25_TEMPORAL_VALIDATION_PASS" else "STOP_ANCHOR25_PROMOTION_WORK",
    }

    out = args.output_dir
    write_json(out / "temporal_results.json", {"parentPhase1Sha": PARENT_SHA, "structural": structural, "folds": folds})
    write_json(out / "bootstrap_intervals.json", {"baseSeed": BASE_SEED, "drawsPerValidFold": args.bootstrap_draws, "folds": boots})
    write_json(out / "decision.json", decision)
    (out / "FINAL_REPORT.md").write_text(report_text(decision, structural, folds, args.bootstrap_draws), encoding="utf-8")
    print(json.dumps({
        "decision": decision_name,
        "structuralValid": structural_valid,
        "dataValidFolds": decision["dataValidFolds"],
        "passingFolds": decision["passingFolds"],
        "outputDir": str(out),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
