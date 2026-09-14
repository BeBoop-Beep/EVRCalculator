# eBay D2F Final Blind certification

- Matcher fingerprint: `a2ac052891df2745f2a2dde8b615a5ccbf1ef23a777eb2a0310e35aef94f6d5e`
- Gold fingerprint: `40da9c4ccbe030124d608c59673902f662e14835cc0d8c4b4fffb89231b97a7a`
- Evaluation code commit: `ece085640a013d2803b0364ddf358ef6b1390854`
- Evaluation timestamp: `2026-09-12T23:20:59.787335+00:00`

Frozen matcher `index_fair_value_ebay_d2m_v2` at `52656c6d1cf6803bbf2ec4f6fc5b14493d68b302` was evaluated against
350 independently frozen Final Blind gold rows. Ambiguous human gold was excluded from
the 339-row primary binary denominator. Deterministic reproduction was identical.

HIGH accepted 153: TP 151, FP 2,
TN 116, FN 70. Precision 98.6928%,
Wilson 95% CI [95.3596%, 99.6408%],
recall 68.3258%, specificity 98.3051%, F1 80.7487%.
Card coverage is 59/70 (84.2857%).
Catastrophic HIGH errors: 2. Decision: FAIL.

This result does not validate the frozen HIGH-confidence identity-filtering layer. It
also does not validate asking-price authority, Near Mint condition, pagination/depth,
completed sales, or Fair Value.
