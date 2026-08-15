import { notFound, redirect } from "next/navigation";

import PokemonSetAnalysisClient from "@/components/pokemon/set-page/Analysis/PokemonSetAnalysisClient";
import { POKEMON_SET_ANALYSIS_ENABLED } from "@/config/featureFlags";
import { buildTcgSetHrefFromSlug, findTargetBySetSlug } from "@/lib/explore/ripStatisticsRouting";
import { getRipStatisticsTargets } from "@/lib/explore/ripStatisticsServer";
import { buildRouteMetadata } from "@/lib/seo/routeMetadata.mjs";

export async function generateMetadata({ params }) {
  const { setSlug } = await params;
  return buildRouteMetadata({ path: `/TCGs/Pokemon/Sets/${encodeURIComponent(setSlug)}/analysis`, title: "Pokémon Set Deep Dive Analysis — inDex", description: "Detailed simulation, Financial RIP, Collector Appeal, and market context for this Pokémon set." });
}

export default async function PokemonSetAnalysisPage({ params }) {
  const { setSlug } = await params;
  if (!POKEMON_SET_ANALYSIS_ENABLED) {
    redirect(buildTcgSetHrefFromSlug(setSlug));
  }
  const payload = await getRipStatisticsTargets({ limit: 150 }).catch(() => ({ targets: [] }));
  const targets = Array.isArray(payload?.targets) ? payload.targets.filter((target) => target?.target_type === "set") : [];
  const selectedTarget = findTargetBySetSlug(targets, String(setSlug || "").toLowerCase());
  if (!selectedTarget) notFound();
  return <PokemonSetAnalysisClient selectedTarget={selectedTarget} targets={targets} />;
}
