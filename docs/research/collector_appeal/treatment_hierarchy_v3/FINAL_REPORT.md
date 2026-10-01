# Treatment Hierarchy V3 — Expanded Modern Pilot

Decision: `TREATMENT_HIERARCHY_V3_DIAGNOSTIC_ONLY`

Workflow run: `36930772601`

## Frozen evidence

Treatment Panel Recovery V3:
- recovery run: `36929725640`
- artifact: `11196076068`
- artifact digest: `sha256:e3dc70d260e53e079348db304774c89812b9a9fc0d35654ecf6d0470f1fc974b`
- history fingerprint: `acdec6152a4027ec6a7440a2ac879fdfd535e151c06cdc56536e9edb8a6fa11b`
- recovery-summary fingerprint: `fd1b1b27c59dd8a17d996efe4516098bfbe43270f9fa8e2889c1ec907f02a60d`
- 29 / 40 frozen identities panel-ready
- 81 / 92 cards recovered
- 7,785 exact NM history rows
- 7,950 provider credits used during recovery
- no provider calls during this estimator fit

## Fit

- cards: 63
- matched identities: 28
- Sets: 6
- Set-specific Treatment coefficients: 9
- Artist-covered cards: 40
- Playability-covered cards: 12
- PURE_TREATMENT condition number: 682.0548
- early/late coefficient Spearman: 0.98333
- passing Set/family groups: 0
- era-supported families: none

## Set-specific results

| Set / family / Treatment | Package log | Pure log | Sign stability | Max leave-identity influence | Temporal sign | Supported |
|---|---:|---:|---:|---:|---|---|
| Paldea Evolved / IR↔Uncommon / IR | 5.3133 | 0.7252 | 0.553 | 4.0880 | same | No |
| Paradox Rift / DR↔UR / UR | 1.1982 | -0.7625 | 0.600 | 1.8223 | same | No |
| SV151 / DR↔SIR↔UR / SIR | 3.8134 | 2.6938 | 0.936 | 1.0405 | same | No |
| SV151 / DR↔SIR↔UR / UR | 1.8459 | 0.3683 | 0.580 | 1.3734 | same | No |
| Shrouded Fable / Common↔IR / IR | 5.9392 | 1.3073 | 0.591 | 4.3051 | same | No |
| Surging Sparks / DR↔SIR↔UR / SIR | 3.3958 | 0.0288 | 0.516 | 3.1294 | changed | No |
| Surging Sparks / DR↔SIR↔UR / UR | 1.1382 | -0.5165 | 0.573 | 1.5380 | same | No |
| Surging Sparks / DR↔UR / UR | 0.9453 | -0.7229 | 0.605 | 1.5505 | same | No |
| White Flare / Common↔IR / IR | 4.8623 | -1.8973 | 0.573 | 6.2826 | same | No |

## Interpretation

The five-identity evidence expansion preserved very strong temporal ordering, but it did not make the global-scarcity PURE_TREATMENT coefficients robust to matched-identity composition. No Set/family met the preregistered complete support gates.

This is a valid negative result for the V3 design. It does not establish that Treatment has no independent collector effect because V3 still shares one global scarcity slope across Sets.

## Safety

Production writes: 0. Collector Appeal mutation: none. Overall RIP mutation: none.
