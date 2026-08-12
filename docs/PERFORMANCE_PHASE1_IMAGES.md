# Phase 1 — image/resource delivery

Phase 0's before-state is `PERFORMANCE_BASELINE.md` and is unchanged. This
document reports Phase 1 only: image and static-icon delivery. No RIP/Collector
Appeal/simulation/EV/market/pull-rate logic, API contract, cache policy for data
APIs, tab architecture, routing, SEO, auth, bundle split, layout, copy, card
count, card dimensions, colour or breakpoint was touched.

## Environment and method

- Audited commit: `207795f8c887cab3dc330347eff4e6ba390418ff` (`main`), plus the
  uncommitted Phase 0 tooling (`@next/bundle-analyzer`, `PERF_AUDIT_DIST_DIR`,
  `.next-perf` ignore). That tooling was preserved.
- Node 22.13.1, Next 15.5.15, Lighthouse 12.8.2, Microsoft Edge via Chromium
  DevTools, repository FastAPI backend on `127.0.0.1:8000`.
- Both builds are `next build` + `next start` into isolated dist directories,
  never `next dev`. Before-state on port 4175, after-state on 4174.
- **The Phase 0 numbers here are NOT the numbers in `PERFORMANCE_BASELINE.md`.**
  The baseline was a single cold run per route; this phase rebuilt the audited
  commit from scratch and re-measured it **3x per route** with the same harness,
  same machine and same backend as the after-state. Comparing Phase 1 against
  the baseline document's single runs would attribute run-to-run variance to the
  change. Every before/after pair below is 3 runs vs 3 runs.
- Reported as `median [min-max]`.
- Before each measurement set the route list was walked once to warm the server.
  Phase 0's raw PNGs came from Cloudflare's warm edge cache; Phase 1's optimized
  variants come from a warm `/_next/image` disk cache. This equalises the two,
  and is the steady state in production; a cold optimizer cache pays a one-time
  transform per variant.

## 1. What the LCP element actually is

The baseline established that image bytes dominate transfer. It did not
establish that any particular image is the LCP element, so that was measured
directly before changing hero images — via Lighthouse's
`largest-contentful-paint-element` audit and, where Lighthouse reports
`notApplicable` (the LCP candidate is detached before collection), via the raw
`largest-contentful-paint` PerformanceObserver entry.

### Phase 0 (before)

| Route | LCP DOM element | Resource | Transfer | Load start → end | Loading |
| --- | --- | --- | ---: | --- | --- |
| `/` | `<img class="rankingTheater_packImage…">` booster pack | `/_next/image?url=/images/pokemon/booster-packs/perfectOrder.webp&w=1080&q=75` | 39.7 kB WebP | 2,748 ms (observer) | eager, not priority |
| `/Research` | `<p>` (Overall RIP explainer) | none — text | n/a | 2,264 ms | n/a |
| `/TCGs/Pokemon/Sets` | `<img aria-hidden>` decorative set-logo wash | `https://images.scrydex.com/pokemon/me4-logo/logo` | 22.1 kB | 2,040 → 4,005 ms | `lazy` |
| set RIP | `<h1>` "#17 Modern Set to Rip Right Now" | none — text | n/a | 416 ms | n/a |
| set Cards | `<p>` "Pulling the checklist page…" (loading state) | none — text | n/a | 352 ms | n/a |

### Phase 1 (after)

| Route | LCP DOM element | Resource | Loading |
| --- | --- | --- | --- |
| `/` | same booster-pack `<img>` | same `/_next/image` URL | unchanged |
| `/Research` | `<p>` | none — text | n/a |
| `/TCGs/Pokemon/Sets` | same decorative wash `<img>` | `/_next/image?url=…scrydex…&w=640&q=75` | `lazy` |
| set RIP | `<h1>` | none — text | n/a |
| set Cards | `<p>` loading state | none — text | n/a |

**Three findings that shaped this phase:**

1. **`/inDex.png` was never the LCP element on any sampled route.** It was
   1.74 MB of connection contention on every route, which is worth removing on
   its own, but removing it is a transfer fix, not an LCP-element fix.
2. **Card images are not the LCP on the Cards route.** The LCP there is the
   loading-state paragraph. So card-image work in this phase is justified by
   transfer bytes, not by LCP.
