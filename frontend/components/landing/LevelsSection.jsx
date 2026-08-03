import Link from "next/link";

import { getInterpretationBadgeStyle } from "@/lib/explore/interpretationTone";
import { selectOpeningEconomics, selectSetValueMovement } from "@/lib/landing/landingPreviews.mjs";
import ChaseCardRow from "./previews/ChaseCardRow";
import SealedProductLine from "./previews/SealedProductLine";
import { Arrow, RankLogo, SetMark, ValueDelta } from "./previews/previewPrimitives";
import { currency0, currency2, formatProbability } from "./landingFormat.mjs";
import styles from "./landing.module.css";

/**
 * Section 2 — the three questions, and the product that answers each.
 *
 * The first pass gave all three levels the same dark metric card, which made
 * one product look like three. Each entry now looks like the thing it is:
 * the RIP entry is anchored to sealed product, the Set Intelligence entry to
 * cards, and the Explore entry to a ranking board.
 */

function RipLevel({ set, sealedProducts }) {
  const economics = selectOpeningEconomics(set);
  const probability = formatProbability(set?.probProfit);

  return (
    <div className={`${styles.levelCard} ${styles.levelCardSealed}`}>
      <p className={styles.levelCardHead}>Opening profile</p>

      {sealedProducts.length > 0 ? (
        <SealedProductLine products={sealedProducts} />
      ) : (
        <p className={styles.emptyNote}>Sealed pricing is refreshing for this set.</p>
      )}

      {economics ? (
        <>
          <div className={styles.divider} aria-hidden="true" />
          <div className={styles.statGrid}>
            <span className={styles.stat}>
              <span className={styles.statLabel}>Pack cost</span>
              <span className={styles.statValue}>{currency2.format(economics.packCost)}</span>
            </span>
            <span className={styles.stat}>
              <span className={styles.statLabel}>Modeled mean</span>
              <span className={styles.statValue}>{currency2.format(economics.meanValue)}</span>
            </span>
            <span className={styles.stat}>
              <span className={styles.statLabel}>Above cost</span>
              <span className={styles.statValue}>{probability ?? "—"}</span>
            </span>
          </div>
        </>
      ) : null}

      {set?.rank !== null && set?.rank !== undefined ? (
        <p className={styles.levelCardFoot}>
          <span className={styles.levelCardFootRank}>#{set.rank}</span> opening profile
          {set.cohortSize !== null ? ` of ${set.cohortSize} tracked sets` : ""}
        </p>
      ) : null}
    </div>
  );
}

function SetLevel({ set, chaseCards }) {
  const movement = selectSetValueMovement(set);
  const signal = set?.decisionLabel || set?.interpretationLabel;

  return (
    <div className={`${styles.levelCard} ${styles.levelCardCards}`}>
      {set ? (
        <div className={styles.setRow}>
          <SetMark logoUrl={set.logoUrl || set.symbolUrl} name={set.name} />
          <span className={styles.setText}>
            <span className={styles.setName}>{set.name}</span>
            {set.setValue !== null ? (
              <span className={styles.setEra}>Set value {currency0.format(set.setValue)}</span>
            ) : null}
          </span>
          <ValueDelta movement={movement} />
        </div>
      ) : null}

      <ChaseCardRow cards={chaseCards.slice(0, 2)} label="Chase cards" />

      {signal ? (
        <p className={styles.signal}>
          <span className={styles.signalDot} aria-hidden="true" />
          <span className={styles.signalText}>{signal}</span>
        </p>
      ) : null}
    </div>
  );
}

function ExploreLevel({ rows }) {
  return (
    <div className={`${styles.levelCard} ${styles.levelCardBoard}`}>
      <p className={styles.levelCardHead}>Tracked sets by opening profile</p>
      {rows.length > 0 ? (
        <ol className={styles.rankList}>
          {rows.map((row) => {
            const tierStyle = row.tier ? getInterpretationBadgeStyle({ rankTier: row.tier }) : null;
            return (
              <li key={row.key}>
                <Link href={row.href} className={styles.rankRow}>
                  <span className={`${styles.rankPos} ${row.rank <= 3 ? styles.rankPosLead : ""}`.trim()}>
                    {row.rank}
                  </span>
                  <RankLogo logoUrl={row.logoUrl} name={row.name} />
                  <span className={styles.rankName}>{row.name}</span>
                  <span className={styles.rankScore}>
                    {row.score !== null ? row.score.toFixed(1) : "—"}
                    {row.tier ? (
                      <span className={styles.tierPill} style={tierStyle || undefined}>
                        {row.tier}
                      </span>
                    ) : null}
                  </span>
                </Link>
              </li>
            );
          })}
        </ol>
      ) : (
        <p className={styles.emptyNote}>Rankings are refreshing. Open Explore for the full table.</p>
      )}
      <Link href="/Explore" className={styles.cardCta}>
        Open Explore
        <Arrow />
      </Link>
    </div>
  );
}

export default function LevelsSection({ set, chaseCards = [], sealedProducts = [], exploreRows = [] }) {
  const LEVELS = [
    {
      key: "rip",
      question: "Should I open it?",
      product: "RIP Score",
      meaning:
        "See modeled opening outcomes, downside, and relative opening strength before breaking the seal.",
      visual: <RipLevel set={set} sealedProducts={sealedProducts} />,
    },
    {
      key: "set",
      question: "What is driving the set?",
      product: "Set Intelligence",
      meaning: "Understand set value, chase-card movement, opening economics, and decision signals.",
      visual: <SetLevel set={set} chaseCards={chaseCards} />,
    },
    {
      key: "explore",
      question: "How does it compare?",
      product: "Explore",
      meaning:
        "Compare opening profiles, set values, tiers, and recent movement across tracked Pokémon sets.",
      visual: <ExploreLevel rows={exploreRows} />,
    },
  ];

  return (
    <section className={styles.section} aria-labelledby="landing-levels-heading">
      <div className={styles.shell}>
        <div className={styles.sectionHead}>
          <h2 id="landing-levels-heading" className={styles.sectionTitle}>
            One pack. One set. The whole Pokémon market.
          </h2>
        </div>

        <div className={styles.levels}>
          {LEVELS.map((level) => (
            <article key={level.key} className={styles.level}>
              <h3 className={styles.levelQuestion}>{level.question}</h3>
              <p className={styles.levelProduct}>{level.product}</p>
              <p className={styles.levelCopy}>{level.meaning}</p>
              <div className={styles.levelPreview}>{level.visual}</div>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
