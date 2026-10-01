# Rankings business-review follow-up

Implemented on `fix/rankings-business-review-followup-20261001` from `origin/develop` at `34713809dab4100a61f80fb957d8fb461f106cf0`.

## Delivered contract

- Product intent and idle prewarming share the session cache and keep public and entitled reads separate.
- Full Market Product Scores and Economics require Index Premium. A supported family requires Index Plus. Both API paths enforce the same scope rule.
- The public Product catalogue is projected from the current ranked authority, so unsupported or unrankable inventory is not disclosed.
- Set and Era score cells retain their numeric score and now expose canonical rank and percentile tier. Collector and Chase are explicitly cohort-relative 0–10 presentation values; their tiers come from canonical rank percentiles and they have no universal 5.0 reference.
- Era Collector and Chase values are equal-Set aggregates of the Set presentation values. This is presentation only and does not alter a published model, rank, or tier.
- The reference row remains 5.0 only for Overall and Financial. Collector and Chase show an explained em dash.
- Pack Economics uses `Packs`; Set parents say `Varies`, while expanded exact Products show their pack counts.
- History controls add 1D and 7D, Era preset selection is single-valued, and the permanent Overall line/key is white and dashed.

No migration, index, publication, deployment, production write, or model recalculation was performed.

## Verification

- Focused frontend contract/model suite: 49 tests.
- Focused backend service/relative-score suite: 93 tests.
- Production build: run with a non-production local backend URL; repository-wide pre-existing lint warnings are reported separately from build success.
- Browser smoke used the prescribed `agent-browser` CLI immediately after starting the local Next development server. The anonymous shell loaded, but live data requests could not complete because no local backend fixture was available at the configured URL; no production backend was contacted.

## Performance interpretation

Development-mode first navigation includes Next compilation and is not a production latency measurement. Warm client navigation benefits from chunk intent preloading and the shared request cache. API/backend latency remains separately observable from browser compilation and render time; no production timing claim is made from the local dev run.
