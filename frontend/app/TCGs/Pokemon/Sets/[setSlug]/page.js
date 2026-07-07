import PokemonSetPageClient from "@/components/pokemon/set-page/PokemonSetPageClient";
import { getExplorePagePayload } from "@/lib/explore/explorePageServer";
import { getRipStatisticsTargets } from "@/lib/explore/ripStatisticsServer";
import { getPokemonSetInitialSnapshots } from "@/lib/pokemon/pokemonSetInitialSnapshotsServer";
import {
  buildTargetHrefById,
  buildTcgSetHrefFromTarget,
  findTargetBySetSlug,
  resolveSetDetailTab,
} from "@/lib/explore/ripStatisticsRouting";
import { redirect } from "next/navigation";

export default async function TcgSetRipStatisticsPage({ params, searchParams }) {
  const routeStartedAt = Date.now();
  const resolvedParams = (await params) || {};
  const requestedSetSlug = String(resolvedParams?.setSlug || "").trim().toLowerCase();
  const resolvedSearchParams = (await searchParams) || {};
  const activeSetDetailTab = resolveSetDetailTab(resolvedSearchParams?.tab);

  const targetsStartedAt = Date.now();
  const targetsPayload = await getRipStatisticsTargets({ limit: 150 }).catch((error) => ({
    targets: [],
    default_target: null,
    meta: {
      fallback: true,
      requestFailed: true,
      warnings: [
        `RIP Statistics targets unavailable; continuing with direct set snapshot fallback. ${error?.message || ""}`.trim(),
      ],
    },
  }));
  const targetsMs = Date.now() - targetsStartedAt;
  const targets = Array.isArray(targetsPayload?.targets) ? targetsPayload.targets : [];
  const defaultTarget = targetsPayload?.default_target || null;
  const targetHrefById = buildTargetHrefById(targets);

  if (!requestedSetSlug && defaultTarget?.target_type === "set") {
    redirect(buildTcgSetHrefFromTarget(defaultTarget));
  }

  const selectedTarget = findTargetBySetSlug(targets, requestedSetSlug);
  const requestedTargetType = selectedTarget?.target_type || "set";
  const requestedTargetId = selectedTarget?.target_id || requestedSetSlug;
  const fallbackTarget = selectedTarget || (requestedTargetId ? { target_type: "set", target_id: requestedTargetId } : null);
  const effectiveSelectedTarget = selectedTarget || fallbackTarget;

  let explorePayload = null;
  let pageError = null;
  let explorePagePayloadMs = null;
  let initialModuleSnapshots = {
    shellPayload: null,
    cardsPayload: null,
    marketDashboardPayload: null,
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
        ? getPokemonSetInitialSnapshots(requestedTargetId, { tab: activeSetDetailTab }).catch((error) => ({
            ...initialModuleSnapshots,
            errors: {
              moduleSnapshots: {
                message: error?.message || "Failed to load initial module snapshots.",
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
          return { payload: null, error: null, elapsedMs: Date.now() - startedAt };
        }
        try {
          return {
            payload: await getExplorePagePayload(requestedTargetType, requestedTargetId, {
              fallbackTarget,
            }),
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
      pageError = exploreResult.error?.message || "Failed to load RIP Statistics.";
    } else if (!explorePayload && needsExplorePagePayload) {
      pageError = "No persisted RIP Statistics payload is available for this set.";
    }
  } else {
    pageError = "Set not found for this URL.";
  }

  const routeTotalMs = Date.now() - routeStartedAt;
  const snapshotTimings = initialModuleSnapshots?.timings || {};
  const snapshotTimedOut = requestedTargetType === "set" && !initialModuleSnapshots?.timings?.totalMs;

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
