# Branch reconciliation

- Current `origin/develop`: `36b8a03462008364cb66c889f1146a8e2720805c`
- Current `origin/main`: `9d9d888c2c4702c23f174e950ec5a6aaf45322a7`
- Historical Rankings baseline: `80ed964161a3600d900624da6155a63b91962d74`
- Merge-base of develop with both the historical baseline and B6: `80ed964161a3600d900624da6155a63b91962d74`

Develop adds four commits after the baseline: `2a2c9346`, `8534b9d8`, `0a657080`, and merge `36b8a034`. They are Market Explorer work affecting 21 paths. The B0â€“B6 delta affects 76 paths. The path intersection is empty.

The pre-Rankings commits `075d4a2f` (sealed constituent long-window authority) and `80ed9641` (Market Explorer backend access transport) are `ALREADY_IN_DEVELOP`. No local-only dependency was imported. The four newer develop commits are `UNRELATED` to Rankings and were preserved.

B0â€“B6 were applied sequentially as local commits `4f1d01a8`, `98ee0208`, `7e541de9`, `c0f3d7b6`, `d01d98e1`, `02e23ba5`, and `5682c683`. There were no textual conflicts and no ours/theirs resolution. Comparison against B6 showed only the 21 preserved Market Explorer paths; there were no Rankings-relevant differences before B7 test/doc work.
