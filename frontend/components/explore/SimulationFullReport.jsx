"use client";
import { useId, useMemo, useState } from "react";
import InfoPopover from "@/components/ui/InfoPopover";
import { selectSimulationFullReport } from "./simulationFullReportSelector.mjs";
import { formatEvRepPacks, formatEvRepPercent, selectEvRepresentativenessPublicV1 } from "./evRepresentativenessSelector.mjs";
import { buildOutcomeProfileViewModel, formatOutcomePercent, selectOpeningOutcomeProfileV1 } from "./openingOutcomeProfileSelector.mjs";
import styles from "./RipDecisionPage.module.css";

const currency = (value) => Number.isFinite(Number(value)) ? new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(Number(value)) : "Not confirmed";

export default function SimulationFullReport({ canonical, summary, percentiles, evRepresentativeness = null, openingOutcomeProfile = null, calculationRunId = null }) {
  const [open, setOpen] = useState(false); const generatedId = useId();
  const panelId = `simulation-full-report-${generatedId.replaceAll(":", "")}`;
  const report = useMemo(() => selectSimulationFullReport({ canonical, summary, percentiles }), [canonical, summary, percentiles]);
  const evRep = useMemo(() => selectEvRepresentativenessPublicV1(evRepresentativeness, calculationRunId), [evRepresentativeness, calculationRunId]);
  const profile = useMemo(() => selectOpeningOutcomeProfileV1(openingOutcomeProfile, calculationRunId), [openingOutcomeProfile, calculationRunId]);
  const outcome = useMemo(() => buildOutcomeProfileViewModel(profile), [profile]);
  if (!report.available) return null;
  const ev = Number(summary?.meanValue);
  const p50Row = (Array.isArray(percentiles) ? percentiles : []).find((row) => Number(row?.percentile ?? row?.p) === 50 || Number(row?.quantile) === .5);
  const p50 = Number(p50Row?.value ?? p50Row?.amount ?? summary?.median_value ?? summary?.medianValue);
  const scale = Math.max(Number.isFinite(ev) ? ev : 0, Number.isFinite(p50) ? p50 : 0);
  const realization36 = evRep?.realizationByPackCount?.find((row) => row.packCount === 36);
  return <div data-simulation-full-report className={styles.fullReportDisclosure}>
    <button type="button" aria-expanded={open} aria-controls={panelId} onClick={() => setOpen((v) => !v)} className={`${styles.disclosureButton} ${styles.fullReportButton}`}><span><strong>View Full Simulation Report</strong><small>All modeled outcomes and distribution statistics</small></span><span aria-hidden="true">{open ? "−" : "+"}</span></button>
    {open ? <div id={panelId} className={styles.fullReportPanel}><p className={styles.fullReportIntro}>Financial RIP is built from six scored dimensions. These statistics include the measurements behind those dimensions and additional simulation diagnostics.</p>
      <section className={styles.outcomeProfileSection} aria-labelledby={`${panelId}-outcomes`}><header><div><h3 id={`${panelId}-outcomes`}>What Happens When You Open a Pack?</h3><p>Where one million modeled pack openings landed relative to today&apos;s pack price.</p></div><InfoPopover text="Gross modeled card market value relative to pack cost. Selling fees, grading and liquidity are not included." /></header>
      {outcome ? <><div className={styles.outcomeHero}><strong>{formatOutcomePercent(outcome.groups[0].probability)}</strong><span>About {Math.round(outcome.groups[0].probability * 100)} out of 100 modeled packs return less than half the pack price.</span></div>
      <div className={styles.outcomeProfileBar} role="img" aria-label={outcome.groups.map((r) => `${r.label}: ${formatOutcomePercent(r.probability)}`).join("; ")}>{outcome.groups.map((r) => <span key={r.key} style={{ flexGrow: r.probability }}><i>{formatOutcomePercent(r.probability)}</i></span>)}<b style={{ left: `${(outcome.groups[0].probability + outcome.groups[1].probability) * 100}%` }}>PACK COST</b></div>
      <div className={styles.outcomeLegend}>{outcome.groups.map((r) => <span key={r.key}>{r.label}</span>)}</div><div className={styles.outcomeProfileCallouts}>{[["Under half back", outcome.groups[0].probability], ["Recover pack cost", outcome.groups[2].probability + outcome.groups[3].probability], ["Reach 2× or more", outcome.groups[3].probability]].map(([label, value]) => <div key={label}><span>{label}</span><strong>{formatOutcomePercent(value)}</strong></div>)}</div>
      <details className={styles.outcomeDetails}><summary>View full outcome breakdown</summary><dl>{outcome.details.map((r) => <div key={r.key}><dt>{r.label}<InfoPopover text={r.interpretation} /></dt><dd>{formatOutcomePercent(r.probability)}</dd></div>)}</dl></details></> : <p className={styles.outcomeProfileUnavailable}>An exact same-run outcome breakdown is not available for this simulation.</p>}</section>
      {evRep ? <section className={styles.evRepSection} aria-labelledby={`${panelId}-ev`}><header><div><h3 id={`${panelId}-ev`}>How Closely Does EV Match Real Openings?</h3><p>Expected Value is a long-run average. This shows how closely typical and repeated openings resemble it.</p></div><InfoPopover text="Estimated from one million modeled outcomes. Horizons assume independent pack draws and are not opening recommendations." /></header>
      <div className={styles.evComparison}>{[["Typical pack (P50)", p50], ["Long-run EV", ev]].map(([label, value]) => <div key={label}><span>{label}</span><div><i style={{ width: `${scale > 0 && Number.isFinite(value) ? value / scale * 100 : 0}%` }} /></div><strong>{currency(value)}</strong></div>)}</div>
      <p className={styles.evCapture}>The typical modeled pack captures <strong>{formatEvRepPercent(evRep.typicalCapture)}</strong> of EV.</p><h4 className={styles.evGapTitle}>Why can EV sit so far above the typical opening?</h4><p className={styles.evSkew}>The best 1% of modeled openings account for <strong>{formatEvRepPercent(evRep.top1OutcomeEvShare)}</strong> of total Expected Value.</p>
      <div className={styles.evMilestones}><div><span>36 packs</span><strong>{realization36 ? formatEvRepPercent(realization36.probabilityAtLeast80PercentEv) : "Not confirmed"}</strong><small>chance to realize at least 80% of EV</small></div><div><span>80% EV horizon</span><strong>{evRep.realizationHorizon ? formatEvRepPacks(evRep.realizationHorizon.packCount) : "Not confirmed"}</strong><small>80% of modeled openers average at least 80% of EV.</small></div><div><span>Convergence horizon</span><strong>{evRep.convergenceHorizon ? formatEvRepPacks(evRep.convergenceHorizon.packCount) : "Not confirmed"}</strong><small>80% of modeled openers finish within ±20% of EV.</small></div></div>
      {evRep.realizationByPackCount.length ? <details className={styles.evRepRealization}><summary>Explore other pack counts</summary><div role="table" aria-label="EV realization by pack count">{evRep.realizationByPackCount.map((r) => <div role="row" key={r.packCount} className={styles.evRepTableRow}><span role="cell">{r.packCount.toLocaleString("en-US")} packs</span><strong role="cell">{formatEvRepPercent(r.probabilityAtLeast80PercentEv)}</strong></div>)}</div></details> : null}</section> : null}
      <div className={styles.fullReportGroups}>{report.groups.map((g) => <section key={g.key} className={styles.fullReportGroup}><header><h3>{g.title}</h3><span>{g.classification}</span></header><dl className={styles.fullReportGrid}>{g.rows.map((r) => <div key={r.key} className={styles.fullReportRow}><dt><span>{r.label}</span>{r.help ? <InfoPopover text={r.help} /> : null}</dt><dd>{r.value}</dd></div>)}</dl></section>)}</div></div> : null}
  </div>;
}
