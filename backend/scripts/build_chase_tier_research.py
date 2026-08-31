"""Stage-IV objective Chase Tier research build.

RESEARCH ONLY. Writes a JSON artifact under ``docs/research/`` and touches no
production table, score, ranking snapshot, endpoint or schema.

    python -m backend.scripts.build_chase_tier_research --packs 1000000

Cohort, market-date and pack-cost authority are identical to Stages I-III, so
the three studies remain directly comparable rather than merely similar.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from backend.scripts.build_set_chase_efficiency_research import (
    _resolve_market_date,
    code_version,
    resolve_pack_cost,
)

TAG = "[CHASE_TIERS_STAGE4]"

#: Near-mint condition. Tier rules are defined on NM prices throughout the
#: programme, so the temporal series must use the same condition or the
#: comparison would be measuring a condition change, not a market move.
NEAR_MINT_CONDITION_ID = "4f8d1181-670e-4aea-937c-4d98d2e531a6"

#: How far back the temporal study reaches, and how often it samples. Weekly
#: sampling over a quarter gives enough points to see turnover without pulling
#: ninety full price snapshots per set.
TEMPORAL_LOOKBACK_DAYS = 91
TEMPORAL_STRIDE_DAYS = 7


def _rows(response: Any) -> List[Dict[str, Any]]:
    return list(getattr(response, "data", None) or [])


#: Variant ids per PostgREST request. A single ``in`` filter over a whole set's
#: 450 uuids exceeds httpx's URL length limit, so the read is chunked.
VARIANT_CHUNK = 80


def load_historical_prices(client: Any, *, variant_ids: Sequence[str], market_date: str,
                           lookback_days: int = TEMPORAL_LOOKBACK_DAYS,
                           stride_days: int = TEMPORAL_STRIDE_DAYS) -> Dict[str, Dict[str, float]]:
    """Weekly NM price snapshots per card variant.

    ``card_variant_price_observations`` carries no ``set_id``, so the cohort is
    addressed by variant id and chunked to stay inside the URL limit.

    Returns ``{market_date: {card_variant_id: price}}``. Dates with implausibly
    thin coverage are DROPPED rather than used: a partial snapshot would look
    like a mass price collapse and manufacture enormous fake tier churn, which
    is exactly the artefact this study is trying to detect.
    """
    from datetime import date, timedelta

    identifiers = sorted({str(value) for value in variant_ids if value})
    if not identifiers:
        return {}
    end = date.fromisoformat(str(market_date)[:10])
    start = end - timedelta(days=lookback_days)
    wanted = set()
    cursor = end
    while cursor >= start:
        wanted.add(cursor.isoformat())
        cursor -= timedelta(days=stride_days)

    observations: Dict[str, Dict[str, float]] = defaultdict(dict)
    for offset in range(0, len(identifiers), VARIANT_CHUNK):
        chunk = identifiers[offset:offset + VARIANT_CHUNK]
        page = 0
        while True:
            batch = _rows(
                client.table("card_variant_price_observations")
                .select("card_variant_id,market_price,captured_date")
                .in_("card_variant_id", chunk)
                .eq("condition_id", NEAR_MINT_CONDITION_ID)
                .gte("captured_date", start.isoformat())
                .lte("captured_date", end.isoformat())
                .range(page * 1000, page * 1000 + 999)
                .execute()
            )
            for row in batch:
                day = str(row.get("captured_date") or "")[:10]
                if day not in wanted:
                    continue
                try:
                    price = float(row["market_price"])
                except (TypeError, ValueError, KeyError):
                    continue
                if price > 0:
                    observations[day][str(row["card_variant_id"])] = price
            if len(batch) < 1000:
                break
            page += 1

    if not observations:
        return {}
    widest = max(len(prices) for prices in observations.values())
    return {
        day: prices for day, prices in sorted(observations.items())
        if len(prices) >= 0.5 * widest
    }


def build(client: Any, *, market_date: Optional[str],
          canonical_keys: Optional[Sequence[str]], pack_count: int,
          with_temporal: bool) -> Dict[str, Any]:
    from backend.db.services.ev_representativeness_service import resolve_research_cohort
    from backend.db.services.evr_input_preparation_service import EVRInputPreparationService
    from backend.jobs.evr_runner import _resolve_set_config
    from backend.research.set_chase_efficiency.stage4 import STAGE4_VERSION, analyse_set_stage4
    from backend.research.set_chase_efficiency.tiers import candidate_rules, candidate_systems

    day = str(market_date)[:10] if market_date else _resolve_market_date(client)
    targets = resolve_research_cohort(client, market_date=day, canonical_keys=canonical_keys)
    print(f"{TAG} market_date={day} cohort={len(targets)} packs={pack_count} "
          f"rules={len(candidate_rules())} systems={len(candidate_systems())} "
          f"temporal={with_temporal}")

    sets: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []
    started = time.perf_counter()
    preparation = EVRInputPreparationService()

    for index, target in enumerate(targets, start=1):
        set_started = time.perf_counter()
        try:
            config_cls, canonical_key = _resolve_set_config(target.canonical_key)
            config = config_cls()
            prepared = preparation.prepare_for_set(
                config, canonical_key, str(getattr(config, "SET_NAME", canonical_key)))
            cost_basis = resolve_pack_cost(
                client, calculation_run_id=target.calculation_run_id, market_date=day)
            frame = prepared["dataframe"]
            variant_ids = set()
            for column in ("card_variant_id", "reverse_variant_id"):
                if column in frame.columns:
                    variant_ids.update(
                        str(value) for value in frame[column].dropna().tolist() if str(value).strip())
            history = (load_historical_prices(client, variant_ids=sorted(variant_ids),
                                              market_date=day)
                       if with_temporal else None)
            result = analyse_set_stage4(
                config=config, dataframe=prepared["dataframe"], set_id=target.set_id,
                set_name=target.set_name, canonical_key=canonical_key,
                calculation_run_id=target.calculation_run_id, market_date=day,
                pack_cost=cost_basis["packEquivalentCost"], pack_cost_basis=cost_basis,
                pack_count=pack_count, historical_prices=history)
            result["authoritativeRunPackCost"] = target.pack_cost
            result["authoritativeRunMeanPackValue"] = target.simulated_mean
            sets.append(result)
            temporal = result.get("temporalStability") or {}
            print(f"{TAG} [{index}/{len(targets)}] {target.set_name} "
                  f"eligible={result['universe']['eligiblePrintings']} "
                  f"evals={result['simulation']['economicsEvaluations']} "
                  f"(cached {result['simulation']['economicsCacheHits']}) "
                  f"dates={temporal.get('dateCount', 0)} "
                  f"{round(time.perf_counter() - set_started, 1)}s")
        except Exception as error:  # research driver: one bad set must not lose the rest
            failures.append({
                "setName": target.set_name, "canonicalKey": target.canonical_key,
                "calculationRunId": target.calculation_run_id,
                "error": f"{type(error).__name__}: {error}"})
            print(f"{TAG} [{index}/{len(targets)}] {target.set_name} FAILED: {error}")

    return {
        "stage": STAGE4_VERSION,
        "codeVersion": code_version(),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "marketDate": day,
        "packCount": pack_count,
        "cohortSize": len(targets),
        "analysedSetCount": len(sets),
        "candidateRuleCount": len(candidate_rules()),
        "candidateSystemCount": len(candidate_systems()),
        "failures": failures,
        "totalSeconds": round(time.perf_counter() - started, 1),
        "sets": sets,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-date", default=None)
    parser.add_argument("--sets", nargs="*", default=None)
    parser.add_argument("--packs", type=int, default=1_000_000)
    parser.add_argument("--no-temporal", action="store_true",
                        help="skip the historical price pull")
    parser.add_argument("--out", default="docs/research/set_chase_tiers_stage4.json")
    args = parser.parse_args(argv)

    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    from backend.db.clients.supabase_client import create_service_role_client

    report = build(create_service_role_client(), market_date=args.market_date,
                   canonical_keys=args.sets, pack_count=args.packs,
                   with_temporal=not args.no_temporal)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"{TAG} wrote {out} sets={report['analysedSetCount']} "
          f"failures={len(report['failures'])}")
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    sys.exit(main())
