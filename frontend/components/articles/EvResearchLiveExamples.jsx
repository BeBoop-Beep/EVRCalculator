import Link from "next/link";
import { LiveDistributionFigure, MediaFigure } from "./ArticlePrimitives";
import OpeningOutcomeProfileSection from "@/components/explore/simulation-evidence/OpeningOutcomeProfileSection.jsx";
import EvRepresentativenessSection from "@/components/explore/simulation-evidence/EvRepresentativenessSection.jsx";

const note = "This panel uses current inDex simulation data and may differ from the frozen August 22, 2026 study results discussed in this article.";

function LiveHeader({ model }) {
  return <div className="mb-4 flex flex-wrap items-end justify-between gap-3 border-b border-[var(--border-subtle)] pb-3"><div><p className="text-[10px] font-bold uppercase tracking-[0.18em] text-[var(--accent)]">Live example</p><p className="mt-1 font-semibold text-[var(--text-primary)]">Prismatic Evolutions <span className="font-normal text-[var(--text-secondary)]">· Current simulation data</span></p></div><Link href={model?.setHref || "/TCGs/Pokemon/Sets/prismatic-evolutions"} className="text-xs font-semibold text-[var(--accent)]">View current Prismatic Evolutions RIP analysis →</Link></div>;
}

function Unavailable() {
  return <MediaFigure caption={note}><p className="py-6 text-center text-sm text-[var(--text-secondary)]">Current example temporarily unavailable.</p></MediaFigure>;
}

export function LivePrismaticDistribution({ model }) {
  if (!model) return <Unavailable />;
  return <div className="!my-10"><LiveHeader model={model} /><LiveDistributionFigure distribution={model.distribution} setName={model.setName} simulationCount={model.simulationCount} caption={`Live example — Prismatic Evolutions. Current inDex modeled opening distribution. This uses the same RipDistributionChart as the set page and updates with current published simulation data. The research results remain frozen to August 22, 2026.`} /></div>;
}

export function LivePrismaticOutcomeProfile({ model }) {
  if (!model) return <Unavailable />;
  return <MediaFigure caption={`Live Prismatic Evolutions example. ${note} The panel itself is shared with the live RIP experience.`}><LiveHeader model={model} /><OpeningOutcomeProfileSection openingOutcomeProfile={model.openingOutcomeProfile} calculationRunId={model.calculationRunId} headingId="article-live-outcome-profile" /></MediaFigure>;
}

export function LivePrismaticEvRepresentativeness({ model }) {
  if (!model) return <Unavailable />;
  return <MediaFigure caption={`Live Prismatic Evolutions example. ${note} The panel itself is shared with the live RIP experience.`}><LiveHeader model={model} /><EvRepresentativenessSection summary={model.summary} percentiles={model.percentiles} evRepresentativeness={model.evRepresentativeness} calculationRunId={model.calculationRunId} headingId="article-live-ev-representativeness" /></MediaFigure>;
}
