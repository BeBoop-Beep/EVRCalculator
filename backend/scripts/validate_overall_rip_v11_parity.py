"""Overall RIP V11 research-parity gate.

READ-ONLY. Publishes nothing, writes nothing, mutates nothing.

Reproduces the Stage VII selected candidate from PRODUCTION code against the
frozen Stage VI/VII cohort artifact. Production must reproduce the research, not
merely reference it, so every column below is recomputed from
``backend.desirability`` and compared to the artifact rather than copied from it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from backend.desirability.chase_core_k import CORE_MULTIPLE, pack_equivalent_cost
from backend.desirability.chase_opportunity import (
    CHASE_OPPORTUNITY_V1_VERSION,
    chase_opportunity_score,
    compute_chase_opportunity,
)
from backend.desirability.scoring_config import (
    OVERALL_RIP_V11_VERSION,
    OVERALL_RIP_V11_WEIGHTS,
)
from backend.desirability.weighted_rip import compute_overall_rip_v11

DATASET = Path("docs/research/chase_pillar_stage6_dataset.json")
TOL = 1e-9


def _spearman(a, b):
    def rank(xs):
        order = sorted(range(len(xs)), key=lambda i: xs[i])
        r = [0.0] * len(xs)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    ra, rb = rank(a), rank(b)
    n = len(a)
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((ra[i] - ma) * (rb[i] - mb) for i in range(n))
    da = sum((ra[i] - ma) ** 2 for i in range(n)) ** 0.5
    db = sum((rb[i] - mb) ** 2 for i in range(n)) ** 0.5
    return num / (da * db)


def main() -> int:
    payload = json.loads(DATASET.read_text(encoding="utf-8"))
    rows = payload["rows"]
    wf = OVERALL_RIP_V11_WEIGHTS["financial_rip"]
    wc = OVERALL_RIP_V11_WEIGHTS["collector_appeal"]
    wq = OVERALL_RIP_V11_WEIGHTS["chase_opportunity"]

    cost_mismatch = k_mismatch = q_mismatch = v11_mismatch = 0
    worst_cost = worst_q = worst_v11 = 0.0
    prod_scores, research_scores = [], []
    unavailable = []

    for row in rows:
        k = row["coreK"]

        # 1. pack-equivalent cost reproduced from production code
        pec = pack_equivalent_cost(
            product_market_cost=row["productMarketCost"],
            random_pack_count=row["randomPackCount"],
        )
        if pec is None or abs(pec - row["packEquivalentCost"]) > TOL:
            cost_mismatch += 1
        else:
            worst_cost = max(worst_cost, abs(pec - row["packEquivalentCost"]))

        # 2. Core K must be a valid non-negative count and survive the payload
        payload_k = compute_chase_opportunity(k)
        if payload_k["coreK"] != k or payload_k["version"] != CHASE_OPPORTUNITY_V1_VERSION:
            k_mismatch += 1
        if not payload_k["rankable"]:
            unavailable.append(row["productName"])

        # 3. Chase Opportunity vs the research transform, recomputed here
        research_q = 100.0 * k / (k + 10.0)
        prod_q = chase_opportunity_score(k)
        dq = abs(prod_q - research_q)
        if dq > TOL:
            q_mismatch += 1
        worst_q = max(worst_q, dq)

        # 4. Overall V11 vs the Stage VII formula
        f, c = row["financialRip"], row["collectorAppeal"]
        research_v11 = wf * f + wc * c + wq * research_q
        prod = compute_overall_rip_v11(f, c, prod_q)
        dv = abs(prod["score"] - research_v11)
        if dv > 5e-5:  # production rounds to 4dp
            v11_mismatch += 1
        worst_v11 = max(worst_v11, dv)

        prod_scores.append(prod["score"])
        research_scores.append(research_v11)

    pairwise = sum(
        1
        for i in range(len(rows))
        for j in range(i + 1, len(rows))
        if (prod_scores[i] > prod_scores[j]) != (research_scores[i] > research_scores[j])
        and abs(research_scores[i] - research_scores[j]) > 1e-9
    )
    rho = _spearman(prod_scores, research_scores)

    print(f"cohort                     : {len(rows)} products, {payload['setCount']} sets")
    print(f"overall version            : {OVERALL_RIP_V11_VERSION}")
    print(f"core floor multiple        : {CORE_MULTIPLE}x pack-equivalent cost")
    print(f"pack-equivalent cost mism. : {cost_mismatch}   worst {worst_cost:.3e}")
    print(f"Core K mismatches          : {k_mismatch}")
    print(f"Chase Opportunity mismatch : {q_mismatch}   worst {worst_q:.3e}")
    print(f"Overall V11 mismatches     : {v11_mismatch}   worst {worst_v11:.3e}")
    print(f"unavailable Chase          : {len(unavailable)}")
    print(f"Spearman (prod vs research): {rho:.6f}")
    print(f"pairwise disagreements     : {pairwise}")

    ok = (
        cost_mismatch == 0
        and k_mismatch == 0
        and q_mismatch == 0
        and v11_mismatch == 0
        and pairwise == 0
        and abs(rho - 1.0) < 1e-12
    )
    print("\nPARITY:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
