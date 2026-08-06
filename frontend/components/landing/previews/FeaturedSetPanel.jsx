import Link from "next/link";

import { getInterpretationBadgeStyle } from "@/lib/explore/interpretationTone";
import { currency2, formatAsOf, formatProbability } from "../landingFormat.mjs";
import { Arrow } from "./previewPrimitives";
import styles from "../landing.module.css";

/**
 * The opening spotlight's intelligence, led by the one figure a first-time
 * visitor can actually read.
 *
 * ORDER IS THE POINT. Rank, then what the rank is, then the cohort it is out
 * of, then the set, its tier, its published read, and only then the absolute
 * opening metrics — with RIP Score last and smallest. A bare "100.0" led this
 * panel before: it is a cohort-relative position, not a score out of a hundred
 * and not a probability, and leading with it invited exactly that misreading.
 *
 * This is also the ONE place on the page that spells the caveat out. Every
 * other surface just uses an accurate label.
 */
export default function FeaturedSetPanel({ set, marketDate = null }) {
  if (!set) {
    return (
      <div className={styles.featuredPanel}>
        <p className={styles.cardHead}>
          <span className={styles.liveDot} aria-hidden="true" />
          Live set intelligence
        </p>
        <p className={styles.emptyNote}>
          Opening rankings are refreshing. Open Explore for the sets published right now.
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
  // No verdict line. `decisionLabel` / `interpretationLabel` were retired
  // interpretation-engine copy; the panel states published figures instead of a
  // sentence about a superseded model.

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
              Opening Rank
              {set.cohortSize !== null ? (
                <span className={styles.openingRankCohort}>of {set.cohortSize} tracked sets</span>
              ) : null}
            </span>
          </>
        ) : (
          <span className={styles.openingRankLabel}>Opening Rank</span>
        )}
      </p>

      <p className={styles.featuredSetName}>
        {set.name}
        {set.tier ? (
          <span className={styles.tierPill} style={tierStyle || undefined}>
            {set.tier}
          </span>
        ) : null}
      </p>

      <div className={styles.featuredStats}>
        {probability ? (
          <span className={styles.stat}>
            <span className={styles.statLabel}>Above pack cost</span>
            <span className={styles.statValue}>{probability}</span>
          </span>
        ) : null}
        {set.packCost !== null ? (
          <span className={styles.stat}>
            <span className={styles.statLabel}>Pack cost</span>
            <span className={styles.statValue}>{currency2.format(set.packCost)}</span>
          </span>
        ) : null}
        {/* Supporting analytical detail, deliberately last and smallest. */}
        <span className={`${styles.stat} ${styles.statMuted}`}>
          <span className={styles.statLabel}>RIP Score</span>
          <span className={styles.statValue}>{set.score.toFixed(0)}</span>
        </span>
      </div>

      <p className={styles.scoreCaveat}>Relative opening rank&mdash;not a profit probability.</p>

      <Link href={set.overviewHref || set.href} className={styles.cardCta}>
        View set intelligence
        <Arrow />
      </Link>
    </div>
  );
}
