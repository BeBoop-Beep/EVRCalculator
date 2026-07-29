import { getRipStatisticsTargets } from "@/lib/explore/ripStatisticsServer";
import { isPublicAnalyticsEligiblePokemonSet } from "@/lib/pokemon/pokemonSetPublicCoverage";
import {
  selectLandingHeroSpotlight,
  selectLandingRankedStrip,
} from "@/lib/landing/landingHeroSpotlight.mjs";

// The landing hero reads the SAME cached RIP Statistics targets contract the
// Explore rankings read — one request/revalidate-300 fetch, already warm for
// most visitors, no landing-only endpoint. Both the panel and the ranked strip
// come out of this single payload.
const LANDING_TARGETS_LIMIT = 60;

export async function getLandingHeroData() {
  const payload = await getRipStatisticsTargets({ limit: LANDING_TARGETS_LIMIT }).catch(() => null);
  const targets = Array.isArray(payload?.targets) ? payload.targets : [];

  // Same public-analytics gate as Explore: sets whose simulator-era data is not
  // validated for public analytics never reach a public surface, and the
  // landing page is the most public surface there is.
  const eligibleTargets = targets.filter(isPublicAnalyticsEligiblePokemonSet);

  return {
    spotlight: selectLandingHeroSpotlight(eligibleTargets),
    ranked: selectLandingRankedStrip(eligibleTargets, 4),
  };
}
