# Overall RIP V13 Collector V7 controlled integration

Decision: `OVERALL_RIP_V13_COLLECTOR_V7_BLOCKED`

The 86/4/10 substitution is conceptually coherent and does not require weight retuning. It is not safe to promote in the present deployment boundary.

The live 2026-09-10 supported cohort contains 276 products across 22 sets. Replacing only Collector V5 with frozen V7 produces a mean score change of -0.2784, median -0.6181, range -2.1923 to +2.7425, and rank agreement of 0.9828. Nine of the prior top ten remain; Temporal Forces Booster Box enters and Pitch Black Pokémon Center Elite Trainer Box exits.

Collector remains secondary. Contribution variance is 47.4642 for Financial, 0.3278 for Chase, and 0.6198 for V7 Collector. V7 is nearly uncorrelated with Financial (Pearson -0.0122) and weakly related to Chase (0.1541). The default 86/4/10 weights therefore remain the frozen recommendation.

Rank movement is nevertheless material because many product scores are tightly spaced: 257 rows change rank, mean absolute movement is 11.86, 202 rows move at least five places, and the maximum move is 39. This movement is explained by actual set-level V5→V7 changes, led upward by Shrouded Fable and Obsidian Flames and downward by White Flare.

## Promotion blocker

Production persists and serves the canonical model through V12-specific columns and `overallRipV12` projections. There is no append-only V13 persistence field set, inactive V13 Rankings/Set-page generation, atomic V13 score-plus-rank promotion RPC, or deployed reader that recognizes a V13 identity. Changing only constants or overwriting V12 columns would violate V12 immutability and could publish a V13 score with a V12 rank or projection.

The task also forbids deploying main. Since the running application cannot be upgraded to understand a new public authority, a production cutover cannot pass the required post-promotion parity checks in this task. No schema, score, snapshot, history, or production row was changed.

The next controlled step must implement append-only V13 storage and readers, deploy that code, build inactive coherent Rankings and Set-page generations, validate tier/entitlement parity, and atomically promote them. V12 remains the exact rollback authority.

Machine-readable evidence is in [overall_rip_v13_collector_v7_shadow.json](overall_rip_v13_collector_v7_shadow.json).
