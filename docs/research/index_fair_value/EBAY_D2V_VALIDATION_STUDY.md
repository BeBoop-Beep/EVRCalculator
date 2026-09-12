# eBay D2V frozen-matcher Validation study

Validation gold reconstructed at 250/250, with 170 positives,
79 negatives, and 1 ambiguous row
excluded from binary metrics. The matcher remained index_fair_value_ebay_d2m_v1, fingerprint
d47384a38912b59bb073c0b7a655e3120424154fa1617faaca541c86d53f2e1c; no matcher, alias, variant, condition, or query rule changed.

## HIGH result

Accepted 106: TP 104, FP 2, TN 77, FN 66. Precision
98.1132%, Wilson 95% CI [93.3801%,
99.4810%], recall 61.1765%, specificity
97.4684%, F1 75.3623%, card coverage 54/70
(77.1429%).

| Target card | Listing title | Human label | Matcher evidence | Accepted reason |
|---|---|---|---|---|
| Furret | Pokemon Furret 168/159 Journey Together Extended Art Custom Case | SEALED_OR_ACCESSORY | {"language": "COMPATIBLE", "name": "MATCH", "number": {"observed": ["168"], "state": "MATCH", "target": "168"}, "raw": "COMPATIBLE", "set": {"conflicts": [], "matched": ["journey together"], "state": "EXACT"}, "variant": {"conflicting_treatments": [], "matched": [], "parallel_terms": [], "state": "ABSENT"}} | THREE_FACTOR_IDENTITY |
| Mega Lucario ex | Pokemon Mega Lucario ex 179 /132 Mega Evolution Extended Art Custom Case | SEALED_OR_ACCESSORY | {"language": "COMPATIBLE", "name": "MATCH", "number": {"observed": ["179"], "state": "MATCH", "target": "179"}, "raw": "COMPATIBLE", "set": {"conflicts": [], "matched": ["mega evolution"], "state": "EXACT"}, "variant": {"conflicting_treatments": [], "matched": [], "parallel_terms": [], "state": "ABSENT"}} | THREE_FACTOR_IDENTITY |

Both false positives are catastrophic SEALED_OR_ACCESSORY cases. Precision, Wilson
lower bound, card coverage, and zero-catastrophic-error gates fail. This is a structural
logic defect, not an allowed threshold-policy choice. No Validation-derived patch was made.

MEDIUM has 12 rows, precision 100.0000%, recall contribution
7.0588%, and 6 incremental
cards; it remains diagnostic-only. Matcher ambiguity is 8.8000%.

Final Blind remains sealed. Matcher v1 cannot be frozen for Final evaluation. Return to
Development with a new matcher version, then repeat independent Validation while keeping
the 350-row Final Blind partition untouched.
