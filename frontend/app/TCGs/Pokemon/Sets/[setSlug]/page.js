import PokemonSetPageClient from "@/components/pokemon/set-page/PokemonSetPageClient";
import { getExplorePagePayload } from "@/lib/explore/explorePageServer";
import { getRipStatisticsTargets } from "@/lib/explore/ripStatisticsServer";
import { getPokemonSetInitialSnapshots } from "@/lib/pokemon/pokemonSetInitialSnapshotsServer";
import {
  buildTargetHrefById,
  buildTcgSetHrefFromTarget,
  findTargetBySetSlug,
} from "@/lib/explore/ripStatisticsRouting";
import { redirect } from "next/navigation";

export default async function TcgSetRipStatisticsPage({ params }) {
  const resolvedParams = (await params) || {};
  const requestedSetSlug = String(resolvedParams?.setSlug || "").trim().toLowerCase();

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
  let initialModuleSnapshots = {
    cardsPayload: null,
    marketDashboardPayload: null,
    errors: {},
    timings: {},
  };

  if (requestedTargetId) {
    const [exploreResult, moduleSnapshotsResult] = await Promise.all([
      (async () => {
        try {
          return {
            payload: await getExplorePagePayload(requestedTargetType, requestedTargetId, {
              fallbackTarget,
            }),
            error: null,
          };
        } catch (error) {
          return { payload: null, error };
        }
      })(),
      requestedTargetType === "set"
        ? getPokemonSetInitialSnapshots(requestedTargetId).catch((error) => ({
            ...initialModuleSnapshots,
            errors: {
              moduleSnapshots: {
                message: error?.message || "Failed to load initial module snapshots.",
              },
            },
          }))
        : Promise.resolve(initialModuleSnapshots),
    ]);

    explorePayload = exploreResult.payload;
    initialModuleSnapshots = moduleSnapshotsResult || initialModuleSnapshots;

    if (exploreResult.error) {
      pageError = exploreResult.error?.message || "Failed to load RIP Statistics.";
    } else if (!explorePayload) {
      pageError = "No persisted RIP Statistics payload is available for this set.";
    }
  } else {
    pageError = "Set not found for this URL.";
  }

  return (
    <PokemonSetPageClient
      targetsPayload={targetsPayload}
      selectedTarget={effectiveSelectedTarget}
      requestedTargetType={requestedTargetType}
      requestedTargetId={requestedTargetId}
      explorePayload={explorePayload}
      initialModuleSnapshots={initialModuleSnapshots}
      pageError={pageError}
      profileBaseHref="/TCGs/Pokemon/Sets"
      targetHrefById={targetHrefById}
    />
  );
}