3. **The Sets catalog LCP *is* an image** — and it is the faint decorative wash,
   not the visible logo. It is `loading="lazy"`. Its loading policy was left
   alone deliberately: it is one of ~19 identical decorative images, marking
   them all eager would starve real content, and after the byte reduction it is
   no longer the network bottleneck it was (2.0 s of transfer time in Phase 0).

## 2. Why `/inDex.png` was requested globally

`frontend/app/layout.js` pointed **all three** icon slots at the master artwork:

```js
icons: {
  icon:     [{ url: "/inDex.png", type: "image/png" }],
  shortcut: ["/inDex.png"],
  apple:    [{ url: "/inDex.png", type: "image/png" }],
}
```

That emitted `<link rel="shortcut icon">`, `<link rel="icon">` and
`<link rel="apple-touch-icon">` all pointing at a **2000×2000 RGBA PNG,
1,741,855 bytes on disk / 1,742,140 bytes transferred**. Browsers fetch
`rel="icon"` eagerly, so every route on the site paid it to paint a 16–32 px
glyph. This is inherited site-wide metadata, which is why it appeared on all
five sampled routes.

Two further defects found in the same audit:

- `public/favicon-180x180.png` was **byte-identical** to `public/inDex.png`
  (same md5, same 2000×2000 dimensions, same 1,741,855 bytes). Despite its name
  it was not 180×180 and nothing referenced it.
- `public/manifest.json` referenced `/favicon.ico` while the file on disk was
  **`favIcon.ico`**. Windows resolves that; Linux and Vercel do not, so the
  manifest icon was a production 404.

## 3. Icon files created / replaced

Generated from the same master by `frontend/scripts/generate_app_icons.py`
(Pillow, build-time only — deliberately **not** added to `package.json`). The
script does not re-crop: the master's transparent padding is part of how the
mark sits in a rounded app-icon tile, so it only resamples. Artwork,
proportions, crop, transparency and branding are unchanged.

| File | Action | Size |
| --- | --- | ---: |
| `public/favicon.ico` | replaced content; **renamed** from `favIcon.ico` | 252,380 B → 5,150 B (16/32/48 multi-res) |
| `public/favicon-32x32.png` | new | 1,627 B |
| `public/favicon-16x16.png` | new | 709 B |
| `public/apple-touch-icon.png` | new (replaces the mis-sized `favicon-180x180.png` role) | 18,269 B |
| `public/icon-192.png` | new (manifest) | 20,155 B |
| `public/icon-512.png` | new (manifest) | 109,250 B |
| `public/favicon-180x180.png` | **deleted** — unreferenced 1.74 MB duplicate of `inDex.png` | 1,741,855 B → 0 |
| `public/inDex.png` | kept, now unreferenced — it is the generation master | 1,741,855 B (0 requests) |

The `favIcon.ico` → `favicon.ico` rename was done as a real two-step `git mv`
so it is recorded as a rename on a case-insensitive filesystem; the manifest and
layout now both reference the lowercase name that actually exists. No duplicate
favicon files remain. `app/layout.js` and `public/manifest.json` were updated to
reference these assets and declare `sizes` so a browser picks one file instead
of fetching several to compare. No SEO title, description, canonical, `og:` or
`twitter:` field was touched.

Verified served from the production build:

```
/favicon.ico          200  5,150 B  image/x-icon
/favicon-32x32.png    200  1,627 B  image/png
/apple-touch-icon.png 200 18,269 B  image/png
/icon-192.png         200 20,155 B  image/png
/icon-512.png         200 109,250 B image/png
/manifest.json        200    756 B  application/json
```

## 4. Header logo — audited, deliberately left unchanged

`components/Header.js` already renders `/images/inDex.png` through `next/image`
with explicit `width`/`height`, `sizes` and `priority`. The network trace shows
it delivered as:

| | Before | After |
| --- | ---: | ---: |
| `/_next/image?url=/images/inDex.png&w=96&q=75` | 2,791 B WebP | 2,791 B WebP |
| `/_next/image?url=/images/inDex.png&w=256&q=75` | 7,439 B WebP | 7,439 B WebP |

