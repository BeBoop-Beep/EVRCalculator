import Image from "next/image";
import Link from "next/link";

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
  const src = set?.logoUrl || set?.symbolUrl;
  return src ? <img className={className} src={src} alt={`${set.name} set logo`} loading="lazy" /> : <span className={styles.markFallback} aria-hidden="true">#{set?.rank || "1"}</span>;
}

function Metrics({ set }) {
  return (
    <dl className={styles.metricGrid}>
      <div><dt>Overall RIP</dt><dd><Score value={set?.score} /></dd></div>
      <div><dt>Financial RIP</dt><dd><Score value={set?.financialRipScore} /></dd></div>
      <div><dt>Expected Value</dt><dd><Money value={set?.meanValue} /></dd></div>
      <div><dt>Typical Opening</dt><dd><Money value={set?.medianValue} /></dd></div>
    </dl>
  );
}

function Theater({ set, rows, boosterPackImage }) {
  return (
    <div className={styles.theater}>
      {rows.slice(1, 3).map((row, index) => (
        <div key={row.key} className={`${styles.rankPlane} ${index === 0 ? styles.rankTwo : styles.rankThree}`} aria-hidden="true">
          <span>#{row.rank}</span><strong>{row.name}</strong>
        </div>
      ))}
      <div className={styles.productGlow} aria-hidden="true" />
      <div className={styles.productStage}>
        {boosterPackImage ? (
          <Image
            className={styles.packImage}
            src={boosterPackImage.src}
            width={boosterPackImage.width}
            height={boosterPackImage.height}
            sizes="(max-width: 767px) 84vw, 480px"
            priority
            alt={`${set?.name || "Featured Pokémon"} booster pack`}
          />
        ) : (
          <div className={styles.logoStage}><SetMark set={set} className={styles.heroLogo} /><span>Local pack image unavailable</span></div>
        )}
      </div>
    </div>
  );
}

export default function RankingTheaterHomepage({ set, rankingRows = [], boosterPackImage = null, marketContext = null }) {
  const landmarks = [
    ["P05", set?.p05Value], ["P50", set?.medianValue], ["P95", set?.p95Value],
    ["P99", set?.p99Value], ["Max", set?.maxValue],
  ];

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
            <div className={styles.mobileTheater}><Theater set={set} rows={rankingRows} boosterPackImage={boosterPackImage} /></div>
            <Metrics set={set} />
            <Link className={styles.primaryCta} href="/Explore/rip-statistics">See Full Rankings <span aria-hidden="true">→</span></Link>
          </div>
          <div className={styles.desktopTheater}><Theater set={set} rows={rankingRows} boosterPackImage={boosterPackImage} /></div>
        </div>
      </section>

      <section className={styles.section} aria-labelledby="best-sets-heading">
        <div className={styles.shell}>
          <div className={styles.sectionHead}><p className={styles.eyebrow}>Published Overall RIP V7</p><h2 id="best-sets-heading">BEST SETS TO RIP RIGHT NOW</h2></div>
          {rankingRows.length ? <ol className={styles.rankingBoard}>
            {rankingRows.map((row) => <li key={row.key}><Link href={row.href} className={styles.rankingRow}>
              <span className={styles.rank}>#{row.rank}</span><SetMark set={row} className={styles.rowLogo} />
              <span className={styles.rowName}><strong>{row.name}</strong><small>{row.tier ? `${row.tier} tier` : "Tier unavailable"}</small></span>
              <span className={styles.rowMetric}><small>Overall RIP</small><Score value={row.score} /></span>
              <span className={styles.rowMetric}><small>Financial RIP</small><Score value={row.financialRipScore} /></span>
              <span className={`${styles.rowMetric} ${styles.optionalMetric}`}><small>Pack price</small><Money value={row.packCost} /></span>
            </Link></li>)}
          </ol> : <p className={styles.unavailable}>Published rankings are refreshing.</p>}
          <Link className={styles.textCta} href="/Explore/rip-statistics">See Full Rankings →</Link>
        </div>
      </section>

      <section className={`${styles.section} ${styles.proofSection}`} aria-labelledby="simulation-heading">
        <div className={styles.shell}>
          <div className={styles.sectionHead}><p className={styles.eyebrow}>Opening outcome profile</p><h2 id="simulation-heading">What does one million simulated openings actually look like?</h2>
            <p>{set?.simulationCount ? `${integer.format(set.simulationCount)} simulated openings for ${set.name}.` : "Simulation count is unavailable in the current published payload."}</p></div>
          <div className={styles.proofGrid}>
            <div className={styles.proofCards}>
              <article><span>Normal / typical</span><h3><Money value={set?.medianValue} /></h3><p>The median (P50): half of modeled openings land below this value and half above.</p></article>
              <article><span>Average / expected</span><h3><Money value={set?.meanValue} /></h3><p>The mean includes rare high-value hits, so it can sit above what a typical opening returns.</p></article>
            </div>
            <div className={styles.tailCard}><p className={styles.tailTitle}>Outcome landmarks</p><ol>
              {landmarks.map(([label, value]) => <li key={label}><span>{label}</span><i aria-hidden="true" /><strong><Money value={value} /></strong></li>)}
            </ol><p className={styles.tailNote}>Percentile thresholds are shown as published values. Expected value is kept separate because a mean is not a percentile.</p></div>
          </div>
        </div>
      </section>

      <section className={`${styles.section} ${styles.personalSection}`} aria-labelledby="personal-heading">
        <div className={`${styles.shell} ${styles.personal}`}><div><p className={styles.eyebrow}>Personal RIP</p><h2 id="personal-heading">Your best set might be different.</h2><p>The public ranking answers “best overall opening profile.” Personal RIP is being built to account for the price you can actually buy at, your budget, the Pokémon you care about, and your opening preferences.</p></div>
          <WaitlistCta source="landing_personal_rip" label="Join the Personal RIP beta" variant="primary" />
        </div>
      </section>

      <MethodologySection marketContext={marketContext} methodologyHref={set?.ripScoreHref || "/Explore/rip-statistics"} />
    </>
  );
}
