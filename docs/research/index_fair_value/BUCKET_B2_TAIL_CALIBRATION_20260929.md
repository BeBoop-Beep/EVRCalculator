# Bucket B2 sold-history tail calibration

Final disposition: **BUCKET_B2_NEEDS_MORE_CALIBRATION**

The bounded calibration is complete. It resumed only the ten cursors created by
Bucket B smoke run `5c951f67-135d-4665-bd5a-e8b733480aea`; it did not start the
207-card breadth backfill.

## Authority and continuation proof

- Base: `4e551946326c49fb35c7471c0c444b946df2398b`
- Core Panel V1 fingerprint:
  `9e3068ffb2e644e3dab2f5c237271afa4efe061ed8f3139187dc9e8331bd1d1f`
- Preflight: ten identities, ten `PARTIAL` states, ten non-null cursors, zero
  provider calls, zero credits and zero writes.
- Every purchased card receipt records a non-null input-cursor hash. The input
  hash for slices two and three equals the prior slice's output hash. No card
  search/identity call exists in the B2 runner and no newest-page request is
  possible on its calibration path.
- Nine undrained cards retain `last_ingested_at = null`. The one drained card
  advanced it only after `has_more=false`.

## Credit and write receipts

| Layer | Run ID | Credits | Rows bought / inserted | Drained in layer | DB insert + state seconds |
|---:|---|---:|---:|---:|---:|
| 80→160 | `6b6f4a50-ec62-4e8d-ad1a-72726f07981d` | 800 | 800 / 800 | 0 | 3.988345 |
| 160→240 | `3791f86e-ae44-4cab-bf47-1662a7a6a6e9` | 800 | 800 / 800 | 0 | 3.422993 |
| 240→320 | `8f6a96ad-ecd6-4b50-8e5b-4db4946eebd3` | 775 | 775 / 775 | 1 | 3.302178 |
| **Total** |  | **2,375 / 3,000 cap** | **2,375 / 2,375** | **1** | **10.713516** |

All three subruns stayed below 1,000 credits and completed without failures,
duplicates or provider-metadata drift. Approximate measured DB throughput for
the timed insert/state sections was 221.7 rows/second. Post-run shadow health:
11 runs, 22 provider identities, 5,877 transaction rows and 22 sync states.

## Per-card final state

| Provider card | Cumulative rows | Newly bought | Oldest sold | Raw | Graded | Exact / Shared / Unknown | State |
|---:|---:|---:|---|---:|---:|---|---|
| 16127 | 320 | 240 | 2026-01-19 | 95 | 225 | 305 / 0 / 15 | has more |
| 24626 | 320 | 240 | 2026-07-11 | 170 | 150 | 294 / 0 / 26 | has more |
| 31828 | 320 | 240 | 2026-08-10 | 125 | 195 | 320 / 0 / 0 | has more |
| 14359 | 320 | 240 | 2026-07-26 | 204 | 116 | 319 / 0 / 1 | has more |
| 28314 | 320 | 240 | 2026-03-17 | 151 | 169 | 287 / 0 / 33 | has more |
| 24546 | 320 | 240 | 2026-07-28 | 229 | 91 | 314 / 0 / 6 | has more |
| 20323 | 295 | 215 | 2025-05-31 | 152 | 143 | 231 / 0 / 64 | **drained** |
| 34083 | 320 | 240 | 2026-07-29 | 123 | 197 | 320 / 0 / 0 | has more |
| 114847 | 320 | 240 | 2026-08-07 | 216 | 104 | 320 / 0 / 0 | has more |
| 29996 | 320 | 240 | 2026-01-26 | 99 | 221 | 280 / 0 / 40 | has more |

Drain observations: 0/10 at 160, 0/10 at 240, and 1/10 by 320 (the drained
history ended at 295). For the nine open histories, median and maximum observed
depth are both lower-bounded at **≥320 rows**. Tail maxima remain unknown.

## Cost and duration calibration

An additional complete 80-row layer cost 800 credits; the third cost 775 only
because one card drained after 55 rows. The steady breadth-layer minimum is
`207 × 80 = 16,560` transaction credits, or **at least three 8,000-credit B
days** for one 80-row pass. Provider identity resolution for the remaining
panel rows is extra but small relative to transaction depth.

The ten-card sample averages at least 317.5 retained rows/card after this run,
with nine tails still open. Applying only that observed lower bound to 207 cards
implies at least 65,723 transaction credits, plus unresolved identity lookups:
**at least nine 8,000-credit B days**. This is explicitly a lower bound, not a
completion estimate.

A cautious operational planning range is **12–20 B days**, with the upper end
still not a statistical bound because 90% of calibration histories remain open.
Another reviewed tail layer is needed before treating that range as budget
support. Stay on Pro: B is intentionally limited to 8,000 credits/day after C,
so a Scale quota does not shorten the policy-bound schedule. No paid upgrade is
recommended from this evidence.

## Inactive breadth-first coordinator design

This is a design only; no schedule/workflow is activated.

1. C daily continuity owns first priority and must report the current Phoenix
   date healthy/complete before B is eligible.
2. B receives at most 8,000 credits for that Phoenix day. Provider headers and
   the durable daily ledger may only reduce the available amount.
3. Acquire `/tmp/pkmnprices-api.lock`, then non-blockingly acquire the heavy
   publication lock. Exit cleanly if either cannot be acquired.
4. Refuse execution while `/home/ubuntu/state/db-safety/hold.json` exists or is
   a symlink.
5. Reuse exact provider identities. Visit each undrained Core Panel card once
   per pass, buying at most one 80-row cursor slice, then cycle to the next card.
   Skip `core_panel_backfill_complete=true` cards.
6. Persist evidence before advancing the cursor. Advance `last_ingested_at` only
   on `has_more=false`; interruption therefore replays append-only rows safely.
7. Operational window: no earlier than **21:30 America/Phoenix**, after the C
   continuity job and its health check. Eligibility is based on C health, not
   wall clock alone. Avoid scrape/publication peaks and the existing 20:30 sold
   evidence job.
8. Emit per-run credit, cursor-hash, inserted/duplicate, drain and DB timing
   receipts. Stop before the next provider request when the remaining budget
   cannot cover its requested page.

No Fair Value fitting, condition-to-NM conversion, Market Scarcity score,
canonical price mutation or Set Value mutation occurred.
