# D3 V3 H1R human-label scoring

Date: 2026-09-30

## Human label lock

The user supplied the completed 111-row H1R review export and explicitly confirmed
"completed" in ChatGPT. The uploaded export itself still carried the UI's draft
metadata because no reviewer/attestation field had been filled in the browser.
The repository therefore preserves a separate chat-attested lock artifact without
changing any row label:

- labels: `condition_validation_live_blind_labels_v3_h1r_human_locked.json`
- lock commit: `27720fa48ab6faacd7211d4e5fead9ce674ba6f8`
- labels preserved exactly: yes
- predictions seen before label lock: no
- follow-up flags: 0
- sample fingerprint: `2400874f78365df02aa1e10bed77bb2e`

Human label counts:
- NM 17
- LP 21
- MP 20
- HP 18
- DAMAGED 19
- AMBIGUOUS 0
- UNLABELED 16

## Frozen V3 score

Classifier:
- version: `pkmnprices_sold_title_condition_v3`
- blob: `e492f1990566d15fa1371a3c7576a4244d98a39b`

On all 111 human labels:

- correct: **93 / 111**
- exact accuracy: **83.78%**

Confusion summary:
- DAMAGED: 14 correct; 5 predicted AMBIGUOUS
- HP: 16 correct; 2 predicted AMBIGUOUS
- LP: 16 correct; 5 predicted AMBIGUOUS
- MP: 16 correct; 4 predicted AMBIGUOUS
- NM: 16 correct; 1 predicted UNLABELED
- UNLABELED: 15 correct; 1 predicted DAMAGED

V3 predicted AMBIGUOUS on all 16 deliberately sampled conflict titles. The human
review instead chose a concrete condition for every conflict title.

## Important semantic finding

The 16 conflict rows are not random classifier failures. The human labels follow
a nearly perfect conservative ordinal-resolution pattern:

- NM/LP -> LP
- LP/MP -> MP
- MP/HP -> HP
- HP/DMG -> DAMAGED

When a physical-damage word appears beside an explicit condition grade, the
review generally preserves the explicit grade unless an explicit DMG/Damaged
label is also present. Example: `MP Crease` was labeled MP, while a title that
only says `Crease` was labeled DAMAGED.

Therefore the human task revealed that the useful target semantics are not
"multiple supported labels => AMBIGUOUS." They are closer to "resolve to the
most conservative explicit ordinal condition, with damage-only language used
when no explicit grade is present."

This distinction matters for pricing research because an AMBIGUOUS bucket throws
away information that the human reviewer consistently considers orderable.

## Non-conflict performance

Excluding the 16 conflict-design rows:

- correct: **93 / 95**
- exact accuracy: **97.89%**

Only two non-conflict disagreements remain:

1. Review index 25:
   - title contains explicit `DMG`
   - human label: UNLABELED
   - V3: DAMAGED
   - this is a likely single annotation anomaly, but the submitted human label is
     preserved and is not silently changed.

2. Review index 104:
   - title contains explicit `Mint Condition`
   - human label: NM
   - V3: UNLABELED
   - V3 currently recognizes `Near Mint` / `NM`, not `Mint Condition`.
   - this is a real uncovered title-language case if Mint is intentionally mapped
     into the supported NM bucket.

## HP-stat result remains strong

The canonical-HP redesign remains supported independently of the H1 semantic
score:

- V2R HP-risk rows: 60
- canonical HP metadata present: 60 / 60
- structurally proven exact printed-HP cases: 58 / 60
- full persisted raw-sale rows with standalone HP and canonical HP: 1,906
- structurally proven printed-HP rows: 1,711
- unresolved standalone-HP rows: 195

The structural rule avoids spending human-review effort on machine-verifiable
printed card stats and also avoids V2's card-number-over-suppression defect.

## Decision

`BUCKET_D3_NEEDS_V4_SEVERITY_POLICY`

Do **not** tune V3 and then report H1R as V4 validation. H1R is now evidence for
the semantic redesign.

A V4 candidate may:
1. keep canonical-HP exact-stat disambiguation;
2. resolve multiple explicit condition grades conservatively by ordinal severity;
3. treat physical damage cues as DAMAGED when no explicit grade is present;
4. evaluate whether explicit `Mint Condition` maps to the supported NM bucket.

Any V4 promotion test must use a fresh holdout not present in V1, V2R, or H1R.
The next human set should be small and targeted, not another 300-row review.

Condition-normalized pricing remains blocked pending that fresh V4 confirmation.
Bucket E transaction-primitive research does not need to wait on it.