It is already negotiated to WebP at the rendered width, is **not** the LCP
element on any sampled route, and costs 10 kB across both srcset candidates.
There was no measurable optimization penalty to fix, so its rendering behaviour,
its source, and its `priority` were all left exactly as they were. `priority`
was not removed: no evidence justified it.

(The 2000×2000 source is larger than needed, but the optimizer already caps
output at the rendered width and the delivered bytes are ~10 kB, so generating a
smaller source derivative would change bytes by roughly nothing while risking
visual parity. Not done.)

## 5. Card-image delivery strategy

**Option A (smaller upstream variant) was evaluated first and rejected on
evidence.** `images.pokemontcg.io` publishes exactly two variants per card:

```
https://images.pokemontcg.io/sv2/1.png        245x342   182,246 B
https://images.pokemontcg.io/sv2/1_hires.png  734x1024 1,183,347 B
```

Every call site already requests the smaller one (`imageSmallUrl` is preferred
over `imageLargeUrl` everywhere). There is no thumbnail variant left to ask for.
The 180–245 kB figure in the baseline **is** the small variant — those PNGs are
RGBA and simply encoded inefficiently for their pixel count.

**Option B (Next Image) was therefore chosen**, verified against the running
production build before committing to it:

| Source | Requested width | Result |
| --- | ---: | --- |
| `sv2/1.png` (182,246 B PNG) | `w=128` | 5,566 B WebP (−96.9%) |
| `sv2/1.png` | `w=256` | 15,824 B WebP (−91.3%) |
| `sv2/1.png` | `w=640` | 15,824 B — **identical**, confirming the optimizer never upscales |
| `sv2/logo.png` (113,089 B PNG) | `w=640` | 17,212 B WebP (−84.8%) |
| `scrydex me4-logo` (22,088 B) | `w=640` | 14,724 B WebP (−33.3%) |

Because the sources (245 px card art, ~451 px logos) are all smaller than the
widths requested, every delivered variant is *the source at its native
resolution, transcoded* — the saving is PNG→WebP, not discarded pixels. That is
why card text stays legible.

### How it was applied

Rather than migrate ~12 `<img>` call sites — each with its own wrapper,
`object-contain`/`object-cover`, absolute positioning and error-fallback state —
to `next/image` with `fill`/`sizes` and risk moving the layout, a small helper
builds the `/_next/image` URL those components would have requested anyway:

`frontend/lib/images/remoteImageDelivery.mjs`

- `optimizedImageUrl(src, width)` returns the optimizer URL, or **`src`
  unchanged** when the host is not configured, the protocol is not https, the
  value is relative/`data:`/malformed/empty. Nothing can 400 through the
  optimizer as a result of this change.
- Widths snap **up** to Next's configured buckets, so the optimizer never
  receives an unconfigured width.
- Quality is left at Next's default 75, so no `images.qualities` config is
  needed.

The elements, their classes and their rendered geometry are untouched — only the
URL changed. Covered by 5 unit tests, including one that asserts the helper's
host allowlist and `next.config.mjs`'s `remotePatterns` cannot drift apart.

### Width policy (one width per artwork role, deliberately)

A width is also a cache key, so two components painting the *same* artwork at
similar sizes must request the same width or one request becomes two.

| Constant | Value | Used for |
| --- | ---: | --- |
| `CARD_ART_WIDTH` | 256 | checklist grid tiles; top-hit / driver rows (68 CSS px at 2x) |
| `CARD_THUMBNAIL_WIDTH` | 128 | row, ticker and detail-strip thumbnails (≤64 CSS px) |
| `SET_LOGO_WIDTH` | 640 | every set-logo slot: catalog tile, catalog ambient wash, set hero, mobile hero, page atmosphere, homepage marks |

The Sets catalog's two roles (faint ambient wash + visible tile logo) share one
URL, exactly as they shared one raw URL before — the browser still makes a
single request per set and reuses it. The decorative ambient artwork was
preserved unchanged.

## 6. Image domains / config changes

`frontend/next.config.mjs` gained only:

```js
images: {
  remotePatterns: [
    { protocol: "https", hostname: "images.pokemontcg.io" },
    { protocol: "https", hostname: "images.scrydex.com" },
  ],
}
```

