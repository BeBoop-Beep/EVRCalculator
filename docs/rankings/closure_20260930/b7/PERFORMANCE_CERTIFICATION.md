# Performance certification

## Production build

With the repository-documented local backend URL supplied to both build variables, `npm.cmd run build` completed all phases using Next.js 15.5.15 and isolated output `.next-build-1116`:

- compile: 13.9 s;
- lint/type phase: complete, with existing non-fatal hook, image, and accessibility warnings;
- static generation: 85/85 pages;
- `/Rankings`: 132 B route size and 115 kB First Load JS;
- shared First Load JS: 104 kB.

The backend URL is legitimate repository configuration (`http://127.0.0.1:8001`), but no configured backend could be started without Supabase credentials. Build-time fallbacks completed normally; this is a full build PASS, not live-data proof.

## Controlled anonymous browser samples

Production server: `next start -p 3107`, using `.next-build-1116`. Network data was supplied by maintained sanitized public fixture routes. Each number below is one browser sample, so no p50/p95 is claimed.

| Viewport | Initial page sample | Products intent → Scores | First Economics | Warm Scores | Warm Economics |
|---|---:|---:|---:|---:|---:|
| Desktop 1440×1000 | 1,038 ms | 843 ms | 26 ms | 35 ms | 36 ms |
| Mobile 390×844 | 1,051 ms | 847 ms | 27 ms | 34 ms | 31 ms |

The first Product sample includes lazy lens loading and a 342-byte Product catalogue response. Warm switching reuses the public catalogue; it does not represent paid Scores/Economics endpoint latency. Era and Set headline responses were 240 and 335 bytes respectively. The 43,629-byte production document was also inspected.

## Blocked measurements

- Paid Product cold/warm endpoint timing: BLOCKED_RUNTIME (no approved paid session/backing service).
- Cards Overall/Pokémon/Trainer/Artist/Playability and warm return: BLOCKED_RUNTIME.
- Graph initial/add/remove/Overall-only/window switch: BLOCKED_RUNTIME.
- Proxy/backend/DB duration, query count, cache hit/miss, and DB plans: BLOCKED_RUNTIME.

Historical fixture/unit measurements remain supporting evidence only: focused B1–B6 suite 70 tests; maintained Rankings suite 341 passing; backend credential-free SQL contracts 14 passing.
