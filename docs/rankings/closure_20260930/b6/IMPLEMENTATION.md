# Bucket 6 implementation

Starting authority: `d7021e4484e0c302759b25a1eee118f637febc38` on the isolated B6 branch.

## Changes

- Removed the decorative Cards selector surface while retaining the Collector/Chase segmented control.
- Added an explicit resolving-access status. A resolving session no longer renders a premature lock, empty state, or request error.
- On entitlement loss, Collector and Chase now invalidate request generations and clear paid rows, facets, and facet errors immediately.
- Row requests use per-mounted-view generations. Cleanup plus generation checks prevents late query or old-session responses from committing.
- Row failures expose local Retry. A same-query refresh failure retains last-good rows and labels them truthfully. Collector facet failure remains independent and has its own retry.
- Lens/filter/page actions set loading state immediately. Filter/page transitions clear old-query rows; a lens may retain only its own keyed last-good state.
- Cache identity remains the existing `user/access:publication` identity from `useRankingsAccess` and `RankingsLazyClient`; canonical Card keys include lens and all sorted query parameters. No extra cache layer was added.

No backend ranking, model, publication, access expansion, or Product score semantics changed.

## Best-supported login diagnosis

The hard-refresh symptom was not reproducible against a live authenticated session. Source inspection showed that identity-scoped remounting and cookie forwarding already exist. The concrete state-model gaps were premature locked rendering during auth resolution, no explicit paid-state purge inside Collector, and no local recovery after a transient request failure. B6 fixes those gaps and proves the anonymous/denied-to-entitled identity transition contract with deterministic source/cache tests. This is a supported diagnosis, not a claim that a live proxy/backend bottleneck was measured.

## Backend inspection

Collector remains page-first. The component RPC ranks the global eligible component cohort before display filters. Only current-page card IDs and Set IDs are enriched. Reads for cards, component scores, Sets, and Eras are bounded but serial. Without live timings, changing concurrency/client behavior was not justified.
