import Link from "next/link";

import { getInterpretationBadgeStyle } from "@/lib/explore/interpretationTone";
import { currency2, formatAsOf, formatProbability } from "../landingFormat.mjs";
import { Arrow } from "./previewPrimitives";
import styles from "../landing.module.css";

/**
 * The featured set's intelligence, led by something a first-time visitor can
 * read.
 *
 * The previous version made a bare "100.0" the dominant element, which is
 * meaningless cold: it is a cohort-relative position, not a score out of a
 * hundred and not a probability. So the headline is now the rank in plain
 * language — "#1 Opening Profile" — the number is demoted to a supporting
 * figure, and the microcopy states outright what it is and is not. The one
 * genuinely interpretable figure beside it is the published share of simulated
 * openings that land above pack cost.
 */
export default function FeaturedSetPanel({ set, marketDate = null, compact = false }) {
  if (!set) {
    return (
      <div className={styles.featuredPanel}>
        <p className={styles.cardHead}>
          <span className={styles.liveDot} aria-hidden="true" />
          Live set intelligence
        </p>
        <p className={styles.emptyNote}>
          Set rankings are refreshing. Open Explore for the sets published right now.
        </p>
        <Link href="/Explore" className={styles.cardCta}>
          Explore Pokémon sets
          <Arrow />
        </Link>
      </div>
    );
  }

  const tierStyle = set.tier ? getInterpretationBadgeStyle({ rankTier: set.tier }) : null;
  const probability = formatProbability(set.probProfit);
  const asOf = formatAsOf(marketDate || set.setValueAsOf);

  return (
    <div className={styles.featuredPanel}>
      <p className={styles.cardHead}>
        <span className={styles.liveDot} aria-hidden="true" />
        Live set intelligence
        {asOf ? <span className={styles.cardHeadNote}>{asOf}</span> : null}
      </p>

      <p className={styles.openingRank}>
        {set.rank !== null ? (
          <>
            <span className={styles.openingRankNum}>#{set.rank}</span>
            <span className={styles.openingRankLabel}>
              Opening profile
              {set.cohortSize !== null ? (
                <span className={styles.openingRankCohort}>of {set.cohortSize} tracked sets</span>
              ) : null}
            </span>
          </>
        ) : (
          <span className={styles.openingRankLabel}>Opening profile</span>
        )}
      </p>

      <p className={styles.featuredSetName}>{set.name}</p>

      <div className={styles.featuredStats}>
        <span className={styles.stat}>
          <span className={styles.statLabel}>RIP Score</span>
          <span className={styles.statValue}>
            {set.score.toFixed(1)}
            {set.tier ? (
              <span className={styles.tierPill} style={tierStyle || undefined}>
                {set.tier}
              </span>
            ) : null}
          </span>
        </span>
        {probability ? (
          <span className={styles.stat}>
            <span className={styles.statLabel}>Above pack cost</span>
            <span className={styles.statValue}>{probability}</span>
          </span>
        ) : null}
        {set.packCost !== null && !compact ? (
          <span className={styles.stat}>
            <span className={styles.statLabel}>Pack cost</span>
            <span className={styles.statValue}>{currency2.format(set.packCost)}</span>
          </span>
        ) : null}
      </div>

      <p className={styles.scoreCaveat}>Relative opening rank&mdash;not a profit probability.</p>

      <Link href={set.overviewHref || set.href} className={styles.cardCta}>
        View set intelligence
        <Arrow />
      </Link>
    </div>
  );
}
