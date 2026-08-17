# Set-page Top Chase authority

The canonical dependency direction is:

```text
authoritative calculation_run_id
  -> rip_decision_service.build_top_chase_contract(run_id=...)
  -> set-page ripDecision.topChase
  -> global Rankings Top Chase projection
```

Set-page construction requests ranked-target metadata with Rankings Top Chase
enrichment disabled. It derives Top Chase directly from the exact run's modeled
input-card probabilities and current Near Mint prices. A previously published
global Rankings snapshot or set-page snapshot is never a Top Chase fallback.

For a supported ranked set, publication fails before the upsert when the
authoritative run is missing, the decision contract is malformed, Top Chase is
missing, or either contract carries a different run ID. The existing snapshot
therefore remains stored when a replacement cannot prove current-run authority.

Global Rankings retains the opposite consumer role: it reads the already
validated set-page `ripDecision.topChase` and rejects a run mismatch.
