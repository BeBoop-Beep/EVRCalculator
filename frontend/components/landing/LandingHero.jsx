import Image from "next/image";
import Link from "next/link";

import { getInterpretationBadgeStyle } from "@/lib/explore/interpretationTone";
import HeroWaitlistForm from "@/components/landing/HeroWaitlistForm";
import styles from "./LandingHero.module.css";

const currencyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const dateFormatter = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  timeZone: "UTC",
});

function formatAsOf(isoDate) {
  if (!isoDate) return null;
  const parsed = new Date(`${isoDate}T00:00:00Z`);
  return Number.isNaN(parsed.getTime()) ? null : dateFormatter.format(parsed);
}

function getInitials(name) {
  const words = String(name || "")
    .split(/\s+/)
    .filter(Boolean);
  if (words.length === 0) return "PK";
  return words
    .slice(0, 2)
    .map((word) => word[0])
    .join("")
    .toUpperCase();
}

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
 * Midground texture, not a reading. Abstract on purpose — no axis, no scale, no
 * labels — so nothing here can be mistaken for a published number.
 */
function SignalTrace() {
  return (
    <svg className={styles.layerSignal} viewBox="0 0 1200 620" preserveAspectRatio="none" aria-hidden="true">
      <path
        d="M0 470 L120 452 L240 486 L360 404 L480 428 L600 336 L720 372 L840 268 L960 296 L1080 196 L1200 224"
        fill="none"
        stroke="rgba(71,183,145,0.28)"
        strokeWidth="1.5"
      />
      <path
        d="M0 546 L150 534 L300 552 L450 512 L600 528 L750 486 L900 498 L1050 456 L1200 466"
        fill="none"
        stroke="rgba(150,200,230,0.13)"
        strokeWidth="1"
      />
    </svg>
  );
}

function SpotlightPanel({ spotlight }) {
  if (!spotlight) {
    return (
      <aside className={`${styles.panel} ${styles.rise}`} style={{ "--d": "260ms" }}>
        <p className={styles.panelHead}>
          <span className={styles.liveDot} aria-hidden="true" />
          Live set intelligence
        </p>
        <p className={styles.panelNote}>
          Set rankings are refreshing. Open Explore for the full ranked table.
        </p>
        <Link href="/Explore" className={styles.panelCta}>
          Explore set rankings
          <Arrow />
        </Link>
      </aside>
    );
  }

  const tierStyle = spotlight.tier ? getInterpretationBadgeStyle({ rankTier: spotlight.tier }) : null;
  const asOf = formatAsOf(spotlight.setValueAsOf);
  const logo = spotlight.logoUrl || spotlight.symbolUrl;

  return (
    <aside className={`${styles.panel} ${styles.rise}`} style={{ "--d": "260ms" }}>
      <p className={styles.panelHead}>
        <span className={styles.liveDot} aria-hidden="true" />
        Live set intelligence
      </p>

      <div className={styles.panelSet}>
        <div className={styles.setMark}>
          {logo ? (
            /* Set logos are remote and this project has no next/image remote
               patterns configured — the same plain <img> Explore uses. */
            // eslint-disable-next-line @next/next/no-img-element
            <img src={logo} alt="" className={styles.setMarkImg} decoding="async" />
          ) : (
            <span className={styles.setMarkFallback}>{getInitials(spotlight.name)}</span>
          )}
        </div>
        <div>
          <p className={styles.setName}>{spotlight.name}</p>
          {spotlight.era ? <p className={styles.setEra}>{spotlight.era}</p> : null}
        </div>
      </div>

      <div className={styles.metric}>
        <span className={styles.metricLabel}>{spotlight.scoreLabel}</span>
        <div className={styles.scoreRow}>
          <span className={styles.score}>{spotlight.score.toFixed(1)}</span>
          <span className={styles.scoreMeta}>
            {spotlight.tier ? (
              <span className={styles.tierPill} style={tierStyle || undefined}>
                {spotlight.tier} tier
              </span>
            ) : null}
            {spotlight.rank !== null ? (
              <span className={styles.rankNote}>
                Rank #{spotlight.rank}
                {spotlight.cohortSize !== null ? ` of ${spotlight.cohortSize}` : ""}
              </span>
            ) : null}
          </span>
        </div>
      </div>

      {spotlight.setValue !== null ? (
        <div className={styles.metric}>
          <span className={styles.metricLabel}>Set value</span>
          <div className={styles.valueRow}>
            <span className={styles.value}>{currencyFormatter.format(spotlight.setValue)}</span>
            {asOf ? <span className={styles.valueAsOf}>as of {asOf}</span> : null}
          </div>
        </div>
      ) : null}

      <Link href={spotlight.href} className={styles.panelCta}>
        View set intelligence
        <Arrow />
      </Link>
    </aside>
  );
}

