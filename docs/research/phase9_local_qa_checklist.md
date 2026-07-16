# Phase 9 — Local Integration & Performance QA Checklist

**Status: REQUIRED before the video.** Everything in this document is the part
of Phase 9 that could not be verified from the implementation machine (its
PostgREST link ran at ~16 kB/s; the `anon` role has a 3s statement timeout, so
every live read timed out). The code is fixture-tested end to end
(765 backend + 490 frontend tests), but §13 Integration QA and §14 Performance
QA below must be executed against live data on a machine with a normal
connection before the phase can be called READY FOR VIDEO.

## 0. Prerequisites — rebuild the snapshots once

The canonical contract only enters production payloads when snapshots are
rebuilt. Old rows serve empty `rip`/`ripCore`/`openingExperience` objects (the
critical payload then carries the warning
`"Canonical RIP contract is not in this snapshot yet; rebuild set-page snapshots."`).

```bash
# From the repo root, with backend/.env loaded:
python backend/scripts/build_pokemon_explore_rankings_snapshot.py --all --commit
python backend/scripts/build_pokemon_set_page_snapshots.py --all --commit
# (or the combined pipeline)
python backend/scripts/build_pokemon_public_snapshots.py --commit
```

Note: the "desirability validation" step was removed from
`build_pokemon_public_snapshots.py` deliberately — do not re-add it.

Then start both servers (ports per prod-smoke convention: frontend 3100,
backend 8000) and hard-refresh with the browser cache disabled.

## 1. §13 Integration QA — golden sets

For each set, open the set page Insights tab AND find its Explore row.

### Ascended Heroes (`ascendedHeroes`)
- [ ] Collector Appeal displays **96.1** — NOT a relative 100.0
- [ ] Roster Desirability **95.5**
- [ ] Dual-Path Depth **27.1%** (a percent, no letter tier on it)
- [ ] RIP hero shows the canonical `rip.score` (a weighted blend of the four
      pillar scores — verify: 0.58·profit + 0.20·safety + 0.12·stability +
      0.10·96.0942, computed from the pillar cards' own displayed scores)
- [ ] Rank badge reads `#N of 21` — the denominator must be 21
- [ ] "Why this score" names Gengar (and Dragonite if in top 3) with TWO
      specific printings each: card number + rarity + "1 in N" odds + image
- [ ] Collector Appeal Impact strip: Weight 10%, Direct RIP Contribution ≈ 9.6 pts

### Chaos Rising (`chaosRising`)
- [ ] Collector Appeal **75.5**
- [ ] Roster Desirability **69.9**
- [ ] Dual-Path Depth **37.2%**

### Shrouded Fable (`shroudedFable`)
- [ ] Collector Appeal **56.8**
- [ ] Subject-path explanation reflects its narrow structure (few dual-path
      subjects; no fabricated breadth)

### Prismatic Evolutions (`prismaticEvolutions`)
- [ ] Collector Appeal **94.6**
- [ ] Multi-path explanation present
- [ ] NO set-value validation chart anywhere on the page

### Cross-surface consistency (all four sets)
- [ ] Explore leaderboard RIP score == set-page hero RIP score (same decimals)
- [ ] Explore rank == set-page rank
- [ ] Leaderboard "Collector Appeal" mode sorts by the new scores and shows 21 rows
- [ ] No row or badge anywhere says "of 33"
- [ ] No SWSH set appears in any leaderboard mode

### Legacy removal
- [ ] "Desirability Evidence", "Does the market agree?", "Set Validation",
      "Card Validation", rank-agreement bars, and the desirability-vs-set-value
      scatter appear NOWHERE
- [ ] Left nav shows "Opening Experience" (not "Desirability Evidence")
- [ ] Old deep links land on the new section:
      `/TCGs/Pokemon/Sets/ascendedHeroes?tab=insights&section=desirability-proof`
      (also `desirability-validation`, `card-desirability-price`) must scroll
      to the Opening Experience card
- [ ] During load, no legacy value flashes before the canonical value renders
      (throttle the network to Slow 3G in devtools and watch the hero + pillars:
      they must go skeleton → canonical, never legacy → canonical)

### Hidden-set direct access
- [ ] Navigate directly to a SWSH set page (e.g. Evolving Skies). The RIP hero
      must show an unavailable state, NOT a canonical-looking score

## 2. §14 Performance QA

Use the browser Network tab, empty cache, on the set Insights page and Explore.

- [ ] Request count on set Insights is UNCHANGED vs before the phase
      (critical + secondary + module snapshots — no new request for CA7 or for
      any opening-experience submetric; the Opening Experience section must
      render entirely from `/insights/critical`)
- [ ] `/insights/critical` payload size: record before/after. Expected: the new
      `rip`/`ripCore`/`openingExperience` objects add a few KB; the removed
      `desirabilityValidation` disappears from `/insights` and
      `/insights/secondary`, which should offset most of it
- [ ] `/explore/rip-statistics/targets` timing: first request after backend
      restart pays the Collector Appeal bundle build ONCE (pull-model read is
      the expensive input, ~11 MB); subsequent requests must be cache-hits at
      the previous latency. Record: cold, warm, and a second user's warm.
- [ ] Set-to-set navigation stays instant on cached sets (no new loading panel
      between sections)
- [ ] No layout shift when the Opening Experience section hydrates
- [ ] Backend logs show `[collector-appeal] built N sets ... in Xms` at most
      once per 6h TTL, never once per request (that would be the forbidden
      per-request rebuild)

## 3. Sign-off

When every box above is checked, Phase 9's verdict flips from
NOT READY FOR VIDEO to READY FOR VIDEO. If any golden number is off by more
than rounding, STOP — do not adjust display code to match; the discrepancy
means either stale snapshots (rebuild and re-check) or a source-data change
(diff the dry-run artifact's source manifest before deciding anything).
