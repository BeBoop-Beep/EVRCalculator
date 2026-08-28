import PokemonSetPageClient from "@/components/pokemon/set-page/PokemonSetPageClient";
import { getExplorePagePayload } from "@/lib/explore/explorePageServer";
import { getRipStatisticsTargets } from "@/lib/explore/ripStatisticsServer";
import { getPokemonSetInitialSnapshots } from "@/lib/pokemon/pokemonSetInitialSnapshotsServer";
import {
  buildTargetHrefById,
  buildTcgSetHrefFromTarget,
  findTargetBySetSlug,
  resolveSetDetailTab,
  toSetSlug,
} from "@/lib/explore/ripStatisticsRouting";
import { buildRouteMetadata } from "@/lib/seo/routeMetadata.mjs";
import { notFound, redirect } from "next/navigation";

const SETS_BASE_PATH = "/TCGs/Pokemon/Sets";

/**
 * SET CANONICAL POLICY
 * --------------------
 * The canonical identity of a set is its BARE path:
 *
 *     /TCGs/Pokemon/Sets/[setSlug]
 *
 * Every query variant of that path — `?tab=market`, `?tab=cards`,
 * `?tab=pull-rates`, `?section=…`, `?window=…`, `?card_sort=…`, `?movement=…`
 * — is presentation state for the same set, so all of them canonicalize to the
 * bare URL below. That keeps Market/Cards/Pull Rates fully functional as user
 * surfaces (nothing about them changes) while stopping them from forming an
 * uncontrolled family of near-duplicate indexable URLs. If any of those tabs
 * later earns its own stable path, that path can declare its own canonical.
 *
 * The pure aliases of the default view (`?tab=rip`, `?tab=analysis`,
 * `?tab=analytics`) are collapsed onto that bare URL with a 308 in
 * middleware.js — they are legacy spellings the app itself never writes, and
 * middleware is the only layer that can still set a status code here (see the
 * note in the page component below). `?tab=overview` is deliberately NOT
 * redirected: the client writes it on every RIP-tab click (see
 * `updateSetDetailQueryParams` in RipStatisticsPageClient), so redirecting it
 * would put a server round-trip in the middle of ordinary tab navigation. The
 * canonical tag already consolidates it.
 *
 * NOTHING HERE COMPUTES A SCORE. The set name is lifted verbatim from the same
 * canonical targets payload the page itself renders from.
 */
export async function generateMetadata({ params }) {
  const resolvedParams = (await params) || {};
  const rawSetSegment = String(resolvedParams?.setSlug || "").trim();
  const requestedSetSlug = toSetSlug(rawSetSegment);

  if (!requestedSetSlug) {
    return buildRouteMetadata({
      path: SETS_BASE_PATH,
      title: "Pokémon TCG Set Catalog — inDex",
      description:
        "Browse Pokémon TCG sets and open one for its Overall RIP and opening analysis.",
    });
  }

  // getRipStatisticsTargets is wrapped in React `cache()` AND a process-level
  // TTL cache, so this resolves from the same in-flight/cached payload the page
  // body below awaits. Metadata costs no extra backend request.
  const targetsPayload = await getRipStatisticsTargets({ limit: 150 }).catch(
    () => null,
  );
  const selectedTarget = findTargetBySetSlug(
      Array.isArray(targetsPayload?.targets) ? targetsPayload.targets : [],
      rawSetSegment,
    );
  const setName = String(selectedTarget?.name || "").trim();
  const canonicalPath = selectedTarget
    ? buildTcgSetHrefFromTarget(selectedTarget).split("?")[0]
    : `${SETS_BASE_PATH}/${encodeURIComponent(requestedSetSlug)}`;

  // Graceful failure: a set we cannot name still gets the RIGHT canonical URL
  // and an accurate generic title. A name is never invented from the slug.
  if (!setName) {
    return buildRouteMetadata({
      path: canonicalPath,
      title: "Pokémon Set Overall RIP & Opening Analysis — inDex",
      description:
        "Overall RIP, Financial RIP, Collector Appeal and modeled opening outcomes for this Pokémon set.",
    });
  }

  return buildRouteMetadata({
    path: canonicalPath,
    title: `${setName} Overall RIP, Expected Value & Opening Analysis — inDex`,
    description: `Is ${setName} worth ripping? See its Overall RIP, Financial RIP, Collector Appeal, expected value and modeled opening outcomes on inDex.`,
    ogTitle: `${setName} — Overall RIP & Opening Analysis`,
    ogDescription: `Overall RIP, Financial RIP, Collector Appeal and modeled pack outcomes for ${setName}.`,
  });
}

