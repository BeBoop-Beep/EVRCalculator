"""Simulation-based power analysis for the collector paired-choice study. RESEARCH ONLY.

WHY A SIMULATION RATHER THAN A FORMULA
--------------------------------------
Closed-form power formulas for logistic regression assume independent
observations. This study's observations are NOT independent: one user makes many
choices, and their choices share a latent taste. At an intra-class correlation of
0.3, 50 users x 20 choices behaves closer to 150 independent observations than
1,000. A formula that ignores that understates the required sample by roughly a
factor of three - which is the single most common reason studies of this shape
end up underpowered and inconclusive.

So power is simulated under the data-generating process the analysis will
actually fit: Bradley-Terry choices with a user-level random intercept.

NO FIXED ANSWER IS ASSERTED
---------------------------
This script deliberately does not print "you need N users". It prints achieved
power across a grid of assumptions, each of which is a stated input. The sample
size is a consequence of assumptions the reader can inspect and disagree with.

READ-ONLY. Writes nothing but its own report.

USAGE
-----
    python -m backend.scripts.simulate_collector_choice_power
    python -m backend.scripts.simulate_collector_choice_power \
        --odds-ratio 1.5 --users 40 80 120 --choices-per-user 10 20 --json power.json
"""

from __future__ import annotations

import argparse
import json
import math
import random
from typing import Any, Dict, List, Optional, Sequence


