"use client";
import { useId, useMemo, useState } from "react";
import InfoPopover from "@/components/ui/InfoPopover";
import { selectSimulationFullReport } from "./simulationFullReportSelector.mjs";
import { formatEvRepPacks, formatEvRepPercent, selectEvRepresentativenessPublicV1 } from "./evRepresentativenessSelector.mjs";
import { formatOutcomePercent, selectOpeningOutcomeProfileV1 } from "./openingOutcomeProfileSelector.mjs";
import styles from "./RipDecisionPage.module.css";

export default function SimulationFullReport({ canonical, summary, percentiles, evRepresentativeness = null, openingOutcomeProfile = null, calculationRunId = null }) {
  const [open, setOpen] = useState(false);
  const generatedId = useId();
  const panelId = `simulation-full-report-${generatedId.replaceAll(":", "")}`;
  const report = useMemo(() => selectSimulationFullReport({ canonical, summary, percentiles }), [canonical, summary, percentiles]);
  const evRep = useMemo(() => selectEvRepresentativenessPublicV1(evRepresentativeness, calculationRunId), [evRepresentativeness, calculationRunId]);
  const outcomeProfile = useMemo(() => selectOpeningOutcomeProfileV1(openingOutcomeProfile, calculationRunId), [openingOutcomeProfile, calculationRunId]);
  if (!report.available) return null;
  return <div data-simulation-full-report className={styles.fullReportDisclosure}>
    <button type="button" aria-expanded={open} aria-controls={panelId} onClick={() => setOpen((value) => !value)} className={`${styles.disclosureButton} ${styles.fullReportButton}`}>
      <span><strong>View Full Simulation Report</strong><small>All modeled outcomes and distribution statistics</small></span><span aria-hidden="true">{open ? "−" : "+"}</span>
    </button>
    {open ? <div id={panelId} className={styles.fullReportPanel}>
      <p className={styles.fullReportIntro}>Financial RIP is built from six scored dimensions. These statistics include both the measurements behind those dimensions and additional simulation diagnostics.</p>
      <section aria-labelledby={`${panelId}-outcome-breakdown`} className={styles.outcomeProfileSection}>
        <header><div><h3 id={`${panelId}-outcome-breakdown`}>Outcome Breakdown</h3><p>Where do modeled openings actually land relative to opening cost?</p></div><InfoPopover text="Each range shows the share of simulated openings returning that portion of opening cost in gross modeled card market value. Selling fees, grading and liquidity are not included." /></header>
        {outcomeProfile ? <><div className={styles.outcomeProfileBar} aria-hidden="true">{outcomeProfile.buckets.map((row) => <span key={row.key} style={{ flexGrow: Math.max(row.probability, .002) }} />)}</div>
          <dl className={styles.outcomeProfileRows}>{outcomeProfile.buckets.map((row) => <div key={row.key}><dt><span>{row.label}</span><small>{row.interpretation}</small></dt><dd>{formatOutcomePercent(row.probability)}</dd></div>)}</dl>
          <div className={styles.outcomeProfileCallouts}>{outcomeProfile.cumulativeProbabilities.map((row) => <div key={row.key}><span>{row.label}</span><strong>{formatOutcomePercent(row.probability)}</strong></div>)}</div></> : <p className={styles.outcomeProfileUnavailable}>An exact same-run outcome breakdown is not available for this simulation.</p>}
      </section>
      {evRep ? <section aria-labelledby={`${panelId}-ev-representativeness`} className={styles.evRepSection}>
        <header><div><h3 id={`${panelId}-ev-representativeness`}>How Representative Is EV?</h3><p>EV is a long-run average. These metrics show how closely realistic modeled openings tend to resemble it.</p></div><InfoPopover text="Estimated from one million modeled outcomes at current market prices. Horizons assume independent pack draws and are not recommendations to open that many packs." /></header>
        <dl className={styles.evRepMetrics}>
          <div><dt>Typical Capture</dt><dd>{formatEvRepPercent(evRep.typicalCapture)}</dd><small>The typical modeled pack returns about {formatEvRepPercent(evRep.typicalCapture)} of this set&apos;s long-run Expected Value.</small></div>
          <div><dt>80% EV Horizon</dt><dd>{formatEvRepPacks(evRep.realizationHorizon?.packCount)}</dd><small>{evRep.realizationHorizon ? "Estimated packs before 80% of modeled openers realize at least 80% of EV." : "A confirmed horizon is not currently available."}</small></div>
          <div><dt>EV Convergence Horizon</dt><dd>{formatEvRepPacks(evRep.convergenceHorizon?.packCount)}</dd><small>{evRep.convergenceHorizon ? "Estimated packs before 80% of modeled opening averages fall within ±20% of EV." : "Independent confirmation did not establish a public horizon."}</small></div>
          <div><dt>Top 1% EV Contribution</dt><dd>{formatEvRepPercent(evRep.top1OutcomeEvShare)}</dd><small>The best 1% of modeled openings generate {formatEvRepPercent(evRep.top1OutcomeEvShare)} of total Expected Value.</small></div>
        </dl>
        {evRep.realizationByPackCount.length ? <div className={styles.evRepRealization}><h4>EV Realization by Opening Size</h4><p>Chance of realizing at least 80% of EV under the current model.</p><div role="table" aria-label="Chance of realizing at least 80 percent of Expected Value by pack count"><div role="row" className={styles.evRepTableHead}><span role="columnheader">Packs</span><span role="columnheader">Chance of ≥80% EV</span></div>{evRep.realizationByPackCount.map((row) => <div role="row" key={row.packCount} className={styles.evRepTableRow}><span role="cell">{row.packCount.toLocaleString("en-US")}</span><strong role="cell">{formatEvRepPercent(row.probabilityAtLeast80PercentEv)}</strong></div>)}</div></div> : null}
      </section> : null}
      <div className={styles.fullReportGroups}>{report.groups.map((group) => <section key={group.key} className={styles.fullReportGroup}>
        <header><h3>{group.title}</h3><span>{group.classification}</span></header>
        <dl className={styles.fullReportGrid}>{group.rows.map((item) => <div key={item.key} className={styles.fullReportRow}><dt><span>{item.label}</span>{item.help ? <InfoPopover text={item.help} /> : null}</dt><dd>{item.value}</dd></div>)}</dl>
      </section>)}</div>
    </div> : null}
  </div>;
}