Exactly the two hosts that serve set/card artwork today — no wildcard, no
`**`, no arbitrary external host. `/_next/image` is a fetch-and-transform
endpoint, so each entry is a host this origin will proxy on request. The Phase 0
tooling (`PERF_AUDIT_DIST_DIR`, bundle analyzer) was left in place.

No signed or protected URLs are involved: both hosts serve unauthenticated
public artwork with `cache-control: public, max-age=31536000`.

## 7. Required before/after image table

| Resource / category | Before | After | Reduction |
| --- | ---: | ---: | ---: |
| Global icon/favicon request (every route) | 1,742,140 B | 5,497 B | **−99.68%** |
| Header logo delivered bytes (w=256 + w=96) | 10,230 B | 10,230 B | 0% (intentionally unchanged) |
| Typical card image (median, Cards mobile) | 176,309 B | 16,022 B | **−90.9%** |
| Cards total image bytes — mobile | 5.08 MB | 0.32 MB | **−93.6%** |
| Cards total image bytes — desktop | 9.96 MB | 0.74 MB | **−92.5%** |
| Sets catalog image bytes — mobile | 2.95 MB | 0.26 MB | **−91.0%** |
| Typical set logo (median, Sets catalog) | 87,177 B | 17,562 B | **−79.9%** |

### Dimensions, format and cache behaviour

| Category | Source dims | Delivered dims | Rendered CSS | Format before → after | Cache |
| --- | --- | --- | --- | --- | --- |
| Global icon | 2000×2000 | 48/32/16 (ico) | 16–32 px | PNG → ICO | static, immutable filename |
| Apple touch icon | 2000×2000 | 180×180 | 180 px | PNG → PNG | static |
| Manifest icons | 2000×2000 | 192, 512 | per-OS | PNG → PNG | static |
| Card grid art | 245×342 | 245×342 (w=256, no upscale) | ~185 px wide mobile / ~230 px desktop | PNG → WebP | `public, max-age=31536000, must-revalidate` |
| Card thumbnails | 245×342 | 128 wide | 28–64 px | PNG → WebP | same |
| Set logos | 451×147 | 451×147 (w=640, no upscale) | 24–288 px | PNG → WebP | same |
| Header logo | 2000×2000 | 256 / 96 | 50–56 px | WebP → WebP (unchanged) | unchanged |

Cacheability was not weakened. The upstream `public, max-age=31536000` is
preserved and `/_next/image` adds `must-revalidate`. Optimizer URLs are
deterministic — no per-render query-string cache busting — so a given artwork
at a given width is one stable cache entry across routes and viewports.

## 8. Required route comparison

3 Lighthouse runs per route/device, both phases, `median [min-max]`.

| Route | Device | Phase 0 LCP | Phase 1 median LCP | Transfer before | Transfer after | CLS before | CLS after |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `/` | Mobile | 5,858 [2,934–6,310] | **2,957 [2,448–4,145]** | 2.49 MB | **0.48 MB** | 0.000 | 0.000 |
| `/Research` | Mobile | 2,012 [2,004–2,014] | 1,981 [1,959–2,005] *(inconclusive)* | 1.95 MB | **0.21 MB** | 0.0005 | 0.0005 |
| `/TCGs/Pokemon/Sets` | Mobile | 4,030 [4,002–4,060] | **3,298 [3,263–3,391]** | 3.28 MB | **0.60 MB** | 0.000 | 0.000 |
| set RIP | Mobile | 2,344 [2,298–3,393] | 2,121 [2,107–2,157] *(inconclusive)* | 4.15 MB | **1.61 MB** | 0.0001 | 0.0001 |
| set Cards | Mobile | 6,213 [6,200–6,214] | 6,126 [6,116–6,424] *(inconclusive)* | 6.01 MB | **1.34 MB** | **0.1150** | **0.1150** |
| set Cards | Desktop | 2,484 [1,137–2,551] | **1,091 [1,060–1,091]** | 10.89 MB | **1.77 MB** | 0.0380 | 0.0380 |
| set RIP | Desktop | 2,484 [2,464–2,486] | **1,081 [1,079–1,083]** | 3.96 MB | **1.61 MB** | 0.0097 | 0.0097 |

