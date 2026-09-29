# Bucket A — Core Panel and evidence-contract freeze

Date: 2026-09-29

Issue: #458

Scope: Bucket A only

## Result

Core Panel V1 is frozen at 207 exact canonical/physical-variant rows from F1 fingerprint
`0e7b04f1119ce525fbe387b50b523ac580aa7a14c758e5d16487a334969825d9`, seed
`20260929`, and a target of 30 rows per frozen price band. Its panel fingerprint is
`9e3068ffb2e644e3dab2f5c237271afa4efe061ed8f3139187dc9e8331bd1d1f`.

The manifest is `core_panel_v1_manifest.json`. It contains canonical card, exact card
variant, root set, TCGplayer product, already-resolved PkmnPrices card (nullable), set,
era, price band, edition/printing identity, source fingerprint and panel fingerprint.

## Dry-run audit

- rows: 207;
- price bands: 30 each, except `250_plus` with all 27 eligible mapped rows;
- root sets: 22;
- eras: Scarlet and Violet 170; Mega Evolution 37;
- duplicate canonical/physical identities: 0;
- edition scopes: 207 unspecified (the frozen strict F1 cohort is modern; no vintage
  diagnostic panel was silently added);
- unresolved PkmnPrices identities: 207. This is expected: the existing 12 mappings
  belong to the separate vintage-gap collector. Bucket B may resolve these exact
  TCGplayer identities before collection, without changing panel membership;
- PkmnPrices API calls: 0; provider credits: 0.

First Edition, Unlimited and Shadowless remain separate physical identities. The new
grading-population mapping contract requires one exact `card_variant_id` and an explicit
edition scope; it cannot map one provider identity onto multiple editions.

## Completed contracts

- PkmnPrices sold-page, bounded collection and compatibility wrapper accept optional
  `grader` and `grade`; `graded=None` omits the parameter and requests the combined stream.
- Normalization preserves `grade`, `grader`, and opaque `grade_qualifier`. Grades remain
  strings, including half grades. CGC Pristine 10 and BGS Black Label 10 therefore remain
  distinct from their ordinary grade-10 rows.
- The additive migration adds nullable `grade_qualifier`; existing rows stay reproducible
  from their unchanged provider payload. Append-only transaction identity is unchanged.
- Provider-agnostic, research-only contracts are defined for fixed-panel active-supply
  runs/snapshots/listings and grading-population identity mappings/snapshots. They are
  empty in Bucket A, RLS-enabled, service-role only, and not connected to any production
  price reader.
- Existing `set_value_nm_eligible=false`, unknown-condition, ungraded-only Fair Value
  eligibility checks remain unchanged.

## Legacy graded-schema audit and cleanup plan

Read-only production audit on 2026-09-29 found:

- `grading_companies`: 5 rows; PSA is duplicated. The canonical-looking PSA row is
  `33e25932-55de-4194-af64-50a4465c26fc`; the test PSA row is
  `b9ae5c9a-d312-4239-bb51-4057daa2967d` with note “Test grading company for graded card flow”.
- `graded_card_variants`: one row, `751c7801-d47f-4cb7-8e4f-caf6897da48b`, linked to the
  test PSA row, grade 10, special label `Test Slab`.
- `graded_card_variant_price_observations`: one row,
  `5ada4fc9-b411-4090-93de-d69f13ebcb22`, source `manual_test`, price $249.99,
  observation date 2026-04-07 (`captured_date` is null).

Nothing was deleted, remapped, or promoted in Bucket A because legacy tables still have
read dependencies. Safe later cleanup is an explicit reviewed migration:

1. snapshot the three affected legacy rows and enumerate every FK/view/function consumer;
2. prove the `manual_test` variant/observation has no legitimate collection ownership or
   downstream authority use;
3. delete the `manual_test` observation, then its test variant, inside one transaction;
4. remap any remaining references from the test PSA ID to the canonical PSA ID;
5. delete only the now-unreferenced duplicate PSA row and add a case-insensitive unique
   normalized-company-name constraint;
6. validate row counts and readers, then commit; otherwise roll back.

The legacy tables remain non-authoritative. The new population contract does not inherit
their rows.

## Scope and authority statement

No broad sold backfill, active-supply collection, grading-population collection, Fair Value
fit, Market Scarcity/Market State/Demand Pressure/HYPE-like score, or production pricing
mutation was performed. Canonical TCGplayer pricing, Set Value, Market Explorer, RIP,
Collector Appeal and all production pricing authorities are unchanged.

## Validation

- focused client/normalizer/panel/migration unit suite: 35 passed;
- changed Python modules: compile clean;
- migration mirror: byte-identical SHA-256 in both migration trees;
- PostgreSQL-native syntax parser: full migration parsed successfully after replacing
  the terminal `COMMIT` with `ROLLBACK`, validating the rollback test envelope without
  applying schema changes;
- panel regeneration: identical fingerprint and zero provider requests/credits;
- no production migration was applied by Bucket A.

The repository-wide unit-suite collection is not green on the starting `develop` tree:
it stops on unrelated existing errors in `ingest_pokemon_canonical_cards.py`, the missing
`ScrydexPokemonError` export, and unavailable optional OpenCV/scikit-learn dependencies.
The broader sold-persistence group also contains an existing workflow assertion expecting
`--persist-evidence`, which the current manual V2 workflow does not include. None of those
files were changed for Bucket A; the focused Issue #458 contract suite is green.
