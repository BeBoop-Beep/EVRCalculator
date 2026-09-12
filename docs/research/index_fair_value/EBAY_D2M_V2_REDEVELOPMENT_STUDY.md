# eBay D2M v2 redevelopment study

The v2 corpus is 700 rows: 450 original Development plus 250 V1 Validation rows now
explicitly reclassified as V2 Development. It contains 447 exact, 235 definitive
negative, and 18 ambiguous labels; the binary denominator is 682.

V1 failed because correct card identity text advertised accessory objects. Across all
19 accessory negatives, the marketplace evidence covers art/custom/display cases,
binder inserts, frames, blankets, and selectable products. Category/aspect fields add
no useful distinction. V2 first classifies the object sold; only SINGLE_RAW_CARD can
reach HIGH. Generic benign language such as case fresh does not trigger the ontology.
Choose-your-card evidence cannot prove the selected variation and is never HIGH.

V2 HIGH: accepted 298, TP 298, FP 0, precision
100.0000%, Wilson 95% CI [98.7273%,
100.0000%], recall 66.6667%, coverage
59/70 (84.2857%). Every catastrophic class
has zero HIGH false positives. MEDIUM remains diagnostic-only. No query change or API
call was needed.

Matcher index_fair_value_ebay_d2m_v2, fingerprint a2ac052891df2745f2a2dde8b615a5ccbf1ef23a777eb2a0310e35aef94f6d5e, is frozen at implementation
commit 52656c6d1cf6803bbf2ec4f6fc5b14493d68b302. Final Blind is the only independent certification corpus.
Its 350-row count comes from the original manifest; labels were not read.
