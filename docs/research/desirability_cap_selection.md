# Overall RIP desirability adjustment — cap selection

**Selected cap: 3** · Measured over the 33 sets with a valid Financial RIP
(`backend/scripts/build_desirability_cap_study.py`, 2026-07-16).

## The rule

> Ship cap 5 only if every guardrail passes; otherwise ship cap 3.

Cap 5 does not pass. **Cap 3 ships.**

## Guardrail results

| Guardrail | Cap 3 | Cap 5 |
|---|---|---|
| 1. No adjustment exceeds the cap | **PASS** (max 3.00) | **PASS** (max 4.55) |
| 2. Median absolute adjustment ≤ 2.5 | **FAIL** (3.00) | **FAIL** (3.79) |
| 3. Financial RIP < 40 cannot become Overall RIP > 50 | **PASS** (0 violations) | **PASS** (0 violations) |
| 4. No desirability-only overtake across a ≥10-point gap | **PASS** (0 violations) | **PASS** (0 violations) |
| Sets clamped at the cap | **30 of 33** | **0 of 33** |
| Sets whose rank changes vs Financial RIP | 9 | 11 |

Guardrail 4 holds by construction, not by luck: the maximum spread between two
sets is `2 × cap`, so at cap 5 a 10-point Financial gap closes to exactly a tie
and never a strict overtake. At cap 3 it cannot close at all. This is pinned in
`test_desirability_cannot_close_a_10_point_financial_gap`.

## Guardrail 2 fails for both caps, and that is a finding, not a bug

The formula assumes desirability is centred on 50:

```
adjustment = clamp((D - 50) / 10, -cap, +cap)
```

It is not. **Every one of the 33 simulated sets scores above 50** — minimum
51.07 (Shrouded Fable), median ≈ 87. The simulated cohort is modern booster
sets with popular rosters, so `(D - 50) / 10` is positive for all of them and
lands near +3.7 for a typical set.

Two consequences worth stating plainly:

1. **The adjustment is a bonus, never a penalty.** No set in the current data
   receives a negative adjustment. The bounded ± framing describes a symmetry
   the data does not exercise.
2. **Median |adjustment| cannot fall below 2.5 at any cap ≥ 2.5**, because the
   median set's raw adjustment is +3.79. Guardrail 2 is unsatisfiable while the
   baseline sits at 50. Cap 3 fails it by less than cap 5, and cap 3 is the
   stated fallback, so cap 3 ships.

## The cost of cap 3, stated up front

At cap 3, **30 of 33 sets clamp to exactly +3.0**. The adjustment therefore adds
a near-constant offset to almost every set while still reordering 9 of them. It
is close to carrying no information: only three sets land inside the cap —
Shrouded Fable (+0.11), Chaos Rising (+1.99), and Scarlet & Violet Base Set
(+2.56). Cap 5 clamps none and preserves the full +0.11 → +4.55 spread.

So cap 3 is the lower-influence choice by the letter of the guardrails, but it
buys that by flattening the signal rather than by scaling it down.

## Largest adjustments

**Cap 3** — top positive (all clamped at +3.0): Ascended Heroes (Financial 22.32,
D 95.48), Astral Radiance (15.08, D 90.00), Battle Styles (13.57, D 85.79),
Black Bolt (16.53, D 84.01), Brilliant Stars (13.67, D 93.38).

Smallest adjustments (the only unclamped sets): Shrouded Fable +0.11 (D 51.07),
Chaos Rising +1.99 (D 69.89), Scarlet & Violet Base Set +2.56 (D 75.60).

**Cap 5** — top positive: Ascended Heroes +4.55 (D 95.48), Paldean Fates +4.53
(D 95.33), Fusion Strike +4.39 (D 93.91), Scarlet & Violet 151 +4.36 (D 93.61),
Brilliant Stars +4.34 (D 93.38). Smallest: the same three sets as cap 3.

## Score movement vs rank movement

Rank changes are not proportional to score changes, because Financial RIP is
tightly clustered: the 33 sets span roughly 5–30, so several sit within one
adjustment-width of each other. At cap 3, nine sets change rank even though
30 of them received an **identical** +3.0 — those moves are caused entirely by
the three unclamped sets falling behind, not by any set being rewarded. That is
the clearest evidence that a near-uniform adjustment still reorders a clustered
leaderboard, and it is why score movement and rank movement are reported apart.

## Recommendation for a future pass (not taken here)

Re-centring the baseline on the observed distribution (median ≈ 87 rather than
50) would make the adjustment two-sided, restore its differentiating power at a
small cap, and let guardrail 2 pass. That is a formula change and is out of
scope for this pass; it is recorded here so the next reader does not rediscover
the same fact from the same data.
