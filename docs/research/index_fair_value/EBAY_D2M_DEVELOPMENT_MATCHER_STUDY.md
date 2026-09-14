# eBay D2M Development matcher study

## Gold authority

Development only: 450/450 effective labels, 0 skipped, 0 unlabeled. Definitive positive:
277; definitive negative: 156; ambiguous
pending adjudication: 17. Validation and Final Blind labels were not
loaded. Price fields are excluded from matcher inputs and outputs.

## Frozen D1 baseline

Accepted 183/450. On 433 definitive rows: TP 171, FP 11,
TN 145, FN 106; precision 93.9560%, recall 61.7329%,
specificity 92.9487%, F1 74.5098%.

| Target card | Listing title | Gold label | D1 verdict | Failure |
|---|---|---|---|---|
| Grubbin | Grubbin Reverse Holo 18/162 Temporal Forces Pokemon Card NM Art Kagemaru Himeno | RELATED_BUT_WRONG_VARIANT | EXACT_MATCH | D1 did not model treatment/parallel identity. |
| Lt. Surge's Bargain | Pokemon Lt. Surge's Bargain (120/197) Mega Evolution LP REVERSE HOLO | RELATED_BUT_WRONG_VARIANT | EXACT_MATCH | D1 did not model treatment/parallel identity. |
| Lt. Surge's Bargain | Lt. Surge's Bargain - 120/132 Reverse Holo Mega Evolution NM Pokemon | RELATED_BUT_WRONG_VARIANT | EXACT_MATCH | D1 did not model treatment/parallel identity. |
| Lt. Surge's Bargain | Lt. Surge's Bargain 120/132 Mega Evolution Reverse Holo Pokemon Card | RELATED_BUT_WRONG_VARIANT | EXACT_MATCH | D1 did not model treatment/parallel identity. |
| Lt. Surge's Bargain | 120/132 Lt Surge's Bargain - ME01 Mega Evolution Reverse Holo NM Pokemon Trainer | RELATED_BUT_WRONG_VARIANT | EXACT_MATCH | D1 did not model treatment/parallel identity. |
| Arbok | Arbok 101/162 Common Temporal Forces Pokemon Reverse Holo Near Mint | RELATED_BUT_WRONG_VARIANT | EXACT_MATCH | D1 did not model treatment/parallel identity. |
| Arbok | Arbok #101/162 Common, Reverse Holo SV05: Temporal Forces Pokemon | RELATED_BUT_WRONG_VARIANT | EXACT_MATCH | D1 did not model treatment/parallel identity. |
| Bronzor | 2024 Scarlet & Violet Series - Temporal Forces Bronzor Common #68 | RELATED_BUT_WRONG_VARIANT | EXACT_MATCH | D1 did not model treatment/parallel identity. |
| Team Rocket's Giovanni | Team Rocket's Giovanni 204/217 Reverse Holo Pokemon ME: Ascended Heroes NM | RELATED_BUT_WRONG_VARIANT | EXACT_MATCH | D1 did not model treatment/parallel identity. |
| Team Rocket's Giovanni | Team Rocket's Giovanni 204/217 - Reverse Holo Ascended Heroes Uncommon - NM - | RELATED_BUT_WRONG_VARIANT | EXACT_MATCH | D1 did not model treatment/parallel identity. |
| Coalossal | Coalossal 95/162 Reverse Holo | Temporal Forces | Pokemon Card | RELATED_BUT_WRONG_VARIANT | EXACT_MATCH | D1 did not model treatment/parallel identity. |

## Error taxonomy and D2M result

D1 definitive false positives were treatment/parallel failures. Development includes 77
graded, 29 wrong-number, 23 wrong-variant, 2 wrong-set, 5 wrong-language, 11 lot/bundle,
and 9 sealed/accessory examples. D2M applies hard exclusions, collector-number parsing,
versioned set aliases, and treatment evidence while keeping condition separate.

HIGH accepted 194 at 100.0000%
precision, Wilson 95% CI [98.0583%,
100.0000%], recall 70.0361%, card coverage
58/70 (82.8571%). No definitive negative is HIGH.
MEDIUM count is 21; ambiguity rate is
3.7778%.

Rules span distinct cards and sets reported in the taxonomy. Validation remains the
independent generalization test. D1 queries are unchanged and no API calls were issued.
Matcher index_fair_value_ebay_d2m_v1 fingerprint d47384a38912b59bb073c0b7a655e3120424154fa1617faaca541c86d53f2e1c is frozen. The human-ambiguous,
matcher-disagreement, and difficult-variant rows remain pending in the second-review queue.