export default async function TcgSetRipStatisticsPage({
  params,
  searchParams,
}) {
  const routeStartedAt = Date.now();
  const resolvedParams = (await params) || {};
  const rawSetSegment = String(resolvedParams?.setSlug || "").trim();
  const requestedSetSlug = toSetSlug(rawSetSegment);
  const resolvedSearchParams = (await searchParams) || {};

  // NOTE: the legacy default-view tab aliases (?tab=rip|analysis|analytics) are
  // collapsed onto the bare canonical set URL by middleware.js, not here. This
  // route has a loading.js, so Next flushes the response shell before this
  // function runs — a redirect thrown from here arrives after the 200 is
  // committed and degrades to a client-side redirect, which is not a signal a
  // crawler can follow. resolveSetDetailTab still aliases them to `overview`
  // below so a direct render (or any request that bypasses middleware) is
  // correct rather than merely redirected.
  const activeSetDetailTab = resolveSetDetailTab(resolvedSearchParams?.tab);

  const targetsStartedAt = Date.now();
  const targetsPayload = await getRipStatisticsTargets({ limit: 150 }).catch(
    (error) => ({
      targets: [],
      default_target: null,
      meta: {
        fallback: true,
        requestFailed: true,
        warnings: [
          `RIP Statistics targets unavailable; continuing with direct set snapshot fallback. ${error?.message || ""}`.trim(),
        ],
      },
    }),
  );
  const targetsMs = Date.now() - targetsStartedAt;
  const targets = Array.isArray(targetsPayload?.targets)
    ? targetsPayload.targets
    : [];
  const defaultTarget = targetsPayload?.default_target || null;
  const targetHrefById = buildTargetHrefById(targets);

  if (!requestedSetSlug && defaultTarget?.target_type === "set") {
    redirect(buildTcgSetHrefFromTarget(defaultTarget));
  }

  const selectedTarget = findTargetBySetSlug(targets, rawSetSegment);
  if (selectedTarget) {
    const canonicalHref = buildTcgSetHrefFromTarget(selectedTarget, {
      tab: resolvedSearchParams?.tab,
      section: resolvedSearchParams?.section,
      window: resolvedSearchParams?.window,
    });
    const canonicalPath = canonicalHref.split("?")[0];
    const requestedPath = `${SETS_BASE_PATH}/${encodeURIComponent(rawSetSegment)}`;
    if (canonicalPath !== requestedPath) redirect(canonicalHref);
  }
  if (!selectedTarget) notFound();
  const requestedTargetType = selectedTarget?.target_type || "set";
  const requestedTargetId = selectedTarget?.target_id;
  const fallbackTarget = selectedTarget;
  const effectiveSelectedTarget = selectedTarget;

  let explorePayload = null;
  let pageError = null;
  let explorePagePayloadMs = null;
  let initialModuleSnapshots = {
    shellPayload: null,
    cardsPayload: null,
    marketDashboardPayload: null,
    simulationEvidencePayload: null,
    errors: {},
    timings: {},
  };

  // Initial set page render only needs the shell (header/title card) plus the
  // active tab's payload — no set-detail tab needs the full page snapshot
  // (payload_json) server-seeded anymore. Pull Rates moved off this in Phase
  // 4A (getPokemonSetPullRates) and Insights moved off it in Phase 4B
  // (getPokemonSetInsights) — both now fetch their own slim contract
  // client-side instead, in RipStatisticsPageClient.jsx. The full /page
  // fetch below is legacy-only, kept for non-"set" target types.
  const needsExplorePagePayload = requestedTargetType !== "set";

  if (requestedTargetId) {
    const snapshotPromise =
      requestedTargetType === "set"
        ? getPokemonSetInitialSnapshots(requestedTargetId, {
            tab: activeSetDetailTab,
          }).catch((error) => ({
            ...initialModuleSnapshots,
            errors: {
              moduleSnapshots: {
                message:
                  error?.message || "Failed to load initial module snapshots.",
              },
            },
          }))
        : Promise.resolve(initialModuleSnapshots);

    // The active tab's module snapshot (shell + cards/market-dashboard) is
    // critical content, not background work — it is awaited in full rather
    // than raced against a short timeout. loadInitialSnapshot already has its
    // own per-request timeout/fallback (see pokemonSetInitialSnapshotsServer),
    // so a slow backend still degrades gracefully without blanking the tab.
    const [exploreResult, moduleSnapshotsResult] = await Promise.all([
      (async () => {
        const startedAt = Date.now();
        if (!needsExplorePagePayload) {
          return {
            payload: null,
            error: null,
            elapsedMs: Date.now() - startedAt,
          };
        }
        try {
          return {
            payload: await getExplorePagePayload(
              requestedTargetType,
              requestedTargetId,
              {
                fallbackTarget,
              },
            ),
            error: null,
            elapsedMs: Date.now() - startedAt,
          };
        } catch (error) {
          return { payload: null, error, elapsedMs: Date.now() - startedAt };
        }
      })(),
      snapshotPromise,
    ]);

    explorePayload = exploreResult.payload;
    explorePagePayloadMs = exploreResult.elapsedMs ?? null;
    initialModuleSnapshots = moduleSnapshotsResult || initialModuleSnapshots;

    if (exploreResult.error) {
      pageError =
        exploreResult.error?.message || "Failed to load RIP Statistics.";
    } else if (!explorePayload && needsExplorePagePayload) {
      pageError =
        "No persisted RIP Statistics payload is available for this set.";
    }
  } else {
    pageError = "Set not found for this URL.";
  }

  const routeTotalMs = Date.now() - routeStartedAt;
  const snapshotTimings = initialModuleSnapshots?.timings || {};
  const snapshotTimedOut =
    requestedTargetType === "set" && !initialModuleSnapshots?.timings?.totalMs;

  console.info("[set-page-route] timings", {
    setSlug: requestedSetSlug,
    requestedTargetId,
    activeSetDetailTab,
    needsExplorePagePayload,
    targetsMs,
    explorePagePayloadMs,
    initialShellSnapshotMs: snapshotTimings.shellMs ?? null,
    initialCardsSnapshotMs: snapshotTimings.cardsMs ?? null,
    initialMarketDashboardSnapshotMs: snapshotTimings.marketDashboardMs ?? null,
    initialOverviewSnapshotMs: snapshotTimings.overviewMs ?? null,
    initialSimulationEvidenceMs: snapshotTimings.simulationEvidenceMs ?? null,
    initialModuleSnapshotsTotalMs: snapshotTimings.totalMs ?? null,
    snapshotTimedOut,
    routeTotalMs,
    targetsFallback: Boolean(targetsPayload?.meta?.fallback),
    explorePayloadFallback: Boolean(explorePayload?.meta?.fallback),
    snapshotErrors: Object.keys(initialModuleSnapshots?.errors || {}),
  });

  initialModuleSnapshots = {
    ...initialModuleSnapshots,
    timings: {
      ...snapshotTimings,
      targetsMs,
      explorePagePayloadMs,
      routeTotalMs,
    },
  };

  return (
    <PokemonSetPageClient
      targetsPayload={targetsPayload}
      selectedTarget={effectiveSelectedTarget}
      requestedTargetType={requestedTargetType}
      requestedTargetId={requestedTargetId}
      explorePayload={explorePayload}
      shellPayload={initialModuleSnapshots?.shellPayload || null}
      initialModuleSnapshots={initialModuleSnapshots}
      pageError={pageError}
      profileBaseHref="/TCGs/Pokemon/Sets"
      targetHrefById={targetHrefById}
    />
  );
}
