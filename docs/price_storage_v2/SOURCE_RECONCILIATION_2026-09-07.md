# Source reconciliation checkpoint — September 7, 2026

## Scope and result

This is a repository-only reconciliation against the independently captured 89-record
production ledger window `20260905235956`–`20260906233651`, manifest MD5
`d988d2e6e877d3373f613d2351e86339`. No live database export was available in this
session. No database statement was executed and no migration was reapplied.

All **five existing source discrepancies are resolved**. Five exact originals were
recovered from current repository copies, verified against both previously captured
statement MD5s and Git blob SHAs. Together with the three already archived originals,
**eight migrations now have exact sources in both migration directories**. The other
**81 originals remain unavailable** and full reconciliation is still incomplete.
The strict 89-record gate must remain failing until those remaining sources exist.

## Reviewed differences

| Applied version | Earlier repository version | Difference from the applied SQL | Exact bytes / MD5 |
|---|---|---|---|
| 20260906003840 | same | One trailing LF only | 3609 / `5b0e08fcd588379f2c28f5f3e3da148e` |
| 20260906052214 | 20260906045000 | Nominal timestamp plus trailing LF | 9306 / `06d906913f742303d5891084b4acafee` |
| 20260906055303 | 20260905120000 | Nominal timestamp, explanatory comments and blank lines | 2498 / `2cbf1bee9d0cc1b4fa2610baff346524` |
| 20260906055315 | 20260905120100 | Nominal timestamp, explanatory comments and blank lines | 4362 / `f7c7d40f16c9f5cd69673edcbd2d897c` |
| 20260906232931 | same | Two postcondition-description comment lines plus trailing LF | 9139 / `8943fe4b4b3e70611543be1f48496c96` |

No executable statement was changed to recover any of these originals. The two
postcondition statements in Boss's Orders are retained; only their two descriptive
comment lines were extra in the repository copy. Recovery was accepted only on an
exact whole-file checksum match, not on visual resemblance or normalized equality.

The three nominal-timestamp files were removed from executable folders and replaced
by exact originals under the ledger's applied IDs. Both supported migration folders
contain the same eight original byte streams. Their previously commented repository
copies are preserved, byte-for-byte, under `reconciliation_repository_copies/`.
Those preserved copies are documentation, not migrations to execute.

## Audit provenance

Source tree inspected: `a3efb5e8ebde199a58d42d90ff8a27e1e4701544`.
PR source before reconciliation: `2ae72956c276cafab831f884068e70d1c0d92a83`.
Shared base: `7d7ae88565a66607f2b727b12530580d1a816bf6`.
Read-only repository workflow: run `34149261751`, artifact `10028772694`, artifact
SHA256 `6be6e71bc2d8fc914883f0738d675f5e682a928cd8e4654d120b8e4b95046dc0`.
The artifact recovered the first four. The fifth was recovered locally by removing
only the two standalone comment lines (original line numbers 168–169) and final LF;
its resulting Git SHA is `328b56f485efcde435b2f82ce00fbaa93daedac5`, matching the
independently captured production Git-blob calculation.

GitHub initially reported a merge conflict, but after refreshing the PR its merge
calculation succeeded. An independent path comparison found **no overlapping files**
between this PR's changes and the 16 newer main commits at the inspected revision.
The reconciliation commit incorporates that main revision, preserving the newer
Collector Appeal and Market Explorer changes. No update to `main` itself is made.

## Important limits

These files are restored source history, not a new production schema release. Do not
run `db push`, `migration repair`, or manually execute any recovered SQL based on this
checkpoint. The eight-file subset is not a replayable replacement for all missing
prerequisites. New environment restore and full migration replay remain unverified.

The scoped-publisher proposal remains outside migration folders and disabled by
default. No source collection, simulation, public snapshot rebuild, gate enablement,
historical rewrite or storage deletion happened in this reconciliation. Existing
live safety status was not refreshed; prior DB checkpoints remain historical evidence.

## Remaining concrete blocker

Obtain the **81 remaining exact original SQL statement sequences** from the migration
ledger, then run the existing checksum-checked reconciler and the strict inventory.
No missing SQL should be inferred from function names, handwritten replacements, or
placeholders. Post-window migrations must also be checked separately before deployment.
Only after source completeness should real-prerequisite restore, scheduled-writer
integration and end-to-end publication acceptance proceed.
