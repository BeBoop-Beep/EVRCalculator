import Link from "next/link";

import WaitlistCta from "@/components/landing/WaitlistCta";
import HeroShowcase from "@/components/landing/HeroShowcase";
import HeroBoosterPackBackdrop from "@/components/landing/HeroBoosterPackBackdrop";
import { formatFullDate } from "@/components/landing/landingFormat.mjs";
import styles from "./LandingHero.module.css";

function Arrow() {
  return (
    <svg className={styles.ctaArrow} width="13" height="13" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path
        d="M3 8h10M9 4l4 4-4 4"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/**
 * The hero.
 *
 * WHAT CHANGED AND WHY. The previous version led with an oversized inDex
 * wordmark and an abstract signal trace, and its loudest action was a waitlist
 * for a product that does not ship yet. A cold visitor could read the whole
 * thing and not learn the category. So:
 *
 *   - the wordmark is gone from the hero (the header already carries the
 *     brand) and the space it held now states the category outright;
 *   - the right side is real Pokemon product content instead of atmosphere;
 *   - the yellow action is Explore, the thing that works today, and the
 *     waitlist steps down to a tertiary link scoped to the portfolio product.
 */
export default function LandingHero({
  set,
  chaseCards = [],
  sealedProducts = [],
  cardsAsOf = null,
  marketContext = null,
  boosterPackImage = null,
}) {
  // Published coverage and freshness, stated as a line rather than as a badge.
  // Both figures are real or the clause is dropped — there is no default here.
  const trackedSets = marketContext?.rankedSetCount ?? null;
  const marketDate = formatFullDate(marketContext?.marketDate || cardsAsOf);
  const metaParts = [
    trackedSets ? `${trackedSets} tracked Pokémon sets` : null,
    marketDate ? `market data as of ${marketDate}` : null,
  ].filter(Boolean);

  return (
    <section className={styles.stage} aria-labelledby="landing-hero-headline">
      <div className={styles.stageGlow} aria-hidden="true" />

      <div className={styles.shell}>
        <div className={styles.frame}>
          <div className={`${styles.layer} ${styles.layerBase}`} aria-hidden="true" />
          <div className={`${styles.layer} ${styles.layerGrid}`} aria-hidden="true" />

          {/* The inDex mark stays, but only as the scene's light source — a
              supporting element behind the product, not the subject. */}
          <div className={`${styles.markLayer} ${styles.markGlow}`} aria-hidden="true" />

          {/* Decorative product imagery. Sits BEFORE the rake and veil so both
              paint over it, keeping the copy column's readability floor exactly
              as it was. Renders nothing when no image resolved. */}
          <HeroBoosterPackBackdrop image={boosterPackImage} />

          <div className={`${styles.layer} ${styles.layerRake}`} aria-hidden="true" />
          <div className={`${styles.layer} ${styles.layerVeil}`} aria-hidden="true" />

          <div className={styles.content}>
            <div className={styles.col}>
              <p className={`${styles.eyebrow} ${styles.rise}`}>Pokémon TCG market intelligence</p>

              <h1 id="landing-hero-headline" className={`${styles.headline} ${styles.rise}`} style={{ "--d": "70ms" }}>
                Know what&rsquo;s
                <br className={styles.breakNarrow} />{" "}
                <span className={styles.headlineAccent}>worth opening</span>
                <br />
                before you rip.
              </h1>

              <p className={`${styles.lede} ${styles.rise}`} style={{ "--d": "130ms" }}>
                Live Pokémon set values, opening simulations, chase-card movement, and cross-set
                rankings&mdash;built to help collectors understand what to open, compare, and track.
              </p>

              {/*
                All three actions are siblings of one flex row so their weights
                can be re-ranked per viewport without moving them in the
                document: on desktop the waitlist takes its own line beneath the
                two buttons; on a phone the secondary drops to link weight and
                shares a line with it, leaving Explore the only button.
              */}
              <div className={`${styles.ctas} ${styles.rise}`} style={{ "--d": "190ms" }}>
                <Link href="/Explore" className={styles.ctaPrimary}>
                  Explore Pokémon sets
                </Link>
                <Link href={set?.ripScoreHref || "/Explore"} className={styles.ctaSecondary}>
                  How RIP Score works
                  <Arrow />
                </Link>
                {/* Scoped to what it actually is: the waitlist is for the
                    portfolio product, which is not shipped. */}
                <WaitlistCta
                  source="landing_page_hero"
                  label="Join the portfolio waitlist"
                  variant="link"
                  className={styles.waitlistLink}
                />
              </div>

              {metaParts.length > 0 ? (
                <p className={`${styles.heroMeta} ${styles.rise}`} style={{ "--d": "250ms" }}>
                  {metaParts.join(" · ")}
                </p>
              ) : null}
            </div>

            <div className={styles.showcaseCol}>
              <HeroShowcase
                set={set}
                chaseCards={chaseCards}
                sealedProducts={sealedProducts}
                cardsAsOf={cardsAsOf}
              />
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
