# Bucket B bounded completed-sale smoke

Status: **complete for the authorized smoke only**. The 207-card backfill was not started.

## Frozen input and zero-credit preflight

- Base: `e64b28c7e1528dd299a5420c10096047366144e5`
- Core Panel V1: 207 exact physical-card rows
- Fingerprint: `9e3068ffb2e644e3dab2f5c237271afa4efe061ed8f3139187dc9e8331bd1d1f`
- Preflight: 10 selected cards, 0 provider requests, 0 credits, 0 database writes
- Selection covers all seven price bands and both panel eras.
- The collector rejects `card_limit > 10` and `credit_cap > 1,000`.
- Later reviewed work can advance `card_offset` in non-overlapping batches while
  retaining those per-run limits; no 207-card command was executed.

## Credit receipt and database result

Run ID: `5c951f67-135d-4665-bd5a-e8b733480aea`

| Measure | Result |
|---|---:|
| Cards attempted / completed | 10 / 10 |
| Provider requests | 53 |
| Credits | 870 (hard run cap 900) |
| Transactions seen / inserted | 800 / 800 |
| Duplicate / metadata-drift rows | 0 / 0 |
| Exact-attribution rows | 792 |
| Raw exact-variant USD research-eligible rows | 482 |
| Set Value / NM eligible rows | 0 |
| Failed cards | 0 |
| Cards with more historical pages | 10 |

Post-run shadow-table counts were 8 runs, 22 resolved identities, 3,502 persisted
transactions and 22 sync states. The ten smoke states are `PARTIAL`; their resumable
combined-stream cursors are stored, while their incremental `last_ingested_at`
watermarks did not advance. This is intentional until each bounded historical walk
drains.

Per-card receipts:

| Provider card | Credits | Rows | Raw | Graded | Observed span | More history |
|---:|---:|---:|---:|---:|---|---|
| 31828 | 141 | 80 | 42 | 38 | 2026-09-16 to 2026-09-28 | yes |
| 20323 | 81 | 80 | 75 | 5 | 2026-07-25 to 2026-09-21 | yes |
| 24626 | 81 | 80 | 48 | 32 | 2026-08-27 to 2026-09-21 | yes |
| 28314 | 81 | 80 | 54 | 26 | 2026-09-04 to 2026-09-27 | yes |
| 16127 | 81 | 80 | 32 | 48 | 2026-08-24 to 2026-09-22 | yes |
| 34083 | 81 | 80 | 51 | 29 | 2026-09-09 to 2026-09-28 | yes |
| 114847 | 81 | 80 | 59 | 21 | 2026-09-21 to 2026-09-28 | yes |
| 29996 | 81 | 80 | 35 | 45 | 2026-08-25 to 2026-09-20 | yes |
| 24546 | 81 | 80 | 60 | 20 | 2026-08-22 to 2026-09-11 | yes |
| 14359 | 81 | 80 | 53 | 27 | 2026-09-05 to 2026-09-28 | yes |

The first receipt includes the 60-credit combined-stream semantics control. The
steady observed first-slice cost was 81 credits/card: one exact identity lookup and
80 purchased transactions.

## Combined raw + graded semantics

For provider card 31828, one `graded=None` page was compared with separate
`graded=false` and `graded=true` control pages:

- combined: 20 rows, including 13 graded rows;
- raw control: 20 rows; graded control: 20 rows;
- all 20 combined IDs overlapped the control union;
- every combined graded row retained both grader and grade;
- `grade_qualifier` was present and is persisted independently of numeric grade.

The result supports one combined cursor walk. This avoids buying separate full raw
and graded histories.

## Cost projection and recommendation

Observed gross cost was 87 credits/card including the one-time control, or 81
credits/card at steady state for an 80-row slice. Applying the steady rate to 207
cards gives **16,767 credits**, plus the 60-credit control, for a **16,827-credit
lower bound for only the first 80 rows/card**. It is not a full-backfill estimate:
all ten cards still had another cursor, so the actual cursor-exhaustion cost is
strictly higher and cannot be responsibly inferred from this smoke.

Recommended next cap after review: **8,000 credits/day**, at most 80 rows/card per
day, resuming stored cursors and stopping for a new cost report after every panel
slice. This stays well below the existing 20,000/day plan allowance and preserves
capacity for normal operations. Do not authorize full-panel execution from this
report alone; first review a second bounded slice to estimate tail depth.

## Zero-credit summaries and free-first validation

Each receipt includes history span, transaction count/days, 7/30/90/180-day counts,
median days between sales, recency, median/MAD/IQR, grader/grade/qualifier mix, and
raw-versus-graded counts. These summaries are computed from persisted evidence and
consume no provider credits.

The smoke contains PSA, BGS, CGC, ACE and TAG rows, grades 6 through 10 (including
half grades), and `Pristine` qualifiers. The later discrepancy sample must stratify
those dimensions plus price band, era and liquidity. Validate PSA rows against PSA
Auction Prices Realized first; use PSA Price Guide only as a secondary estimate,
Card Ladder Free for public verified-sale spot checks, and CGC resources for identity
and population context. Report transaction/date/identity/qualifier mismatch and
missing-comp rates, with manual review of disagreements. No paid feed or Card Ladder
Pro purchase is justified by this smoke, and no scraping is authorized.

No Fair Value fitting, canonical pricing mutation, Set Value mutation, or raw-card
Near Mint reinterpretation occurred.