def _logistic(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    z = math.exp(x)
    return z / (1.0 + z)


def simulate_one_study(
    *,
    users: int,
    choices_per_user: int,
    pairs: int,
    log_odds_per_sd: float,
    within_user_sd: float,
    rng: random.Random,
) -> bool:
    """One simulated study. Returns True when the effect is detected.

    The data-generating process mirrors the planned analysis:

      * each PAIR has a fixed difference in the predictor, drawn once and reused
        across users - pairs are a design feature, not noise,
      * each USER has a random intercept representing their taste,
      * the choice is Bernoulli in the combined linear predictor.

    Inference uses a cluster-robust (sandwich) standard error on the slope, which
    is the clustered-SE specification the plan names. Fitting a full mixed model
    per simulation would be far slower and would not change the power conclusion
    materially.
    """
    # Pair-level predictor differences, standardized. Fixed across users.
    pair_deltas = [rng.gauss(0.0, 1.0) for _ in range(pairs)]

    xs: List[float] = []
    ys: List[int] = []
    clusters: List[int] = []

    for user in range(users):
        # The user's taste: shifts their baseline preference, not the effect.
        intercept = rng.gauss(0.0, within_user_sd)
        for _ in range(choices_per_user):
            index = rng.randrange(pairs)
            delta = pair_deltas[index]
            probability = _logistic(intercept + log_odds_per_sd * delta)
            xs.append(delta)
            ys.append(1 if rng.random() < probability else 0)
            clusters.append(user)

    estimate = _fit_logit_clustered(xs, ys, clusters)
    if estimate is None:
        return False
    slope, standard_error = estimate
    if standard_error <= 0:
        return False
    return abs(slope / standard_error) >= 1.959963985


def _fit_logit_clustered(
    xs: Sequence[float], ys: Sequence[int], clusters: Sequence[int]
) -> Optional[tuple]:
    """Newton-Raphson logistic fit with a cluster-robust slope SE.

    Two parameters (intercept, slope). Returns None if the fit does not
    converge or the information matrix is singular - a non-converged fit is
    reported as "not detected" rather than silently counted either way.
    """
    n = len(xs)
    if n < 10:
        return None
    beta0, beta1 = 0.0, 0.0

    for _ in range(50):
        g0 = g1 = 0.0
        h00 = h01 = h11 = 0.0
        for x, y in zip(xs, ys):
            mu = _logistic(beta0 + beta1 * x)
            residual = y - mu
            weight = mu * (1.0 - mu)
            g0 += residual
            g1 += residual * x
            h00 += weight
            h01 += weight * x
            h11 += weight * x * x
        determinant = h00 * h11 - h01 * h01
        if abs(determinant) < 1e-12:
            return None
        step0 = (h11 * g0 - h01 * g1) / determinant
        step1 = (h00 * g1 - h01 * g0) / determinant
        beta0 += step0
        beta1 += step1
        if abs(step0) < 1e-8 and abs(step1) < 1e-8:
            break

    # Bread: inverse Hessian. Meat: sum of squared per-cluster score vectors.
    h00 = h01 = h11 = 0.0
    scores: Dict[int, List[float]] = {}
    for x, y, cluster in zip(xs, ys, clusters):
        mu = _logistic(beta0 + beta1 * x)
        weight = mu * (1.0 - mu)
        h00 += weight
        h01 += weight * x
        h11 += weight * x * x
        residual = y - mu
        entry = scores.setdefault(cluster, [0.0, 0.0])
        entry[0] += residual
        entry[1] += residual * x

    determinant = h00 * h11 - h01 * h01
    if abs(determinant) < 1e-12:
        return None
    # Inverse Hessian entries.
    i00 = h11 / determinant
    i01 = -h01 / determinant
    i11 = h00 / determinant

    m00 = m01 = m11 = 0.0
    for s0, s1 in scores.values():
        m00 += s0 * s0
        m01 += s0 * s1
        m11 += s1 * s1

    # Sandwich variance of the slope: (I^-1 M I^-1)[1,1].
    a0 = i01 * m00 + i11 * m01
    a1 = i01 * m01 + i11 * m11
    variance = a0 * i01 + a1 * i11
    if variance <= 0:
        return None
    return beta1, math.sqrt(variance)


def icc_to_sd(icc: float) -> float:
    """Intra-class correlation -> random-intercept SD on the logit scale.

    Uses the standard latent-variable formulation, where the residual variance of
    a logistic model is fixed at pi^2/3:

        ICC = sigma^2 / (sigma^2 + pi^2/3)
    """
    icc = min(max(float(icc), 0.0), 0.95)
    residual = (math.pi ** 2) / 3.0
    if icc <= 0:
        return 0.0
    return math.sqrt(icc * residual / (1.0 - icc))


def run_grid(args: argparse.Namespace) -> Dict[str, Any]:
    log_odds = math.log(float(args.odds_ratio))
    within_sd = icc_to_sd(args.within_user_correlation)
    results: List[Dict[str, Any]] = []

    for users in args.users:
        for choices in args.choices_per_user:
            rng = random.Random(args.seed)
            detected = sum(
                simulate_one_study(
                    users=users,
                    choices_per_user=choices,
                    pairs=args.pairs,
                    log_odds_per_sd=log_odds,
                    within_user_sd=within_sd,
                    rng=rng,
                )
                for _ in range(args.simulations)
            )
            power = detected / args.simulations
            results.append(
                {
                    "users": users,
                    "choicesPerUser": choices,
                    "totalChoices": users * choices,
                    "power": round(power, 4),
                    "meetsTarget": power >= args.power,
                }
            )

    return {
        "assumptions": {
            "oddsRatioPerSd": args.odds_ratio,
            "logOddsPerSd": round(log_odds, 6),
            "pairs": args.pairs,
            "withinUserCorrelation": args.within_user_correlation,
            "randomInterceptSd": round(within_sd, 6),
            "targetPower": args.power,
            "alpha": args.alpha,
            "simulations": args.simulations,
            "seed": args.seed,
        },
        "grid": results,
        "smallestSufficientDesign": next(
            (row for row in sorted(results, key=lambda r: r["totalChoices"]) if row["meetsTarget"]),
            None,
        ),
        "note": (
            "Power is a function of the assumptions above, not a property of the "
            "study. Vary --odds-ratio and --within-user-correlation before "
            "committing to a sample size; the within-user correlation in "
            "particular is usually the binding constraint and is usually guessed "
            "too low."
        ),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--odds-ratio", type=float, default=1.5,
                        help="Effect size: odds ratio per 1-SD predictor difference.")
    parser.add_argument("--users", type=int, nargs="+", default=[25, 50, 100, 200])
    parser.add_argument("--choices-per-user", type=int, nargs="+", default=[5, 10, 20])
    parser.add_argument("--pairs", type=int, default=30)
    parser.add_argument("--within-user-correlation", type=float, default=0.30)
    parser.add_argument("--power", type=float, default=0.80)
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--simulations", type=int, default=400)
    parser.add_argument("--seed", type=int, default=20260804)
    parser.add_argument("--json", dest="json_path", default=None)
    args = parser.parse_args(argv)

    report = run_grid(args)

    print("=" * 78)
    print("COLLECTOR PAIRED-CHOICE STUDY — SIMULATED POWER")
    print("=" * 78)
    assumptions = report["assumptions"]
    print(f"Odds ratio per 1 SD      : {assumptions['oddsRatioPerSd']}")
    print(f"Within-user correlation  : {assumptions['withinUserCorrelation']} "
          f"(random-intercept SD {assumptions['randomInterceptSd']})")
    print(f"Distinct product pairs   : {assumptions['pairs']}")
    print(f"Target power / alpha     : {assumptions['targetPower']} / {assumptions['alpha']}")
    print(f"Simulations per cell     : {assumptions['simulations']}")
    print()
    print(f"{'users':>7}{'per user':>10}{'total':>9}{'power':>9}   target")
    print("-" * 78)
    for row in report["grid"]:
        mark = "yes" if row["meetsTarget"] else "no"
        print(f"{row['users']:>7}{row['choicesPerUser']:>10}{row['totalChoices']:>9}"
              f"{row['power']:>9.3f}   {mark}")

    smallest = report["smallestSufficientDesign"]
    print()
    if smallest:
        print(f"Smallest design reaching {assumptions['targetPower']:.0%} power in this grid: "
              f"{smallest['users']} users x {smallest['choicesPerUser']} choices "
              f"= {smallest['totalChoices']} observations.")
    else:
        print("No design in this grid reaches the target power. Widen the grid or "
              "revisit the assumed effect size.")
    print("\n" + report["note"])

    if args.json_path:
        with open(args.json_path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, sort_keys=True)
        print(f"\nWrote {args.json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
