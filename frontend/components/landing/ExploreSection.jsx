import Link from "next/link";

import { getInterpretationBadgeStyle } from "@/lib/explore/interpretationTone";
import RemoteImg from "./previews/RemoteImg";
import { Arrow, RankLogo, ValueDelta } from "./previews/previewPrimitives";
import { currency0 } from "./landingFormat.mjs";
import styles from "./landing.module.css";

/**
 * Section 4 — the ranking board.
 *
 * Two panels with deliberately different weight, because they answer different
 * questions and the first pass made them look interchangeable:
 *
 *   PRIMARY   Best Sets to Rip — the cohort's opening-profile rank, the leading
 *             result given a real card thumbnail so the board is recognizably
 *             Pokemon at a glance.
 *   SECONDARY Set Value Leaders — ordered by checklist set value. Its position
 *             is this list's own descending order, a presentational index and
 *             never a cohort rank, which is what the caption says.
 *
 * Both read published rankings and route through the same set Overview links
 * Explore uses. Explore's own styling is untouched.
 */
export default function ExploreSection({ exploreRows = [], setValueLeaders = [], leadCard = null }) {
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
            <Link href="/Explore" className={styles.ctaSecondary}>
              Open Explore
              <Arrow />
            </Link>
          </div>
        </div>

        <div className={styles.boardGrid}>
          <div className={`${styles.card} ${styles.boardPrimary}`}>
            <p className={styles.cardHead}>
              <span className={styles.liveDot} aria-hidden="true" />
              <span id="landing-board-rip">Best sets to rip</span>
              <span className={styles.cardHeadNote}>Opening rank · RIP Score</span>
            </p>

            {exploreRows.length > 0 ? (
              <ol className={styles.rankList} aria-labelledby="landing-board-rip">
                {exploreRows.map((row, index) => {
                  const tierStyle = row.tier ? getInterpretationBadgeStyle({ rankTier: row.tier }) : null;
                  const showLeadCard = index === 0 && leadCard;

                  return (
                    <li key={row.key}>
                      <Link
                        href={row.href}
                        className={`${styles.rankRow} ${showLeadCard ? styles.rankRowLead : ""}`.trim()}
                      >
                        <span className={`${styles.rankPos} ${row.rank <= 3 ? styles.rankPosLead : ""}`.trim()}>
                          {row.rank}
                        </span>
                        {showLeadCard ? (
                          <span className={styles.leadThumb}>
                            <RemoteImg
                              src={leadCard.image}
                              className={styles.leadThumbImg}
                              width={245}
                              height={342}
                              fallback={<RankLogo logoUrl={row.logoUrl} name={row.name} />}
                            />
                          </span>
                        ) : (
                          <RankLogo logoUrl={row.logoUrl} name={row.name} />
                        )}
                        <span className={styles.rankName}>{row.name}</span>
                        <span className={styles.rankTrail}>
                          <span className={styles.rankScore}>
                            {row.score !== null ? row.score.toFixed(1) : "—"}
                            {row.tier ? (
                              <span className={styles.tierPill} style={tierStyle || undefined}>
                                {row.tier}
                              </span>
                            ) : null}
                          </span>
                        </span>
                      </Link>
                    </li>
                  );
                })}
              </ol>
            ) : (
              <p className={styles.emptyNote}>
                Rankings are refreshing. Open Explore for the full table.
              </p>
            )}

            <Link href="/Explore" className={styles.cardCta}>
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

            {setValueLeaders.length > 0 ? (
              <ol className={styles.valueList} aria-labelledby="landing-board-value">
                {setValueLeaders.map((row) => (
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
                Set values are refreshing. Open Explore for the sets published right now.
              </p>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