Honest reading of the LCP column:

- **Real, non-overlapping improvements:** both desktop routes (−56%), mobile
  home (−49.5%, though the Phase 0 range is wide), Sets catalog (−18.2%, ranges
  do not overlap).
- **Inconclusive:** Research (−1.6%), set Cards mobile (−1.4%) — the ranges
  overlap and the differences are inside run noise. Set RIP mobile (−9.5%) has
  a tighter after-range but the before-range overlaps it; treat as suggestive,
  not proven.
- This is the expected shape given section 1: LCP only moved materially where
  the LCP was image-backed or where image contention was starving the paint.
  On the three text-LCP mobile routes, removing image bytes did not move LCP.

Secondary metrics (medians): FCP is flat or slightly better everywhere
(set Cards mobile −9.8%, set RIP mobile −8.7%). TBT is noisy in both phases and
moves both ways (set RIP mobile −18.2%, Sets −19.2%, Research −17.4%; home
+22.9%, set Cards mobile +25.7%). **No TBT claim is made** — this phase changed
no JavaScript, the ranges overlap heavily, and TBT is Phase 2's concern.
Request counts are unchanged (±2 requests, within noise).

## 9. Cards CLS — measured cause contradicts the baseline hypothesis

Cards mobile CLS is **0.1150 before and 0.1150 after** — identical to four
decimal places across all six runs. It did not improve, and the target of
<0.10 was **not met**. That is not a measurement gap; the cause was identified:

```
layout-shifts audit, mobile set Cards:
  0.1149515 — div.min-w-0
             (div.dashboard-container > section#set-detail-cards > div.min-w-0)
             boundingRect height 10,351 px
  0.0021839 — web font load
```

The single dominant shift is `SetTabLoadingPanel` (a short branded loader) being
replaced by the full 10,351 px card grid. It is a loading-state height problem,
not an image-geometry problem:

- The card tiles **already** reserve their geometry — `aspect-[3/4] w-full` on
  the image box, with `CardImagePlaceholder` filling it before the image lands.
  The image slot already occupies its final dimensions immediately.
- The baseline's "unsized set logo is a layout-shift risk" hypothesis is not
  supported by measurement: every set-logo `<img>` sits inside a fixed-size
  wrapper (`h-20`, `h-9 w-14`, `h-14 w-24`, `h-72 w-72`) with `object-contain`,
  so the wrapper reserves the box and the missing intrinsic attributes shift
  nothing. Measured CLS is 0.000 on Sets and 0.0001 on set RIP, before and
  after.

Fixing the real cause means giving the Cards loading state a reserved height
approximating the grid — a change to layout composition and loading behaviour,
which section 2 puts out of scope for this phase and section 21 says to stop and
report rather than force. **Recommended for the phase that owns the set client**,
alongside the tab-boundary work.

Desktop Cards CLS (0.0380) and set RIP CLS (0.0097) are likewise unchanged.

## 10. No new waterfalls, duplicates or errors

Playwright network audit, 7 routes × 2 device profiles, both builds:

| Route | Device | Image reqs before | after | Raw remote before | after | Failed | Redirects | Dup variants | Console errors |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `/` | mobile | 8 | 8 | 5 | 0 | 0 | 0 | 0 | 0 |
| `/Rankings` | mobile | 7 | 7 | 5 | 0 | 0 | 0 | 0 | 0 |
| Sets catalog | mobile | 9 | 9 | 7 | 0 | 0 | 0 | 0 | 0 |
| set RIP | mobile | 3 | 3 | 1 | 0 | 0 | 0 | 0 | 0 |
| set Market | mobile | 9 | 9 | 7 | 0 | 0 | 0 | 0 | 0 |
| set Cards | mobile | 13 | 13 | 11 | 0 | 0 | 0 | 0 | 0 |
| set Pull Rates | mobile | 3 | 3 | 1 | 0 | 0 | 0 | 0 | 0 |
| `/` | desktop | 8 | 8 | 5 | 0 | 0 | 0 | 0 | 0 |
| `/Rankings` | desktop | 25 | 25 | 22 | 0 | 0 | 0 | 0 | 0 |
| Sets catalog | desktop | 24 | 24 | 22 | 0 | 0 | 0 | 0 | 0 |
| set RIP | desktop | 6 | 6 | 4 | 0 | 0 | 0 | 0 | 0 |
| set Market | desktop | 19 | 19 | 17 | 0 | 0 | 0 | 0 | 0 |
| set Cards | desktop | 23 | 23 | 21 | 0 | 0 | 0 | 0 | 0 |
| set Pull Rates | desktop | 3 | 3 | 1 | 0 | 0 | 0 | 0 | 0 |

