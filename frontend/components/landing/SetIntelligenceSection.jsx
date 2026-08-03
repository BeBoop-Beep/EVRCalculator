import Link from "next/link";

import { selectOpeningEconomics, selectSetValueMovement } from "@/lib/landing/landingPreviews.mjs";
import ChaseCardRow from "./previews/ChaseCardRow";
import { Arrow, SetMark, ValueDelta } from "./previews/previewPrimitives";
import { currency0, currency2, formatAsOf, formatProbability } from "./landingFormat.mjs";
import styles from "./landing.module.css";

/**
 * Section 3 — one real set, read end to end.
 *
 * Features a DIFFERENT set from the hero wherever more than one is published,
 * so the page shows breadth rather than describing one set four times.
 *
 * The Quick Read leads. It is the backend's own published decision signal
 * (`leaderboard_label`, falling back to the canonical recommendation header and
 * then the RIP interpretation label) — never invented advice. When no published
 * interpretation exists the block falls back to plain factual labels and no
 * verdict is stated at all.
 */
export default function SetIntelligenceSection({ set, chaseCards = [] }) {
  const movement = selectSetValueMovement(set);
  const economics = selectOpeningEconomics(set);
  const probability = formatProbability(set?.probProfit);
  const asOf = formatAsOf(set?.setValueAsOf);
  const quickRead = set?.decisionLabel || set?.interpretationLabel || null;

  return (
    <section className={`${styles.section} ${styles.sectionRaised}`} aria-labelledby="landing-set-heading">
      <div className={styles.shell}>
        <div className={styles.feature}>
          <div className={styles.featureCopy}>
            <h2 id="landing-set-heading" className={styles.sectionTitle}>
              Understand the set, not just the chase card.
            </h2>
            <p className={styles.sectionLede}>
              Follow the complete set through value trends, opening economics, chase-card movement,
              and decision signals.
            </p>

            {quickRead ? (
              <div className={styles.quickRead}>
                <p className={styles.quickReadLabel}>Quick read</p>
                <p className={styles.quickReadText}>{quickRead}</p>
                {set?.interpretationSummary ? (
                  <p className={styles.quickReadNote}>{set.interpretationSummary}</p>
                ) : null}
              </div>
            ) : null}

            <div className={styles.featureActions}>
              <Link href={set?.overviewHref || "/Explore"} className={styles.ctaSecondary}>
                View set intelligence
                <Arrow />
              </Link>
            </div>
          </div>

          <div className={styles.featureMedia}>
            <div className={styles.setBoard}>
              {set ? (
                <div className={styles.setBoardHead}>
                  <SetMark logoUrl={set.logoUrl || set.symbolUrl} name={set.name} className={styles.showcaseLogo} />
                  <span className={styles.setText}>
                    <span className={styles.showcaseSetName}>{set.name}</span>
                    {set.era ? <span className={styles.showcaseSetMeta}>{set.era}</span> : null}
                  </span>
                  {asOf ? <span className={styles.cardHeadNote}>{asOf}</span> : null}
                </div>
              ) : null}

              <ChaseCardRow cards={chaseCards} label="Top chase cards" />

              <div className={styles.setBoardStats}>
                {set?.setValue !== null && set?.setValue !== undefined ? (
                  <div className={styles.setBoardStat}>
                    <span className={styles.metricLabel}>Set value</span>
                    <p className={styles.value}>{currency0.format(set.setValue)}</p>
                    <ValueDelta movement={movement} />
                  </div>
                ) : null}

                {economics ? (
                  <div className={styles.setBoardStat}>
                    <span className={styles.metricLabel}>Opening profit vs cost</span>
                    <div className={styles.bars}>
                      <div className={styles.barRow}>
                        <span className={styles.barLabel}>Pack cost</span>
                        <span className={styles.barValue}>{currency2.format(economics.packCost)}</span>
                        <span className={styles.barTrack}>
                          <span
                            className={`${styles.barFill} ${styles.barFillCost}`}
                            style={{ width: `${(economics.costShare * 100).toFixed(1)}%` }}
                          />
                        </span>
                      </div>
                      <div className={styles.barRow}>
                        <span className={styles.barLabel}>Modeled mean opening</span>
                        <span className={styles.barValue}>{currency2.format(economics.meanValue)}</span>
                        <span className={styles.barTrack}>
                          <span
                            className={styles.barFill}
                            style={{ width: `${(economics.valueShare * 100).toFixed(1)}%` }}
                          />
                        </span>
                      </div>
                    </div>
                    {probability ? (
                      <p className={styles.emptyNote}>
                        {probability} of simulated openings land above pack cost.
                      </p>
                    ) : null}
                  </div>
                ) : null}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
