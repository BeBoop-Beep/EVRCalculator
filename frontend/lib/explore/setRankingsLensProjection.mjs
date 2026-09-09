import {
  projectRankingsClientPlus,
  projectRankingsClientPublicSetLeaderboard,
} from "./rankingsClientProjection.mjs";

/**
 * Final server-to-client boundary for the live Set Rankings lens.
 *
 * The backend has already enforced the plan boundary and reports that decision
 * in `access.rankingsIntelligence`. Basic rows stay on the narrow public Set
 * RIP leaderboard contract. Entitled rows retain the fields the live table
 * consumes, while Chase is normalized once to `setRipV1.chaseAccessibility`,
 * the canonical location read by ExploreTableClient and rankingsSort.
 */
export function projectSetRankingsLensTargets(targets, access = null) {
  if (access?.rankingsIntelligence !== true) {
    return projectRankingsClientPublicSetLeaderboard(targets);
  }
  return projectRankingsClientPlus(targets).map((target) => {
    const chase = target?.setRipV1?.chaseAccessibility || target?.chaseAccessibility;
    const projected = { ...target };
    if (chase) {
      projected.setRipV1 = { ...(projected.setRipV1 || {}), chaseAccessibility: chase };
    }
    // The Set table has one Chase contract location. Avoid serializing a
    // second copy after normalization.
    delete projected.chaseAccessibility;
    delete projected.overallRipV12Composition;
    if (projected.overallRipV12) {
      projected.overallRipV12 = { ...projected.overallRipV12 };
      delete projected.overallRipV12.components;
    }
    return projected;
  });
}
