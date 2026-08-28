import Image from "next/image";
import { MediaFigure } from "@/components/articles/ArticlePrimitives";

export function ChaseEfficiencyInputsFigure() {
  const inputs = [
    ["Current card value", "Exact printing · Near Mint"],
    ["Modeled pull probability", "Exact printing · per pack"],
    ["Best verified opening cost", "Lowest supported cost per random pack"],
  ];
  return <MediaFigure caption="The three inputs that shape model behavior. This explains the methodology; it is not the Index Premium leaderboard."><div role="img" aria-label="Current exact-printing card value, modeled pull probability, and best verified pack-equivalent opening cost flow into Chase Efficiency" className="grid items-stretch gap-3 md:grid-cols-[1fr_auto_1fr]">
    <div className="grid gap-3">{inputs.map(([title, detail]) => <div key={title} className="rounded-xl border border-[var(--border-subtle)] bg-white/[.035] p-4"><p className="font-semibold text-[var(--text-primary)]">{title}</p><p className="mt-1 text-xs">{detail}</p></div>)}</div>
    <div className="hidden items-center text-2xl text-[var(--accent)] md:flex" aria-hidden="true">→</div>
    <div className="flex min-h-28 items-center justify-center rounded-xl border border-[color-mix(in_srgb,var(--accent)_45%,var(--border-subtle))] bg-[color-mix(in_srgb,var(--accent)_10%,transparent)] p-5 text-center"><div><p className="text-xs font-bold uppercase tracking-[.16em] text-[var(--accent)]">Card-level comparison</p><p className="mt-2 text-xl font-semibold text-[var(--text-primary)]">Chase Efficiency</p></div></div>
  </div></MediaFigure>;
}

const routeRows = [
  ["Shrouded Fable", 14.81, 8.90, "Booster Bundle", "39.9%"],
  ["Temporal Forces", 11.25, 8.58, "Booster Box", "23.7%"],
  ["Obsidian Flames", 12.98, 10.16, "Booster Box", "21.7%"],
  ["Paldea Evolved", 16.25, 13.03, "Booster Box", "19.8%"],
  ["Stellar Crown", 10.59, 8.72, "Booster Box", "17.6%"],
];
export function ChaseEfficiencyRouteCostFigure() {
  const max = 16.25;
  return <MediaFigure caption="Source: inDex Chase Efficiency production publication, August 27, 2026. Frozen production prices. “Best verified” means the cheapest current cost per modeled random pack among supported products with known composition. It does not imply that opening is profitable."><div className="space-y-6" role="img" aria-label="Loose pack and best verified pack-equivalent costs for five Pokémon sets">
    {routeRows.map(([name, loose, best, route, reduction]) => <section key={name} aria-label={`${name}: loose pack ${loose} dollars, best verified ${best} dollars through ${route}, a ${reduction} reduction`}><div className="flex flex-wrap items-baseline justify-between gap-2"><h3 className="font-semibold text-[var(--text-primary)]">{name}</h3><p className="text-xs">{route} · <span className="font-semibold text-[var(--accent)]">{reduction} lower</span></p></div><div className="mt-2 grid grid-cols-[4.7rem_minmax(0,1fr)_3.6rem] items-center gap-2 text-xs"><span>Loose pack</span><span className="h-2 rounded-full bg-violet-400" style={{ width: `${loose / max * 100}%` }} /><strong className="text-right text-[var(--text-primary)]">${loose.toFixed(2)}</strong><span>Best verified</span><span className="h-2 rounded-full bg-[var(--accent)]" style={{ width: `${best / max * 100}%` }} /><strong className="text-right text-[var(--text-primary)]">${best.toFixed(2)}</strong></div></section>)}
  </div></MediaFigure>;
}

export function ChaseProbabilityMilestonesFigure() {
  const milestones = [["50%", 333], ["75%", 665], ["90%", 1105], ["95%", 1437]];
  return <MediaFigure caption="Hypothetical probability example — not a live card ranking. Per-pack probability p = 1 / 480; milestones are rounded to whole packs."><div role="img" aria-label="For a hypothetical one in 480 pull probability, 50 percent is 333 packs, 75 percent is 665, 90 percent is 1105, and 95 percent is 1437" className="grid gap-3 sm:grid-cols-4">{milestones.map(([chance, packs]) => <div key={chance} className="rounded-xl border border-[var(--border-subtle)] bg-white/[.035] p-4 text-center"><p className="text-2xl font-semibold text-[var(--accent)]">{chance}</p><div className="mx-auto my-3 h-1.5 rounded-full bg-[var(--accent)]" style={{ width: chance }} aria-hidden="true" /><p className="font-semibold text-[var(--text-primary)]">{packs.toLocaleString()} packs</p></div>)}</div></MediaFigure>;
}

export function ChaseEfficiencyCoverageFigure() {
  return <MediaFigure caption="Source: inDex Chase Efficiency production publication, August 27, 2026. Exclusions fail closed rather than receiving inferred or neutral values."><div role="group" aria-label="Chase Efficiency publication coverage: 22 supported sets, 4,862 eligible exact printings, and 17 excluded printings" className="grid gap-3 sm:grid-cols-3"><Stat value="22" label="supported sets" /><Stat value="4,862" label="eligible exact printings" /><div className="rounded-xl border border-[var(--border-subtle)] p-4"><p className="text-3xl font-semibold text-[var(--accent)]">17</p><p className="mt-1 text-sm text-[var(--text-primary)]">excluded printings</p><p className="mt-3 text-xs">9 stale Near Mint price<br />8 unmapped canonical card identity</p></div></div></MediaFigure>;
}
function Stat({ value, label }) { return <div className="rounded-xl border border-[var(--border-subtle)] p-4"><p className="text-3xl font-semibold text-[var(--accent)]">{value}</p><p className="mt-1 text-sm text-[var(--text-primary)]">{label}</p></div>; }

export function ExactPrintingFigure() {
  return <div><div className="relative mx-auto aspect-[2.5/3.5] w-52 sm:w-56"><div className="absolute inset-8 rounded-full bg-[var(--accent)]/15 blur-3xl" aria-hidden="true" /><Image src="https://images.pokemontcg.io/sv7/148_hires.png" alt="Squirtle Illustration Rare card from Stellar Crown" fill sizes="224px" className="object-contain drop-shadow-[0_18px_28px_rgba(0,0,0,0.5)]" /></div><p className="mx-auto mt-3 max-w-xs text-center text-xs leading-5 text-[var(--text-secondary)]">Card artwork is illustrative. Chase Efficiency evaluates exact printings rather than Pokémon names in the abstract.</p></div>;
}