Image request counts are **identical on every route in both profiles**. No image
became two requests, no original-plus-transformed pair, no redirect chain, no
failed `/_next/image`, no remote-host permission error, no console error.

This audit is also what caught the last gap: the homepage's
`RankingTheaterHomepage` set marks were a separate `<img>` path that still
fetched 5 raw remote logos after the first pass. Converted; raw remote image
fetches are now 0 across all 14 route/device combinations.

One intermittent console 500 was observed on the Cards route (2 of 3 renders
were clean with 60 card images and 0 failed images; the third failed to load the
cards data payload). It is a backend/data-provider flake, not an image request —
`failed` images was 0 in every case — and it reproduces on the baseline build.

## 11. Visual fidelity

Before/after screenshots at 1440×900 desktop and Pixel 5 mobile for Homepage,
Rankings, Sets catalog, set RIP, set Market, set Cards and set Pull Rates.
Per-pixel difference (channel delta > 12 counted as changed):

| Screenshot | Changed px | Mean delta |
| --- | ---: | ---: |
| desktop home | 0.06% | 0.04 |
| desktop rankings | 0.01% | 0.00 |
| desktop sets | 0.51% | 0.14 |
| desktop set RIP | 0.15% | 0.07 |
| desktop set Market | 0.00% | 0.04 |
| desktop set Cards | 6.26% | 1.51 |
| desktop set Pull Rates | 0.04% | 0.05 |
| mobile home | 0.02% | 0.02 |
| mobile rankings | 0.01% | 0.01 |
| mobile sets | 1.55% | 0.32 |
| mobile set RIP | 0.03% | 0.01 |
| mobile set Market | 0.03% | 0.01 |
| mobile set Cards | 1.73% | 0.40 |
| mobile set Pull Rates | 0.03% | 0.01 |

Desktop Cards is the largest figure because card art covers most of the
viewport, so WebP's sub-threshold differences are spread over a large area — the
mean delta of 1.51/255 is well under a perceptible step. Side-by-side inspection
of the desktop Cards pair confirms identical layout, identical card dimensions
and spacing, identical crop, identical set logo and background wash, and card
text (HP, attack names, ability text, flavour text, set/number line) legible in
both. No aspect-ratio distortion, no missing images, no background-colour
change, no compression artefacts, no transparency loss on set logos.

## 12. Build and tests

- `npm run build`: **passed**. Set detail first-load JS is still **392 kB** and
  shared first-load JS still **102 kB** — unchanged, confirming no Phase 2
  bundle work leaked in.
- `npm run test:frontend`:

| | Tests | Pass | Fail |
| --- | ---: | ---: | ---: |
| Before (session start, audited commit) | 1,451 | 1,359 | 92 |
| After Phase 1 implementation | 1,456 | 1,364 | **92** |
| Final run | 1,467 | 1,371 | 96 |

The middle row is the like-for-like comparison: **+5 tests (the new helper's
own), +5 passing, and the failing set byte-identical to the 92-name baseline —
zero new failures.**

The final run's extra 11 tests / 4 failures come from
`components/explore/SetTabRequestGating.contract.test.mjs`, an **untracked file
that appeared in the working tree during this session and was not created by
this work**. It asserts value-history fetch gating (Phase 2/3 scope) that does
not exist yet. Verified not attributable to Phase 1: with
`RipStatisticsPageClient.jsx` reverted to the unmodified audited-commit source,
the same 4 tests fail identically (11 tests, 7 pass, 4 fail).

The 92 pre-existing failures were not investigated or rewritten, and no existing
assertion was weakened.

## 13. Success criteria

