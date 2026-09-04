"use client";
import { useId, useMemo, useState } from "react";
import InfoPopover from "@/components/ui/InfoPopover";
import OpeningOutcomeProfileSection from "./simulation-evidence/OpeningOutcomeProfileSection.jsx";
import {
  formatEvRepPacks,
  formatEvRepPercent,
  selectEvRepresentativenessPublicV1,
} from "./evRepresentativenessSelector.mjs";
import { selectSimulationFullReport } from "./simulationFullReportSelector.mjs";
import styles from "./RipDecisionPage.module.css";
import { ANALYTICAL_ACTION_CLASS } from "@/components/ui/analyticalInteraction.mjs";

const currency = (value) =>
  Number.isFinite(Number(value))
    ? new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
      }).format(Number(value))
    : "Not confirmed";

function EvGapExplanation({
  summary,
  evRepresentativeness,
  calculationRunId,
  canViewAdvanced,
}) {
  const evRep = selectEvRepresentativenessPublicV1(
    evRepresentativeness,
    calculationRunId,
  );
  const expectedValue = Number(summary?.meanValue ?? summary?.mean_value);
  const typicalValue = Number(summary?.medianValue ?? summary?.median_value);
  const capture =
    Number.isFinite(expectedValue) &&
    expectedValue > 0 &&
    Number.isFinite(typicalValue)
      ? typicalValue / expectedValue
      : null;
  const scaleMax = Math.max(
    Number.isFinite(typicalValue) ? typicalValue : 0,
    Number.isFinite(expectedValue) ? expectedValue : 0,
  );
  const comparisonRows = [
    { key: "typical", label: "Typical Opening", value: typicalValue },
    { key: "expected", label: "Expected Value", value: expectedValue },
  ];
  return (
    <section
      className={styles.evGapSection}
      aria-labelledby="simulation-ev-gap-heading"
    >
      <h3 id="simulation-ev-gap-heading">
        Why Is Expected Value Higher Than a Typical Opening?
      </h3>
      <p>
        Expected Value and a typical opening describe two different parts of the
        modeled distribution.
      </p>
      <div
        className={styles.evGapComparison}
        data-ev-gap-comparison
        aria-label="Typical Opening compared with Expected Value on the same scale"
      >
        {comparisonRows.map((row) => {
          const width =
            scaleMax > 0 && Number.isFinite(row.value)
              ? `${Math.max(0, (row.value / scaleMax) * 100)}%`
              : "0%";
          return (
            <div className={styles.evGapRow} key={row.key}>
              <div className={styles.evGapLabel}>
                <span>{row.label}</span>
                <strong>{currency(row.value)}</strong>
              </div>
              <div className={styles.evGapTrack} aria-hidden="true">
                <i data-series={row.key} style={{ width }} />
              </div>
            </div>
          );
        })}
      </div>
      {capture !== null ? (
        <p className={styles.evCapture}>
          The typical modeled pack captures{" "}
          <strong>{formatEvRepPercent(capture)}</strong> of long-run EV.
        </p>
      ) : null}
      <p className={styles.evSkew}>
        Rare high-value openings pull the average upward, so Expected Value can
        sit well above what a typical pack returns.
      </p>
      {evRep?.realizationHorizon ? (
        <p className={styles.evTailNote} data-ev-realization-headline>
          About {formatEvRepPercent(evRep.realizationHorizon.openerProbability)} of
          modeled openers reach at least{" "}
          {formatEvRepPercent(evRep.realizationHorizon.targetEvRatio)} of this
          set&apos;s long-run EV by{" "}
          <strong>{formatEvRepPacks(evRep.realizationHorizon.packCount)}</strong>.
        </p>
      ) : null}
      {canViewAdvanced && evRep?.top1OutcomeEvShare != null ? (
        <p className={styles.evTailNote}>
          The best 1% of modeled openings account for{" "}
          <strong>{formatEvRepPercent(evRep.top1OutcomeEvShare)}</strong> of
          total Expected Value.
        </p>
      ) : null}
    </section>
  );
}

export default function SimulationFullReport({
  canonical,
  summary,
  percentiles,
  evRepresentativeness = null,
  openingOutcomeProfile = null,
  calculationRunId = null,
  canViewAdvanced = false,
}) {
  const [open, setOpen] = useState(false);
  const generatedId = useId();
  const panelId = `simulation-full-report-${generatedId.replaceAll(":", "")}`;
  const report = useMemo(
    () => selectSimulationFullReport({ canonical, summary, percentiles }),
    [canonical, summary, percentiles],
  );
  if (!report.available) return null;
  return (
    <div data-simulation-full-report className={styles.fullReportDisclosure}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((v) => !v)}
        className={`${styles.fullReportButton} ${ANALYTICAL_ACTION_CLASS}`}
      >
        <span>
          <strong>
            {open
              ? "Hide Full Simulation Report"
              : canViewAdvanced
                ? "View Full Simulation Report"
                : "What Happens When You Open a Pack?"}
          </strong>
          <small>
            {canViewAdvanced
              ? "Outcome evidence and why EV differs from a typical opening"
              : "The basic modeled outcome profile"}
          </small>
        </span>
        <span aria-hidden="true">{open ? "↑" : "→"}</span>
      </button>
      {open ? (
        <div id={panelId} className={styles.fullReportPanel}>
          <p className={styles.fullReportIntro}>
            These probabilities describe modeled opening outcomes; they are not
            guarantees for an individual pack.
          </p>
          <OpeningOutcomeProfileSection
            openingOutcomeProfile={openingOutcomeProfile}
            calculationRunId={calculationRunId}
            headingId={`${panelId}-outcomes`}
            canViewAdvanced={canViewAdvanced}
          />
          <EvGapExplanation
            summary={summary}
            evRepresentativeness={evRepresentativeness}
            calculationRunId={calculationRunId}
            canViewAdvanced={canViewAdvanced}
          />
          {!canViewAdvanced ? (
            <div className={styles.premiumTeaser}>
              <strong>Go deeper with Index Plus</strong>
              <p>
                Unlock EV reliability by pack count, downside, upside, tail and
                distribution diagnostics.
              </p>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export function SimulationDiagnostics({ canonical, summary, percentiles }) {
  const report = useMemo(
    () => selectSimulationFullReport({ canonical, summary, percentiles }),
    [canonical, summary, percentiles],
  );
  if (!report.available)
    return (
      <p className={styles.unavailableNote}>
        Advanced simulation diagnostics are unavailable for this run.
      </p>
    );
  return (
    <div className={styles.fullReportGroups}>
      {report.groups.map((g) => (
        <section key={g.key} className={styles.fullReportGroup}>
          <header>
            <h3>{g.title}</h3>
            <span>{g.classification}</span>
          </header>
          <dl className={styles.fullReportGrid}>
            {g.rows.map((r) => (
              <div key={r.key} className={styles.fullReportRow}>
                <dt>
                  <span>{r.label}</span>
                  {r.help ? <InfoPopover text={r.help} /> : null}
                </dt>
                <dd>{r.value}</dd>
              </div>
            ))}
          </dl>
        </section>
      ))}
    </div>
  );
}
