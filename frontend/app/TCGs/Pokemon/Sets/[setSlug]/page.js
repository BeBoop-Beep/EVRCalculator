import PokemonSetPageClient from "@/components/pokemon/set-page/PokemonSetPageClient";
import { getExplorePagePayload } from "@/lib/explore/explorePageServer";
import { getPokemonSetRouteDirectory } from "@/lib/pokemon/pokemonSetRouteDirectoryServer";
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

export async function generateMetadata({ params }) {
  const resolvedParams = (await params) || {};
  const rawSetSegment = String(resolvedParams?.setSlug || "").trim();
  const requestedSetSlug = toSetSlug(rawSetSegment);

  if (!requestedSetSlug) {
    return buildRouteMetadata({
      path: SETS_BASE_PATH,
      title: "Pokémon TCG Set Catalog — inDex",
      description: "Browse Pokémon TCG sets and open one for its Overall RIP and opening analysis.",
    });
  }

  const targetsPayload = await getPokemonSetRouteDirectory({ limit: 150 }).catch(() => null);
  const selectedTarget = findTargetBySetSlug(
    Array.isArray(targetsPayload?.targets) ? targetsPayload.targets : [],
    rawSetSegment,
  );
  const setName = String(selectedTarget?.name || "").trim();
  const canonicalPath = selectedTarget
    ? buildTcgSetHrefFromTarget(selectedTarget).split("?")[0]
    : `${SETS_BASE_PATH}/${encodeURIComponent(requestedSetSlug)}`;

  if (!setName) {
    return buildRouteMetadata({
      path: canonicalPath,
      title: "Pokémon Set Overall RIP & Opening Analysis — inDex",
      description: "Overall RIP, Financial RIP, Collector Appeal and modeled opening outcomes for this Pokémon set.",
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

export default async function TcgSetRipStatisticsPage({ params, searchParams }) {
  const routeStartedAt = Date.now();
  const resolvedParams = (await params) || {};
  const rawSetSegment = String(resolvedParams?.setSlug || "").trim();
  const requestedSetSlug = toSetSlug(rawSetSegment);
  const resolvedSearchParams = (await searchParams) || {};
  const activeSetDetailTab = resolveSetDetailTab(resolvedSearchParams?.tab);

  // P0 performance rule: URL resolution and the set picker never need the
  // heavyweight RIP Statistics cohort. Every canonical set tab uses the slim
  // route directory; active-tab analytics arrive through their own dedicated
  // contracts below/client-side.
  const targetsStartedAt = Date.now();
  const targetsPayload = await getPokemonSetRouteDirectory({ limit: 150 }).catch((error) => ({
    targets: [],
    default_target: null,
    meta: {
      fallback: true,
      requestFailed: true,
      warnings: [`Set route directory unavailable. ${error?.message || ""}`.trim()],
    },
  }));
  const targetsMs = Date.now() - targetsStartedAt;
  const targets = Array.isArray(targetsPayload?.targets) ? targetsPayload.targets : [];
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
    ripBootstrapPayload: null,
    errors: {},
    timings: {},
  };

  // Canonical set routes no longer require the legacy monolithic /page
  // snapshot. Keep the fallback only for a legacy non-set target should one
  // ever reach this route.
  const needsExplorePagePayload = requestedTargetType !== "set";

  if (requestedTargetId) {
    const snapshotPromise = requestedTargetType === "set"
      ? getPokemonSetInitialSnapshots(requestedTargetId, { tab: activeSetDetailTab }).catch((error) => ({
          ...initialModuleSnapshots,
          errors: { moduleSnapshots: { message: error?.message || "Failed to load initial module snapshots." } },
        }))
      : Promise.resolve(initialModuleSnapshots);

    const [exploreResult, moduleSnapshotsResult] = await Promise.all([
      (async () => {
        const startedAt = Date.now();
        if (!needsExplorePagePayload) return { payload: null, error: null, elapsedMs: Date.now() - startedAt };
        try {
          return {
            payload: await getExplorePagePayload(requestedTargetType, requestedTargetId, { fallbackTarget }),
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
    initialOverviewSnapshotMs: snapshotTimings.overviewMs ?? null,
    initialSimulationEvidenceMs: snapshotTimings.simulationEvidenceMs ?? null,
    initialRipBootstrapMs: snapshotTimings.ripBootstrapMs ?? null,
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
