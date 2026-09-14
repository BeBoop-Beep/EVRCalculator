# eBay D3 v3 redevelopment study

All 1,050 previously labeled listings are v3 development evidence: 668
exact, 353 definitive negative, and
29 ambiguous. None remains independent certification evidence.

V2's `D2-0674` failure was a directional multiplicity gap: it recognized `2x` but not
`X2`. V3 uses contextual bidirectional quantities, explicit card counts, pairs, sets,
packs, playsets, and selectable offers while protecting collector-number fractions.

`D2-0310` has condition `Ungraded`, conditionId `4000`, empty category/aspects, no
subtitle, and no captured grading metadata. Its slab status came only from human image
inspection. V3 rejects every affirmative structured/textual graded signal, but records
this irreducible deterministic limitation as `IMAGE_ONLY_GRADED_RISK`.

Development-only HIGH: 450 accepted, 449 TP, 1 FP, precision
99.7778%, Wilson 95% CI [98.7521%,
99.9608%], recall 67.2156%, and card coverage
61/70 (87.1429%). The sole HIGH error is the
image-only graded row. These figures are development diagnostics, not authority.

The next certification is preregistered as a fresh 300-HIGH precision cohort plus an
independent 420-row card-stratified coverage/failure cohort. Expected unique review
burden is about 600, capped at 720. The capture budget is exactly 140 Browse calls,
well below the 5,000-call daily default.
