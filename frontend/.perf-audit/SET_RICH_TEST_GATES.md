# Pokemon Set regression gates

`baselines/set-rich/` is the historical August 30, 2026 live-data baseline. It is retained unchanged as audit evidence and is not the active regression authority.

`baselines/set-rich-fixture-v1/` is the active deterministic visual authority. Its raw public inputs live in `fixtures/set-rich-v1/`. Run `npm run perf:set-visual`; the runner builds against and starts a strict local playback backend, starts a production Next server, verifies the complete 24-case matrix, and fails on unknown or unused critical fixtures.

The performance-refactor gate is the conjunction of:

1. Deterministic fixture visual parity: 24/24.
2. Current backend health: `npm run perf:set-live-contract` passes.
3. Current browser runtime health: start the production server against the live backend and run `npm run perf:set-live-smoke`.

Daily prices, dates, membership, and data-driven Cards/Sealed availability belong to the live contract. They do not alter the frozen visual authority.

## Data paths covered

| Consumer | Method and backend path | Execution | Visual cases |
|---|---|---|---|
| Route identity | `GET /tcgs/pokemon/set-route-directory?limit=150` | Next SSR | All 24 |
| Set shell | `GET /tcgs/pokemon/sets/{uuid}/shell` | Next SSR | All 24 |
| RIP bootstrap | `GET /tcgs/pokemon/sets/{uuid}/rip/bootstrap` | Next SSR | RIP |
| Market bootstrap/Set Value | `GET /tcgs/pokemon/sets/{uuid}/market/bootstrap?window=365d` | Next SSR and same-origin proxy | Market |
| Market movers | `GET /tcgs/pokemon/sets/{uuid}/market/movers` with the manifest query | Next SSR | Market |
| Top Chase | `GET /tcgs/pokemon/sets/{uuid}/market/top-chase` with `window=365d`, `limit=10`, `snapshot_contract=pricing-v4` | Browser through Next proxy | Market |
| Sealed summary/detail | `GET .../market/sealed-summary` and `GET .../market/sealed-consumer` | Browser through Next proxy | Market |
| Cards | `GET .../cards/page` with page, sorting, section, movement, and snapshot parameters | Browser through Next proxy | Cards |
| Pull Rates | `GET .../pull-rates` | Browser through Next proxy | Pull Rates |

Market signals are authenticated and fail closed for the anonymous visual audit; the public locked presentation is covered without recording credentials. RIP advanced/simulation/rank-context requests are not needed by the canonical public first-paint scenario. Image delivery remains external but all images are masked by the parity screenshot contract.

The backend target is supplied through the existing `BACKEND_API_BASE_URL` and `NEXT_PUBLIC_BACKEND_API_BASE_URL` configuration. No production fixture branch or UI test switch exists.
