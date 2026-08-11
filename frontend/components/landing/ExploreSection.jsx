import Link from "next/link";

import { getInterpretationBadgeStyle } from "@/lib/explore/interpretationTone";
import { Arrow, RankLogo, ValueDelta } from "./previews/previewPrimitives";
import { currency0 } from "./landingFormat.mjs";
import styles from "./landing.module.css";

/**
 * Section 4 — the ranking board.
 *
 * ENTITY IMAGERY IS UNIFORM. Every row on both boards is a SET, so every row
 * shows that set's logo. An earlier pass gave the leading Best Sets to Rip row
 * the top chase card from the hero set instead, which put a single card image
 * in a column of set logos and implied the row was about that card. The lead
 * row still reads as the lead row — through the rank numeral and a subtle
 * background — but its entity image is the set logo like every other row.
 *
 * The two boards differ by HIERARCHY AND METRIC, not by imagery:
 *   PRIMARY   Best Sets to Rip — strong numbered rank, tier, RIP Score secondary
 *   SECONDARY Set Value Leaders — compact financial rows, value and 7-day move
 *
 * Both read published rankings and route through the same set Overview links
 * Explore uses. Explore's own styling is untouched, and no row is withheld
 * because the set is featured elsewhere on the page — the board has to be the
 * real ranking.
 */
export default function ExploreSection({ openingRankingRows = [], setValueRankingRows = [] }) {
  return (
    <section className={styles.section} aria-labelledby="landing-explore-heading">
      <div className={styles.shell}>
        <div className={styles.sectionHead}>
          <h2 id="landing-explore-heading" className={styles.sectionTitle}>
            See where every tracked Pokémon set stands.
          </h2>
          <p className={styles.sectionLede}>
            Compare opening strength, set value, tier, and recent movement without researching every
            set separately.
          </p>
          <div className={styles.featureActions}>
            <Link href="/Rankings" className={styles.ctaSecondary}>
              Open Rankings
              <Arrow />
            </Link>
          </div>
        </div>

        <div className={styles.boardGrid}>
          <div className={`${styles.card} ${styles.boardPrimary}`}>
            <p className={styles.cardHead}>
              <span className={styles.liveDot} aria-hidden="true" />
              <span id="landing-board-rip">Best sets to rip</span>
              <span className={styles.cardHeadNote}>Opening Rank</span>
            </p>

            {openingRankingRows.length > 0 ? (
              <ol className={styles.rankList} aria-labelledby="landing-board-rip">
                {openingRankingRows.map((row, index) => {
                  const tierStyle = row.tier ? getInterpretationBadgeStyle({ rankTier: row.tier }) : null;

                  return (
                    <li key={row.key}>
                      <Link
                        href={row.href}
                        className={`${styles.rankRow} ${index === 0 ? styles.rankRowLead : ""}`.trim()}
                      >
                        <span
                          className={`${styles.rankPos} ${row.rank <= 3 ? styles.rankPosLead : ""}`.trim()}
                        >
                          {row.rank}
                        </span>
                        <RankLogo logoUrl={row.logoUrl} name={row.name} />
                        <span className={styles.rankName}>{row.name}</span>
                        <span className={styles.rankTrail}>
                          {row.tier ? (
                            <span className={styles.tierPill} style={tierStyle || undefined}>
                              {row.tier}
                            </span>
                          ) : null}
                          {row.score !== null ? (
                            <span className={styles.rankScoreMuted}>{row.score.toFixed(0)}</span>
                          ) : null}
                        </span>
                      </Link>
                    </li>
                  );
                })}
              </ol>
            ) : (
              <p className={styles.emptyNote}>
                Rankings are refreshing. Open Rankings for the full table.
              </p>
            )}

            <Link href="/Rankings" className={styles.cardCta}>
              See all rankings
              <Arrow />
            </Link>
          </div>

          <div className={`${styles.card} ${styles.boardSecondary}`}>
            <p className={styles.cardHead}>
              <span id="landing-board-value">Set value leaders</span>
              {/* The caption is the accessible description too: this list's
                  order is its own descending index, not a cohort rank. */}
              <span className={styles.cardHeadNote}>Highest checklist value first</span>
            </p>

            {setValueRankingRows.length > 0 ? (
              <ol className={styles.valueList} aria-labelledby="landing-board-value">
                {setValueRankingRows.map((row) => (
                  <li key={row.key}>
                    <Link href={row.href} className={styles.valueRowLink}>
                      <RankLogo logoUrl={row.logoUrl} name={row.name} />
                      <span className={styles.valueName}>{row.name}</span>
                      <span className={styles.valueTrail}>
                        <span className={styles.valueAmount}>{currency0.format(row.setValue)}</span>
                        <ValueDelta movement={row.movement} />
                      </span>
                    </Link>
                  </li>
                ))}
              </ol>
            ) : (
              <p className={styles.emptyNote}>
                Set values are refreshing. Open Market for the sets published right now.
              </p>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
