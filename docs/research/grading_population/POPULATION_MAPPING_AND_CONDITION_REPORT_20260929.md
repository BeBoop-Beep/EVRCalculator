# Bucket D free-foundation report

Date: 2026-09-29

## Population adapter and exact mapping

`backend/pricing_pipeline/grading_population.py` converts a provider response into the
deployed Bucket A tables:

- `grading_population_provider_identities_v1`;
- `grading_population_snapshots_v1`.

The fixture-backed pilot uses no credential and no live population data. Its mapping must
provide canonical card ID, exact `card_variant_id`, explicit internal and provider edition
scope, provider card ID, match basis and confidence. It fails closed when provider and
internal scopes differ. First Edition, Unlimited and Shadowless can never share a mapping.
Unresolved or review-state records are not normalized as exact mappings.

The identity row retains provider/universal IDs, exact internal variant, match basis,
confidence and semantics. Snapshot rows retain grader, opaque string grade, opaque string
qualifier, observed population, observed date, source timestamp, provider ID lineage and
raw grade-key/count evidence. Half grades are strings. BGS Black 10, BGS Pristine 10,
ordinary CGC 10, CGC Pristine 10 and CGC Perfect 10 remain distinct.

The fixture and tests prove the storage boundary writes only the two Bucket A population
tables. No commercial API request or production population insert was made.

Population language is fixed to:

> observed graded population / submissions represented by the grading service

It must never be presented as number of copies in existence, surviving physical supply,
or a price.

## Condition classifier

`backend/pricing_pipeline/sold_condition_classifier.py` is deterministic and versioned as
`pkmnprices_sold_title_condition_v1`. It emits:

- condition label: NM, LP, MP, HP, DAMAGED, AMBIGUOUS or UNLABELED;
- confidence: HIGH, MEDIUM, LOW or NONE;
- evidence tokens;
- classifier version;
- ambiguity reason for conflicting labels.

The classifier recognizes bounded explicit labels/abbreviations and a short, reviewed set
of physical-damage phrases. It intentionally does not reinterpret “pack fresh,” “minty,”
“excellent,” or “clean” as Near Mint. Multiple condition classes yield AMBIGUOUS.

The additive research table `pkmnprices_sold_condition_classifications_v1` stores results
beside, not inside, immutable PkmnPrices sold evidence. It is version-keyed, RLS-enabled,
service-role insert/select only, and is not connected to a price reader.

## Reviewed validation artifact

`condition_validation_sample_v1.json` contains 35 human-authored rows: five for each
output class. Coverage includes vintage/modern, low/mid/high values, short/verbose titles,
explicit/implicit/conflicting language and false-positive risks from card names, a set
name, abbreviations and seller marketing language.

Deterministic replay produced:

- 35/35 correct;
- precision 1.000 for each of NM, LP, MP, HP, DAMAGED, AMBIGUOUS and UNLABELED;
- zero errors on this reviewed contract fixture.

This is a small precision-oriented contract sample. It does not estimate real-world recall,
prevalence or price-adjustment accuracy. No classifier-derived price adjustment is
authorized. A later representative, randomly sampled production-title review is required
before any broader use.

## Authority and cost boundary

- graded price and population remain separate;
- no GemRate credential was used and no live population was ingested;
- no grader site or Card Ladder page was scraped;
- no subscription was purchased;
- no Fair Value fit, Market Scarcity score or production pricing change was made.

## Validation

- focused Bucket D plus PkmnPrices contracts: 50 passed;
- reviewed classifier replay: 35/35, deterministic output artifact;
- changed Python modules compile cleanly;
- Bucket D migration files are byte-identical;
- PostgreSQL-native parser accepted the complete condition migration with terminal
  `COMMIT` replaced by `ROLLBACK`;
- no population-provider credentials were present or used;
- no production migration or data write was performed.

The broader pricing-pipeline suite reached 145 passed / 2 skipped and one unrelated
existing failure in `test_daily_multi_source_pipeline.py::test_health_all_green`; Bucket D
does not change that health logic or fixture.

Program outcome: the free/fixture foundation is ready. Live normalized population remains
gated on GemRate’s written commercial access and data-rights response.