export default function LandingHero({ spotlight = null, ranked = [] }) {
  return (
    <section className={styles.stage} aria-labelledby="landing-hero-headline">
      <div className={styles.stageGlow} aria-hidden="true" />

      <div className={styles.shell}>
        <div className={styles.frame}>
          <div className={`${styles.layer} ${styles.layerBase}`} aria-hidden="true" />
          <div className={`${styles.layer} ${styles.layerGrid}`} aria-hidden="true" />

          {/* The mark is the scene's light source: the glow is registered to the
              silhouette, and every highlight in the frame falls off from here. */}
          <div className={`${styles.markLayer} ${styles.markGlow}`} aria-hidden="true" />
          <div className={`${styles.markLayer} ${styles.markCrisp}`} aria-hidden="true">
            <Image
              src="/images/inDex.png"
              alt=""
              width={760}
              height={760}
              sizes="(max-width: 900px) 104vw, 760px"
              className={styles.markImg}
              priority
            />
          </div>
          <div className={`${styles.markLayer} ${styles.markTint}`} aria-hidden="true" />

          <div className={`${styles.layer} ${styles.layerRake}`} aria-hidden="true" />
          <div className={styles.layer} aria-hidden="true">
            <SignalTrace />
          </div>
          <div className={`${styles.layer} ${styles.layerVeil}`} aria-hidden="true" />

          <div className={styles.content}>
            <div className={styles.col}>
              <div className={`${styles.lockup} ${styles.rise}`}>
                <div className={styles.wordmark}>
                  <Image
                    src="/images/inDex_wm.png"
                    alt="inDex"
                    width={560}
                    height={560}
                    sizes="240px"
                    className={styles.wordmarkImg}
                    priority
                  />
                </div>
                <span className={styles.lockupRule} aria-hidden="true" />
                <p className={styles.eyebrow}>Collectible intelligence</p>
              </div>

              <h1 id="landing-hero-headline" className={`${styles.headline} ${styles.rise}`} style={{ "--d": "90ms" }}>
                Know what&rsquo;s
                <br className={styles.breakNarrow} />{" "}
                <span className={styles.headlineAccent}>worth opening</span>
                <br />
                before you rip.
              </h1>

              <p className={`${styles.lede} ${styles.rise}`} style={{ "--d": "160ms" }}>
                We simulate every sealed set against live market prices and score what comes
                out of the pack. Check the value, the tier and the rank before you spend.
              </p>

              <div className={styles.rise} style={{ "--d": "220ms" }}>
                <HeroWaitlistForm />
              </div>
            </div>

            <SpotlightPanel spotlight={spotlight} />
          </div>
        </div>

        {ranked.length > 0 ? (
          <nav className={`${styles.strip} ${styles.rise}`} style={{ "--d": "340ms" }} aria-label="Next ranked sets">
            <span className={styles.stripLabel}>Ranked next</span>
            {ranked.map((entry) => (
              <Link key={entry.key} href={entry.href} className={styles.stripItem}>
                <span className={styles.stripRank}>#{entry.rank}</span>
                {entry.name}
                <span className={styles.stripScore}>{entry.score.toFixed(1)}</span>
              </Link>
            ))}
          </nav>
        ) : null}
      </div>
    </section>
  );
}
