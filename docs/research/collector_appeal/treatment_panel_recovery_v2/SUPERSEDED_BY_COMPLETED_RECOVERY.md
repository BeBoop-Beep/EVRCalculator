# Superseded execution

This branch's guarded VM collection request was intentionally invalidated before provider execution because an independently queued Treatment Panel Recovery V2 run completed first on branch `research/treatment-panel-recovery-v2-pkmnprices-nm-20261001`.

Authoritative completed recovery:

- workflow run: `36913676646`
- provider credits used: `3521`
- cards: `36 / 36`
- recovered matched identities: `16`
- PANEL_READY_MODERATE: `16`
- HISTORY_BLOCKED: `0`
- production writes: `0`
- decision: `TREATMENT_PANEL_RECOVERY_V2_PASS_PHASE2_REOPENED`

Moving this branch HEAD causes the already-queued SHA-pinned VM operation to fail closed at its source-SHA gate, preventing duplicate provider spending.
