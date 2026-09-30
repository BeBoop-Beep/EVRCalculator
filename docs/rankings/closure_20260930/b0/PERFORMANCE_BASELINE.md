# Rankings Bucket 0 performance baseline

## Controlled setup

- Source: `80ed964161a3600d900624da6155a63b91962d74`.
- Build command: `npm.cmd run build` in `frontend`.
- Production output: isolated `.next-build-31956`.
- Server: `next start`, local port 3310, with that exact dist directory.
- Browser: Playwright 1.62.1, installed headless Chromium, fresh context per run.
- No `next dev` measurements are used.

## Measured navigation

| Run | HTTP | TTFB | DOMContentLoaded | load | document transfer | decoded document |
|---|---:|---:|---:|---:|---:|---:|
| Cold new browser context | 200 | 14.6ms | 216.1ms | 226.6ms | 19,901 B | 89,049 B |
| Second new context, warm server | 200 | 11.8ms | 155.7ms | 165.7ms | 19,901 B | 89,049 B |

The build compile phase took 4.1 minutes before lint/type/page generation. This is build throughput evidence, not end-user latency.

## Anonymous interaction/gate observations

Captured click wall times included an intentional 100ms post-click stabilization wait, so they are not pure React render durations. Cold: Era 172.6ms, Set 154.2ms, Product 151.2ms, Cards 140.8ms, Overview 139.5ms. Second context: 157.4ms, 128.6ms, 141.7ms, 153.1ms, 154.6ms respectively. Era/Set rendered locks; Product/Card paid data did not load anonymously.

## Layer findings

| Layer | Evidence | Conclusion |
|---|---|---|
| Module load | Lens modules are dynamic. Era is idle-warmed first; Sets next. Products/Cards are only intent-loaded. | First paid interaction may include chunk load; paid measurements blocked. |
| Frontend session cache | Identity is `${user identity}:${accessMode}`; Product views are separate 60s keys; Card keys include lens/query. | Cache design separates cold/warm and auth identities. One stale regex test is red, but behavioral cache tests pass. |
| Proxy | Anonymous 401s were 3.2–58.8ms in the two-probe sample. | Gate overhead is small after first Set proxy touch; this does not measure entitled payloads. |
| Backend | Source shows Product authority cached 60s; economics adds an exact Best-Open read. Card queries are page-first. | Plausible warm improvement exists; not certified without paid requests. |
| DB | Bounded live reads completed; the full `read_pack_economics` service call completed within a 27.1s combined audit command that also ran artwork counts and scorecards. | Do not attribute that combined wall time to one query. No per-endpoint DB timing was isolated. |
| Payload | Anonymous document 19,901 B transferred / 89,049 B decoded. | Valid anonymous baseline only. Paid row payload sizes blocked. |
| Browser render | Anonymous navigation measured above. | Product/Card paid rendering and rapid switches blocked. |

Historical measurements in `docs/PERFORMANCE_BASELINE.md` and `docs/PERFORMANCE_BROWSER_RANKINGS_HOME_MARKET.md` were reviewed for method and context only. They are not presented as this audit's baseline.

## Certification status

Anonymous production-build navigation is measured. Product economics switching, Card component switching, login-without-refresh, and logout/access-loss are `BROWSER_BLOCKED`; no performance PASS is claimed for them.
