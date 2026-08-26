"use client";

import { useMemo } from "react";
import InfoPopover from "@/components/ui/InfoPopover";
import { buildOutcomeProfileViewModel, formatOutcomePercent, selectOpeningOutcomeProfileV1 } from "../openingOutcomeProfileSelector.mjs";
import styles from "../RipDecisionPage.module.css";

export default function OpeningOutcomeProfileSection({ openingOutcomeProfile = null, calculationRunId = null, headingId, canViewAdvanced = false }) {
  const profile = useMemo(() => selectOpeningOutcomeProfileV1(openingOutcomeProfile, calculationRunId), [openingOutcomeProfile, calculationRunId]);
  const outcome = useMemo(() => buildOutcomeProfileViewModel(profile), [profile]);
  return <section className={styles.outcomeProfileSection} aria-labelledby={headingId}><header><div><h3 id={headingId}>What Happens When You Open a Pack?</h3><p>Where one million modeled pack openings landed relative to today&apos;s pack price.</p></div><InfoPopover text="Gross modeled card market value relative to pack cost. Selling fees, grading and liquidity are not included." /></header>
    {outcome ? <><div className={styles.outcomeHero}><strong>{formatOutcomePercent(outcome.groups[0].probability)}</strong><span>About {Math.round(outcome.groups[0].probability * 100)} out of 100 modeled packs return less than half the pack price.</span></div>
    <div className={styles.outcomeProfileBar} role="img" aria-label={outcome.groups.map((r) => `${r.label}: ${formatOutcomePercent(r.probability)}`).join("; ")}>{outcome.groups.map((r, index) => <span key={r.key} style={{ flexGrow: r.probability, flexBasis: 0 }}><i>{formatOutcomePercent(r.probability)}</i>{index === 1 ? <b>PACK COST</b> : null}</span>)}</div>
    <div className={styles.outcomeLegend}>{outcome.groups.map((r) => <span key={r.key}>{r.label}</span>)}</div><div className={styles.outcomeProfileCallouts}>{[["Under half back", outcome.groups[0].probability], ["Recover pack cost", outcome.groups[2].probability + outcome.groups[3].probability], ["Reach 2× or more", outcome.groups[3].probability]].map(([label, value]) => <div key={label}><span>{label}</span><strong>{formatOutcomePercent(value)}</strong></div>)}</div>
    {canViewAdvanced ? <details className={styles.outcomeDetails}><summary>View full outcome breakdown</summary><dl>{outcome.details.map((r) => <div key={r.key}><dt>{r.label}<InfoPopover text={r.interpretation} /></dt><dd>{formatOutcomePercent(r.probability)}</dd></div>)}</dl></details> : null}</> : <p className={styles.outcomeProfileUnavailable}>An exact same-run outcome breakdown is not available for this simulation.</p>}
  </section>;
}
