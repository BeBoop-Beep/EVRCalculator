import Image from "next/image";
import Link from "next/link";

import RipDistributionChart from "@/components/explore/RipDistributionChart";
import { SET_LOGO_WIDTH, optimizedImageUrl } from "@/lib/images/remoteImageDelivery.mjs";
import WaitlistCta from "./WaitlistCta";
import MethodologySection from "./MethodologySection";
import styles from "./rankingTheater.module.css";

const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });
const integer = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

function Score({ value }) {
  return value === null || value === undefined ? <span aria-label="Unavailable">&mdash;</span> : Number(value).toFixed(1);
}

function Money({ value }) {
  return value === null || value === undefined ? <span aria-label="Unavailable">&mdash;</span> : money.format(value);
}

function SetMark({ set, className = "" }) {
  // SET_LOGO_WIDTH for every slot this renders — the hero stage (up to 190 px
  // tall), the supporting visual and the 52 px ranking-row mark can all show
  // the same set on one page, so a single width keeps that a single request.
  const src = optimizedImageUrl(set?.logoUrl || set?.symbolUrl, SET_LOGO_WIDTH);
  return src ? <img className={className} src={src} alt={`${set.name} set logo`} loading="lazy" /> : <span className={styles.markFallback} aria-hidden="true">#{set?.rank || "1"}</span>;
}

function SupportingSetVisual({ row }) {
  return (
    <div className={styles.supportVisual}>
      <SetMark set={row} className={styles.supportLogo} />
    </div>
  );
}

function Metrics({ set }) {
  return (
    <dl className={styles.metricGrid}>
      <div><dt>Set RIP</dt><dd><Score value={set?.score} /></dd></div>
      <div><dt>Expected Value</dt><dd><Money value={set?.meanValue} /></dd></div>
      <div><dt>Typical Opening</dt><dd><Money value={set?.medianValue} /></dd></div>
    </dl>
  );
}

function HeroVisual({ set, heroVisual }) {
  if (heroVisual?.type === "pack" && heroVisual.asset) {
    return (
      <Image
        className={styles.packImage}
        src={heroVisual.asset.src}
        width={heroVisual.asset.width}
        height={heroVisual.asset.height}
        sizes="(max-width: 767px) 84vw, 480px"
        priority
        alt={`${set?.name || "Featured Pokémon"} booster pack`}
      />
    );
  }
  if (heroVisual?.type === "hero-image" && heroVisual.src) {
    const optimizedSrc = optimizedImageUrl(heroVisual.src, SET_LOGO_WIDTH);
    return (
      // eslint-disable-next-line @next/next/no-img-element -- remote hero art is already delivered pre-optimized by optimizedImageUrl
      <img
        className={styles.packImage}
        src={optimizedSrc || heroVisual.src}
        loading="eager"
        alt={`${set?.name || "Featured set"} artwork`}
      />
    );
  }
  return <div className={styles.logoStage}><SetMark set={set} className={styles.heroLogo} /></div>;
}

function Theater({ set, rows, heroVisual }) {
  return (
    <div className={styles.theater}>
      {rows.slice(1, 3).map((row, index) => (
        <div key={row.key} className={`${styles.rankPlane} ${index === 0 ? styles.rankTwo : styles.rankThree}`} aria-label={`#${row.rank} ${row.name}`} title={`#${row.rank} ${row.name}`}>
          <div className={styles.supportLockup}>
            <SupportingSetVisual row={row} />
            <span className={styles.supportRank}>#{row.rank}</span>
          </div>
        </div>
      ))}
      <div className={styles.productGlow} aria-hidden="true" />
      <Link
        className={styles.productStage}
        href={set?.href || "/Explore/rip-statistics"}
        aria-label={`View ${set?.name || "featured set"} RIP analysis`}
      >
        <HeroVisual set={set} heroVisual={heroVisual} />
      </Link>
    </div>
  );
}

