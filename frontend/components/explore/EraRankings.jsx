import { eraStrengthRows, displayScore } from "./eraSetStrengthSelector.mjs";
import { RipScoreBadge, RipTierMark } from "./RipScoreBadge.jsx";
import styles from "./explore.module.css";

function StrengthRange({ era }) {
  const values = (era.constituentSets || []).map((set) => Number(set.score) / 10).filter(Number.isFinite).sort((a, b) => a - b);
  if (!values.length) return <span className="text-xs text-[var(--text-secondary)]">Unavailable</span>;
  const min = values[0];
  const max = values.at(-1);
  const median = values[Math.floor((values.length - 1) / 2)];
  return <div className="min-w-36" aria-label={`Set Strength range ${min.toFixed(1)} to ${max.toFixed(1)}, median ${median.toFixed(1)}`}>
    <div className="relative h-1 rounded-full bg-[var(--border-subtle)]"><span className="absolute top-0 h-1 rounded-full bg-[rgb(var(--ex-teal))]/45" style={{ left: `${min * 10}%`, width: `${Math.max(1, (max - min) * 10)}%` }} /><span className="absolute top-1/2 h-2 w-2 -translate-x-1/2 -translate-y-1/2 rotate-45 border border-[rgb(var(--ex-teal))] bg-[var(--surface-page)]" style={{ left: `${median * 10}%` }} /></div>
    <div className="mt-1 flex justify-between text-[9px] tabular-nums text-[var(--text-secondary)]"><span>{min.toFixed(1)}</span><span>{median.toFixed(1)} median</span><span>{max.toFixed(1)}</span></div>
  </div>;
}

export default function EraRankings({ contract, onSelectEra }) {
  const rows = eraStrengthRows(contract);
  if (!contract || rows.length === 0) return <section className={`${styles.surface} rounded-xl p-5`} data-era-rankings-unavailable><h2 className="text-base font-semibold text-[var(--text-primary)]">Era Set Strength unavailable</h2><p className="mt-1 text-sm text-[var(--text-secondary)]">Era Set Strength could not be loaded from the current published Rankings snapshot.</p></section>;
  return <section data-era-rankings>
    <header className="mb-3"><h2 className="text-lg font-semibold text-[var(--text-primary)]">Era Set Strength</h2><p className="text-xs text-[var(--text-secondary)]">Equal-weight average of each era&apos;s canonical Set RIP scores. Opening economics do not affect this ranking.</p></header>
    <div className={`${styles.surface} hidden overflow-x-auto desk:block`}><table className={styles.table}><thead className={styles.head}><tr><th className={styles.numeric}>Rank</th><th>Era</th><th className={styles.numeric}>Era Set Strength</th><th>Tier</th><th className={styles.numeric}>Sets</th><th>Strongest Set</th><th>Set Strength Range</th></tr></thead><tbody>{rows.map((era) => <tr className={styles.row} key={era.eraId || era.eraName} data-era-strength-row={era.eraName}><td className={styles.numeric}>{era.rank ? `#${era.rank}` : "—"}</td><td><button className="font-semibold hover:underline" onClick={() => onSelectEra?.(era)}>{era.eraName}</button></td><td className={styles.numeric}><RipScoreBadge score={era.score} tier={era.tier}/></td><td><RipTierMark tier={era.tier}/></td><td className={styles.numeric}>{era.modeledSetCount}</td><td>{era.strongestSet?.setName || "—"}</td><td><StrengthRange era={era} /></td></tr>)}</tbody></table></div>
    <ul className="space-y-2.5 desk:hidden">{rows.map(era => <li key={era.eraId || era.eraName} className={`${styles.surface} rounded-xl p-4`} data-era-strength-card={era.eraName}><div className="flex items-start justify-between"><div><span className="text-xs text-[var(--text-secondary)]">{era.rank ? `#${era.rank} of ${era.cohortSize}` : "Unranked"}</span><button className="block text-left font-semibold hover:underline" onClick={() => onSelectEra?.(era)}>{era.eraName}</button></div><div className="flex gap-2"><RipScoreBadge score={era.score} tier={era.tier}/><RipTierMark tier={era.tier}/></div></div><p className="mt-3 text-xs text-[var(--text-secondary)]">{era.modeledSetCount} modeled sets · strongest: <span className="text-[var(--text-primary)]">{era.strongestSet?.setName || "Unavailable"}</span></p><div className="mt-3"><StrengthRange era={era} /></div></li>)}</ul>
  </section>;
}
