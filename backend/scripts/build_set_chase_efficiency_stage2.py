"""Stage-II Set Chase Efficiency research build.

RESEARCH ONLY. Writes a JSON artifact under ``docs/research/`` and touches no
production table, score, ranking snapshot or API contract.

    python -m backend.scripts.build_set_chase_efficiency_stage2 --packs 1000000

Cohort, market-date and pack-cost authority are identical to Stage I - this
reuses ``resolve_research_cohort`` and ``resolve_pack_cost`` from the Stage-I
driver so the two studies are directly comparable rather than merely similar.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from backend.scripts.build_set_chase_efficiency_research import (
    _resolve_market_date,
    code_version,
    resolve_pack_cost,
)

TAG = "[SET_CHASE_EFFICIENCY_STAGE2]"


def build(client: Any, *, market_date: Optional[str], canonical_keys: Optional[Sequence[str]],
          pack_count: int) -> Dict[str, Any]:
    from backend.db.services.ev_representativeness_service import resolve_research_cohort
    from backend.db.services.evr_input_preparation_service import EVRInputPreparationService
    from backend.jobs.evr_runner import _resolve_set_config
    from backend.research.set_chase_efficiency.stage2 import analyse_set_stage2
    from backend.research.set_chase_efficiency.version import (
        SET_CHASE_EFFICIENCY_RESEARCH_VERSION,
    )

    day = str(market_date)[:10] if market_date else _resolve_market_date(client)
    targets = resolve_research_cohort(client, market_date=day, canonical_keys=canonical_keys)
    print(f"{TAG} market_date={day} cohort={len(targets)} packs={pack_count}")

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
            result = analyse_set_stage2(
                config=config, dataframe=prepared["dataframe"], set_id=target.set_id,
                set_name=target.set_name, canonical_key=canonical_key,
                calculation_run_id=target.calculation_run_id, market_date=day,
                pack_cost=cost_basis["packEquivalentCost"], pack_cost_basis=cost_basis,
                pack_count=pack_count)
            result["authoritativeRunPackCost"] = target.pack_cost
            result["authoritativeRunMeanPackValue"] = target.simulated_mean
            sets.append(result)
            supported = sum(1 for u in result["universes"] if u.get("supported"))
            print(f"{TAG} [{index}/{len(targets)}] {target.set_name} "
                  f"universes={supported}/{len(result['universes'])} "
                  f"core={result['coreExtended']['coreCount']} "
                  f"{round(time.perf_counter() - set_started, 1)}s")
        except Exception as error:  # research driver: one bad set must not lose the rest
            failures.append({
                "setName": target.set_name, "canonicalKey": target.canonical_key,
                "calculationRunId": target.calculation_run_id,
                "error": f"{type(error).__name__}: {error}",
            })
            print(f"{TAG} [{index}/{len(targets)}] {target.set_name} FAILED: {error}")

    return {
        "researchVersion": SET_CHASE_EFFICIENCY_RESEARCH_VERSION,
        "stage": "stage2-chase-universe-and-beat-the-buy-v1",
        "codeVersion": code_version(),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "marketDate": day,
        "packCount": pack_count,
        "cohortSize": len(targets),
        "analysedSetCount": len(sets),
        "failures": failures,
        "totalSeconds": round(time.perf_counter() - started, 1),
        "sets": sets,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-date", default=None)
    parser.add_argument("--sets", nargs="*", default=None)
    parser.add_argument("--packs", type=int, default=1_000_000)
    parser.add_argument("--out", default="docs/research/set_chase_efficiency_stage2.json")
    args = parser.parse_args(argv)

    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    from backend.db.clients.supabase_client import create_service_role_client

    report = build(create_service_role_client(), market_date=args.market_date,
                   canonical_keys=args.sets, pack_count=args.packs)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"{TAG} wrote {out} sets={report['analysedSetCount']} "
          f"failures={len(report['failures'])}")
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    sys.exit(main())
