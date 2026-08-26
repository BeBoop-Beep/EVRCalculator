"use client";
import { useId, useMemo, useState } from "react";
import InfoPopover from "@/components/ui/InfoPopover";
import OpeningOutcomeProfileSection from "./simulation-evidence/OpeningOutcomeProfileSection.jsx";
import EvRepresentativenessSection from "./simulation-evidence/EvRepresentativenessSection.jsx";
import { selectSimulationFullReport } from "./simulationFullReportSelector.mjs";
import styles from "./RipDecisionPage.module.css";
import { ANALYTICAL_ACTION_CLASS } from "@/components/ui/analyticalInteraction.mjs";

export default function SimulationFullReport({ canonical, summary, percentiles, evRepresentativeness = null, openingOutcomeProfile = null, calculationRunId = null, canViewAdvanced = false }) {
  const [open, setOpen] = useState(false); const generatedId = useId();
  const panelId = `simulation-full-report-${generatedId.replaceAll(":", "")}`;
  const report = useMemo(() => selectSimulationFullReport({ canonical, summary, percentiles }), [canonical, summary, percentiles]);
  if (!report.available) return null;
  return <div data-simulation-full-report className={styles.fullReportDisclosure}>
    <button type="button" aria-expanded={open} aria-controls={panelId} onClick={() => setOpen((v) => !v)} className={`${styles.fullReportButton} ${ANALYTICAL_ACTION_CLASS}`}><span><strong>{open ? "Hide Full Simulation Report" : canViewAdvanced ? "View Full Simulation Report" : "What Happens When You Open a Pack?"}</strong><small>{canViewAdvanced ? "Outcome evidence and why EV differs from a typical opening" : "The basic modeled outcome profile"}</small></span><span aria-hidden="true">{open ? "↑" : "→"}</span></button>
    {open ? <div id={panelId} className={styles.fullReportPanel}><p className={styles.fullReportIntro}>These probabilities describe modeled opening outcomes; they are not guarantees for an individual pack.</p>
      <OpeningOutcomeProfileSection openingOutcomeProfile={openingOutcomeProfile} calculationRunId={calculationRunId} headingId={`${panelId}-outcomes`} canViewAdvanced={canViewAdvanced} />
      {canViewAdvanced ? <EvRepresentativenessSection summary={summary} percentiles={percentiles} evRepresentativeness={evRepresentativeness} calculationRunId={calculationRunId} headingId={`${panelId}-ev`} summaryOnly /> : <div className={styles.premiumTeaser}><strong>Go deeper with Index Plus</strong><p>Unlock EV reliability by pack count, downside, upside, tail and distribution diagnostics.</p></div>}</div> : null}
  </div>;
}

export function SimulationDiagnostics({ canonical, summary, percentiles }) {
  const report = useMemo(() => selectSimulationFullReport({ canonical, summary, percentiles }), [canonical, summary, percentiles]);
  if (!report.available) return <p className={styles.unavailableNote}>Advanced simulation diagnostics are unavailable for this run.</p>;
  return <div className={styles.fullReportGroups}>{report.groups.map((g) => <section key={g.key} className={styles.fullReportGroup}><header><h3>{g.title}</h3><span>{g.classification}</span></header><dl className={styles.fullReportGrid}>{g.rows.map((r) => <div key={r.key} className={styles.fullReportRow}><dt><span>{r.label}</span>{r.help ? <InfoPopover text={r.help} /> : null}</dt><dd>{r.value}</dd></div>)}</dl></section>)}</div>;
}