| Target | Result |
| --- | --- |
| Global icon −90% or better | **Met — −99.68%** (1,742,140 B → 5,497 B) |
| Cards image bytes −50% or better, same card count, same artwork quality | **Met — −93.6% mobile, −92.5% desktop**, still 60 cards, no visible quality change |
| Cards mobile CLS < 0.10 | **Not met — 0.1150 unchanged.** Root cause measured and is a loading-state height issue, not image geometry (§9) |
| Materially reduce cold mobile LCP on image-dominated routes | **Partly met.** Real on Sets (−18.2%) and mobile home (−49.5%); both desktop routes −56%. Inconclusive on Research and Cards mobile, where the LCP is text |

## 14. Files changed

```
frontend/app/layout.js                                    icon metadata only
frontend/app/TCGs/Pokemon/Sets/page.js                    one shared optimized logo URL
frontend/components/explore/RipStatisticsPageClient.jsx   image URLs only (11 sites)
frontend/components/explore/SetIdentity.jsx               set logo URL
frontend/components/explore/ExploreTopRankings.jsx        set logo URL
frontend/components/explore/RipDecisionPage.jsx           chase card thumbnail URL
frontend/components/explore/SevenDayMarketMoversTicker.jsx ticker thumbnail URL
frontend/components/landing/previews/RemoteImg.jsx        optimizeWidth prop
frontend/components/landing/HeroBoosterPackBackdrop.jsx   passes SET_LOGO_WIDTH
frontend/components/landing/RankingTheaterHomepage.jsx    set mark URL
frontend/lib/images/remoteImageDelivery.mjs               new — URL builder
frontend/lib/images/remoteImageDelivery.test.mjs          new — 5 tests
frontend/next.config.mjs                                  images.remotePatterns
frontend/public/manifest.json                             icon entries
frontend/scripts/generate_app_icons.py                    new — build-time generator
frontend/public/favIcon.ico → favicon.ico                 renamed + regenerated
frontend/public/favicon-{16x16,32x32}.png                 new
frontend/public/apple-touch-icon.png                      new
frontend/public/icon-{192,512}.png                        new
frontend/public/favicon-180x180.png                       deleted (1.74 MB duplicate)
```

`RipStatisticsPageClient.jsx` received image-URL changes only. No hook warnings
were fixed, no components split, no fetching refactored, no unrelated cleanup.

## 15. Intentionally left unchanged

- **Header logo rendering, source and `priority`** — already efficiently
  delivered, not the LCP anywhere (§4).
- **Sets catalog decorative wash `loading="lazy"`** — it is the LCP there, but
  making one of ~19 decorative images eager needs to target only the first tile
  and would compete with real content; left for a follow-up with its own
  evidence.
- **Cards loading-state height** — the actual CLS cause, out of scope (§9).
- **`app/head.js`**, which preloads `/images/inDex.png` as an image. This is a
  Pages-Router convention that App Router does not execute; the network trace
  confirms no such request is made in either build. It currently costs 0 bytes,
  so it was left alone rather than cleaned up in this phase — but it is a latent
  874 kB preload if that file ever becomes live, and worth deleting separately.
- **`public/inDex.png`** — kept as the icon generation master; now 0 requests.
- **Local booster-pack assets** (3–6 MB JPG/WebP sources) — already served
  through `next/image` and delivered at 39.7 kB on the homepage.
- **`PageArtworkAtmosphere`** — its source is a local SVG, not a remote raster.
- **The 92 pre-existing test failures.**
- **Phase 0 tooling** — analyzer, `ANALYZE`, `PERF_AUDIT_DIST_DIR`,
  `.next-perf` ignore all preserved.

## 16. Notes for the next phase

Phase 1 removed image bytes as the dominant transfer cost: Cards mobile went
6.01 → 1.34 MB and desktop 10.89 → 1.77 MB. What remains on those routes is
**JavaScript and API payloads**, not images. Two observations relevant to the
Phase 2-vs-Phase 3 decision, offered as data rather than recommendation:

- Cards mobile LCP is now gated on the **loading-state paragraph**, i.e. on how
  long the cards payload takes to arrive and hydrate — an API/JS characteristic.
- Cards mobile CLS 0.1150 is caused by the loading-state → grid swap, which the
  set-client/tab-boundary work would naturally touch.

Neither was acted on here.
