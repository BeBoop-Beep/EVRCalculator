"use client";
import { useId, useMemo, useState } from "react";
import InfoPopover from "@/components/ui/InfoPopover";
import { selectSimulationFullReport } from "./simulationFullReportSelector.mjs";
import styles from "./RipDecisionPage.module.css";

export default function SimulationFullReport({ canonical, summary, percentiles }) {
  const [open, setOpen] = useState(false);
  const generatedId = useId();
  const panelId = `simulation-full-report-${generatedId.replaceAll(":", "")}`;
  const report = useMemo(() => selectSimulationFullReport({ canonical, summary, percentiles }), [canonical, summary, percentiles]);
  if (!report.available) return null;
  return <div data-simulation-full-report className={styles.fullReportDisclosure}>
    <button type="button" aria-expanded={open} aria-controls={panelId} onClick={() => setOpen((value) => !value)} className={`${styles.disclosureButton} ${styles.fullReportButton}`}>
      <span><strong>View Full Simulation Report</strong><small>All modeled outcomes and distribution statistics</small></span><span aria-hidden="true">{open ? "−" : "+"}</span>
    </button>
    {open ? <div id={panelId} className={styles.fullReportPanel}>
      <p className={styles.fullReportIntro}>Financial RIP is built from six scored dimensions. These statistics include both the measurements behind those dimensions and additional simulation diagnostics.</p>
      <div className={styles.fullReportGroups}>{report.groups.map((group) => <section key={group.key} className={styles.fullReportGroup}>
        <header><h3>{group.title}</h3><span>{group.classification}</span></header>
        <dl className={styles.fullReportGrid}>{group.rows.map((item) => <div key={item.key} className={styles.fullReportRow}><dt><span>{item.label}</span>{item.help ? <InfoPopover text={item.help} /> : null}</dt><dd>{item.value}</dd></div>)}</dl>
      </section>)}</div>
    </div> : null}
  </div>;
}
