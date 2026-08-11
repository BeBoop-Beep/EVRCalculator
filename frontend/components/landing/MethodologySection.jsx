import Link from "next/link";

import { formatFullDate } from "./landingFormat.mjs";
import { Arrow } from "./previews/previewPrimitives";
import styles from "./landing.module.css";

/**
 * Section 5 — how the numbers are produced, compressed.
 *
 * The first pass gave this the same full-width heading block, three-column grid
 * and generous padding as every other section, and it filled most of a viewport
 * with mostly background. It is now one band: heading and steps side by side,
 * figures inline, disclaimer secondary.
 *
 * The figures are read from the same payload the previews use and render ONLY
 * when present — no hardcoded set count, no invented cadence.
 */
const STEPS = [
  {
    index: "01",
    title: "Market data",
    copy: "Current pricing and set information establish the market context.",
  },
  {
    index: "02",
    title: "Opening simulations",
    copy: "Pack and set models test possible opening outcomes.",
  },
  {
    index: "03",
    title: "Intelligence",
    copy: "inDex turns the results into scores, trends, decision signals, and comparisons.",
  },
];

export default function MethodologySection({ marketContext, methodologyHref = "/Research" }) {
  const marketDate = formatFullDate(marketContext?.marketDate);
  const rankedSets = marketContext?.rankedSetCount ?? null;

  const facts = [
    rankedSets ? { key: "sets", value: String(rankedSets), label: "Ranked sets published" } : null,
    marketDate ? { key: "market", value: marketDate, label: "Latest market snapshot" } : null,
  ].filter(Boolean);

  return (
    <section className={`${styles.section} ${styles.sectionMethod}`} aria-labelledby="landing-method-heading">
      <div className={styles.shell}>
        <div className={styles.method}>
          <div className={styles.methodIntro}>
            <p className={styles.sectionEyebrow}>Methodology</p>
            <h2 id="landing-method-heading" className={styles.methodTitle}>
              Built from market data. Tested through simulation.
            </h2>

            {facts.length > 0 ? (
              <div className={styles.facts}>
                {facts.map((fact) => (
                  <p key={fact.key} className={styles.fact}>
                    <span className={styles.factValue}>{fact.value}</span>
                    <span className={styles.factLabel}>{fact.label}</span>
                  </p>
                ))}
              </div>
            ) : null}

            {/* General methodology belongs to the global Research surface;
                set-specific evidence remains on each set's RIP page. */}
            <Link href={methodologyHref} className={styles.methodLink}>
              Read the Research
              <Arrow />
            </Link>
          </div>

          <ol className={styles.steps}>
            {STEPS.map((step) => (
              <li key={step.index} className={styles.step}>
                <span className={styles.stepIndex}>{step.index}</span>
                <h3 className={styles.stepTitle}>{step.title}</h3>
                <p className={styles.stepCopy}>{step.copy}</p>
              </li>
            ))}
          </ol>
        </div>

        <p className={styles.disclaimer}>
          Simulation results are modeled outcomes from current market inputs, not predictions of what
          a specific pack will return and not financial advice.
        </p>
      </div>
    </section>
  );
}
