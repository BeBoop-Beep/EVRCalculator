"use client";

import { useMemo } from "react";
import InfoPopover from "@/components/ui/InfoPopover";
import { formatEvRepPacks, formatEvRepPercent, selectEvRepresentativenessPublicV1 } from "../evRepresentativenessSelector.mjs";
import styles from "../RipDecisionPage.module.css";

const currency = (value) => Number.isFinite(Number(value)) ? new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(Number(value)) : "Not confirmed";

export default function EvRepresentativenessSection({ summary, percentiles, evRepresentativeness = null, calculationRunId = null, headingId }) {
  const evRep = useMemo(() => selectEvRepresentativenessPublicV1(evRepresentativeness, calculationRunId), [evRepresentativeness, calculationRunId]);
  if (!evRep) return null;
  const ev = Number(summary?.meanValue ?? summary?.mean_value);
  const p50Row = (Array.isArray(percentiles) ? percentiles : []).find((row) => Number(row?.percentile ?? row?.p) === 50 || Number(row?.quantile) === .5);
  const p50 = Number(p50Row?.value ?? p50Row?.amount ?? summary?.median_value ?? summary?.medianValue);
  const scale = Math.max(Number.isFinite(ev) ? ev : 0, Number.isFinite(p50) ? p50 : 0);
  const realization36 = evRep.realizationByPackCount?.find((row) => row.packCount === 36);
  return <section className={styles.evRepSection} aria-labelledby={headingId}><header><div><h3 id={headingId}>How Representative Is EV of Real Openings?</h3><p>Expected Value is a long-run average. Value ratios and repeated-opening probabilities answer different questions.</p></div><InfoPopover text="Estimated from one million modeled outcomes. Horizons assume independent pack draws and are not opening recommendations." /></header>
    <div className={styles.evComparison}>{[["Typical pack (P50)", p50], ["Long-run EV", ev]].map(([label, value]) => <div key={label}><span>{label}</span><div><i style={{ width: `${scale > 0 && Number.isFinite(value) ? value / scale * 100 : 0}%` }} /></div><strong>{currency(value)}</strong></div>)}</div>
    <p className={styles.evCapture}>The typical modeled pack captures <strong>{formatEvRepPercent(evRep.typicalCapture)}</strong> of EV.</p><h4 className={styles.evGapTitle}>Why can EV sit so far above the typical opening?</h4><p className={styles.evSkew}>The best 1% of modeled openings account for <strong>{formatEvRepPercent(evRep.top1OutcomeEvShare)}</strong> of total Expected Value.</p>
    <div className={styles.evMilestones}><div><span>36 packs</span><strong>{realization36 ? formatEvRepPercent(realization36.probabilityAtLeast80PercentEv) : "Not confirmed"}</strong><small>of modeled 36-pack runs average at least 80% of long-run EV</small></div><div><span>Reach 80% of EV Reliably</span><strong>{evRep.realizationHorizon ? formatEvRepPacks(evRep.realizationHorizon.packCount) : "Not confirmed"}</strong><small>the first count where 80% of runs average at least 80% of EV</small></div><div><span>Converge Near EV</span><strong>{evRep.convergenceHorizon ? formatEvRepPacks(evRep.convergenceHorizon.packCount) : "Not confirmed"}</strong><small>the first count where 80% of runs finish within ±20% of EV</small></div></div>
    {evRep.realizationByPackCount.length ? <details className={styles.evRepRealization}><summary>Chance to Reach at Least 80% of EV</summary><div role="table" aria-label="Chance to reach at least 80% of EV by pack count">{evRep.realizationByPackCount.map((r) => <div role="row" key={r.packCount} className={styles.evRepTableRow}><span role="cell">{r.packCount.toLocaleString("en-US")} packs</span><strong role="cell">{formatEvRepPercent(r.probabilityAtLeast80PercentEv)}</strong></div>)}</div></details> : null}
  </section>;
}
