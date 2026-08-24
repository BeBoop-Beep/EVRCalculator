import { MediaFigure } from "@/components/articles/ArticlePrimitives";

const outcomeRows = [
  ["Prismatic Evolutions", 93.91, 3.23, 2.30, 1.08],
  ["Journey Together", 81.31, 7.62, 3.96, 0.97],
  ["Phantasmal Flames", 92.43, 3.55, 0.87, 0.33],
  ["Temporal Forces", 83.37, 10.18, 5.61, 1.35],
];

function Bar({ value, max = 100, tone = "bg-[var(--accent)]" }) {
  return <div className="h-2 w-full overflow-hidden rounded-full bg-white/10" aria-hidden="true"><span className={`block h-full rounded-full ${tone}`} style={{ width: `${(value / max) * 100}%` }} /></div>;
}

export function TypicalVsEvFigure() {
  const rows = [["Prismatic Evolutions", 1.78, 8.53, "20.9%"], ["Journey Together", 1.89, 3.44, "54.9%"]];
  return <MediaFigure caption="Figure 1. Median modeled opening versus Expected Value on one shared $0–$9 scale. Frozen market date: August 22, 2026."><div role="img" aria-label="Prismatic Evolutions has a median of 1 dollar 78 cents and EV of 8 dollars 53 cents. Journey Together has a median of 1 dollar 89 cents and EV of 3 dollars 44 cents." className="space-y-6">{rows.map(([name, median, ev, capture]) => <div key={name}><div className="flex flex-wrap items-baseline justify-between gap-2"><p className="font-semibold text-[var(--text-primary)]">{name}</p><p className="text-sm"><span className="font-semibold text-[var(--accent)]">{capture}</span> Typical Capture</p></div><div className="mt-3 space-y-2"><div className="grid grid-cols-[5rem_1fr_3.4rem] items-center gap-2 text-sm"><span>Median</span><Bar value={median} max={9} /><strong className="text-right text-[var(--text-primary)]">${median.toFixed(2)}</strong></div><div className="grid grid-cols-[5rem_1fr_3.4rem] items-center gap-2 text-sm"><span>EV</span><Bar value={ev} max={9} tone="bg-violet-400" /><strong className="text-right text-[var(--text-primary)]">${ev.toFixed(2)}</strong></div></div></div>)}</div></MediaFigure>;
}

export function TailConvergenceFigure() {
  const rows = [["Prismatic Evolutions", 64.1, "2,812", "5,906"], ["Journey Together", 16.7, "150", "150"]];
  return <MediaFigure caption="Figure 2. Two examples from the 22-set cohort. The cohort-wide rank correlations—not these two cases alone—support the association. Frozen August 22, 2026."><div className="grid gap-4 sm:grid-cols-2" role="group" aria-label="Tail concentration and confirmed convergence comparison">{rows.map(([name, share, r80, convergence]) => <section key={name} className="rounded-xl border border-[var(--border-subtle)] p-4"><h3 className="font-semibold text-[var(--text-primary)]">{name}</h3><p className="mt-3 text-3xl font-semibold text-[var(--accent)]">{share}%</p><p className="text-xs uppercase tracking-wide">of EV from top 1% of outcomes</p><Bar value={share} /><dl className="mt-5 grid grid-cols-2 gap-3 text-sm"><div><dt>80% EV horizon</dt><dd className="mt-1 font-semibold text-[var(--text-primary)]">{r80} packs</dd></div><div><dt>±20% horizon</dt><dd className="mt-1 font-semibold text-[var(--text-primary)]">{convergence} packs</dd></div></dl></section>)}</div></MediaFigure>;
}

export function OutcomeProbabilityFigure() {
  const labels = ["Under half", "Recover cost", "2×+", "5×+"];
  return <MediaFigure caption="Figure 3. Cumulative one-pack probabilities from exact modeled outcome counts. Gross card market value before selling costs; frozen August 22, 2026."><div className="overflow-x-auto"><table className="w-full min-w-[38rem] border-collapse text-left text-sm"><thead><tr><th scope="col" className="p-2 text-[var(--text-primary)]">Set</th>{labels.map(label => <th scope="col" key={label} className="p-2 text-right text-[var(--text-primary)]">{label}</th>)}</tr></thead><tbody>{outcomeRows.map(([name, ...values]) => <tr key={name} className="border-t border-[var(--border-subtle)]"><th scope="row" className="p-2 font-medium text-[var(--text-primary)]">{name}</th>{values.map((value, index) => <td key={labels[index]} className="p-2 text-right tabular-nums"><span className="block">{value.toFixed(2)}%</span><span className="ml-auto mt-1 block w-16"><Bar value={value} /></span></td>)}</tr>)}</tbody></table></div></MediaFigure>;
}