function DistributionVisual({ distribution }) {
  if (!distribution?.bins?.length && !distribution?.thresholdBins?.length) {
    return <p className={styles.distributionUnavailable}>Measured distribution bins are unavailable for this set.</p>;
  }
  return (
    <div className={styles.outcomeLayout}>
      <dl className={styles.outcomeStats}>
        {distribution.markers.filter((marker) => !marker.locked && marker.value !== null).map((marker) => <div key={marker.key}>
          <dt>{marker.label}</dt>
          <dd>{money.format(marker.value)}</dd>
        </div>)}
      </dl>
      <div className={styles.distributionFigure}>
        <RipDistributionChart
          bins={distribution.bins}
          thresholdBins={distribution.thresholdBins}
          markers={distribution.markers}
          showTitle={false}
          flush
        />
      </div>
    </div>
  );
}

export default function RankingTheaterHomepage({ set, rankingRows = [], heroVisual = null, distribution = null, marketContext = null }) {
  return (
    <>
      <section className={styles.hero} aria-labelledby="landing-hero-headline">
        <div className={styles.heroShell}>
          <div className={styles.heroCopy}>
            <p className={styles.eyebrow}>Pokémon TCG opening intelligence</p>
            <h1 id="landing-hero-headline">WHAT&rsquo;S ACTUALLY<br />WORTH RIPPING?</h1>
            <p className={styles.lede}>One million simulated openings. Current market prices. One ranking.</p>
            <div className={styles.answer}>
              <span>#1&nbsp; BEST SET TO RIP RIGHT NOW</span>
              <strong>{set?.name || "Ranking temporarily unavailable"}</strong>
            </div>
            <div className={styles.mobileTheater}><Theater set={set} rows={rankingRows} heroVisual={heroVisual} /></div>
            <Metrics set={set} />
            <Link className={styles.primaryCta} href="/Rankings">See Full Rankings <span aria-hidden="true">→</span></Link>
          </div>
          <div className={styles.desktopTheater}><Theater set={set} rows={rankingRows} heroVisual={heroVisual} /></div>
        </div>
      </section>

      <section className={styles.section} aria-labelledby="best-sets-heading">
        <div className={styles.shell}>
          <div className={styles.sectionHead}><p className={styles.eyebrow}>Published Set RIP ranking</p><h2 id="best-sets-heading">BEST SETS TO RIP RIGHT NOW</h2></div>
          {rankingRows.length ? <ol className={styles.rankingBoard}>
            {rankingRows.map((row) => <li key={row.key}><Link href={row.href} className={styles.rankingRow}>
              <span className={styles.rank}>#{row.rank}</span><SetMark set={row} className={styles.rowLogo} />
              <span className={styles.rowName}><strong>{row.name}</strong><small>{row.tier ? `${row.tier} tier` : "Tier unavailable"}</small></span>
              <span className={styles.rowMetric}><small>Set RIP</small><Score value={row.score} /></span>
              <span className={`${styles.rowMetric} ${styles.optionalMetric}`}><small>Pack price</small><Money value={row.packCost} /></span>
            </Link></li>)}
          </ol> : <p className={styles.unavailable}>Published rankings are refreshing.</p>}
          <Link className={styles.textCta} href="/Rankings">See Full Rankings →</Link>
        </div>
      </section>

      <section className={`${styles.section} ${styles.proofSection}`} aria-labelledby="simulation-heading">
        <div className={styles.shell}>
          <div className={styles.sectionHead}><p className={styles.eyebrow}>Opening outcome profile</p><h2 id="simulation-heading">What does one million simulated openings actually look like?</h2>
            <p>{distribution?.simulationCount ? `${integer.format(distribution.simulationCount)} simulated openings for ${set?.name}. Most openings cluster on the left; farther right means rarer, more valuable outcomes.` : "Simulation count is unavailable in the current published payload."}</p></div>
          <DistributionVisual distribution={distribution} />
        </div>
      </section>

      <section className={`${styles.section} ${styles.personalSection}`} aria-labelledby="personal-heading">
        <div className={`${styles.shell} ${styles.personal}`}><div><p className={styles.eyebrow}>Personal RIP</p><h2 id="personal-heading">Your best set might be different.</h2><p>The public ranking answers “best overall opening profile.” Personal RIP is being built to account for the price you can actually buy at, your budget, the Pokémon you care about, and your opening preferences.</p></div>
          <WaitlistCta source="landing_personal_rip" label="Join the Personal RIP beta" variant="primary" />
        </div>
      </section>

      <MethodologySection marketContext={marketContext} methodologyHref="/Articles/how-rip-score-works" />
    </>
  );
}
