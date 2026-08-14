import Image from "next/image";
import Link from "next/link";
import { ARTICLES } from "@/lib/articles/articleData.mjs";
import { buildRouteMetadata } from "@/lib/seo/routeMetadata.mjs";

export const metadata = buildRouteMetadata({ path: "/Articles", title: "Articles | inDex", description: "Approachable research on how inDex models Pokémon pack openings, validates simulations, and builds RIP scores.", ogTitle: "inDex Articles" });
const groups = ["Methodology", "Analysis & Guides"];

function CardMotif({ type }) {
  if (type === "distribution") return <svg viewBox="0 0 260 90" className="absolute bottom-0 right-0 w-60 opacity-70" aria-hidden="true"><path d="M0 82 C55 80 66 30 105 48 C145 66 158 14 202 60 C224 78 243 74 260 67" fill="none" stroke="var(--accent)" strokeWidth="4" /></svg>;
  if (type === "contrast") return <div className="absolute bottom-5 right-5 flex items-end gap-2 opacity-70" aria-hidden="true"><span className="h-10 w-5 rounded-t bg-[var(--accent)]"/><span className="h-16 w-5 rounded-t bg-violet-400"/><span className="h-7 w-5 rounded-t bg-[var(--accent)]"/></div>;
  if (type === "ev") return <span className="absolute bottom-5 right-5 text-2xl font-black text-[var(--accent)]/60" aria-hidden="true">EV ≈ SIM</span>;
  if (type === "scores") return <div className="absolute bottom-5 right-5 grid grid-cols-3 gap-2 text-[9px] font-bold text-white/75" aria-hidden="true"><span>RIP</span><span>FIN</span><span>CA</span></div>;
  return null;
}

function ArticleCard({ article, featured = false }) {
  const imageClass = article.key === "collector" ? "object-contain object-right p-4" : "object-contain object-right scale-110";
  return <Link href={article.href} className={`group relative block min-h-[15rem] overflow-hidden rounded-3xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] transition duration-300 hover:-translate-y-1 hover:border-[var(--accent)] hover:shadow-[0_20px_55px_rgba(0,0,0,.28)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] ${featured ? "sm:min-h-[18rem]" : ""}`}>
    <div className="absolute inset-y-0 right-0 w-[52%]"><div className="absolute inset-4 rounded-full bg-[var(--accent)]/12 blur-3xl"/><Image src={article.media.src} alt="" fill sizes="(max-width: 767px) 46vw, 300px" className={imageClass} /></div>
    <CardMotif type={article.media.motif} />
    <div className="absolute inset-0 bg-[linear-gradient(90deg,var(--surface-panel)_0%,var(--surface-panel)_48%,transparent_83%)]" />
    <div className="relative flex min-h-[15rem] max-w-[74%] flex-col p-5 sm:p-6"><p className="text-[11px] font-bold uppercase tracking-[0.16em] text-[var(--accent)]">{article.category}</p><h3 className={`mt-2 font-semibold leading-tight tracking-tight text-[var(--text-primary)] ${featured ? "text-2xl sm:text-3xl" : "text-xl sm:text-2xl"}`}>{article.title}</h3><p className="mt-3 text-sm leading-6 text-[var(--text-secondary)]">{article.description}</p><span className="mt-auto pt-5 text-sm font-semibold text-[var(--accent)]">Read article <span aria-hidden="true">→</span></span></div>
  </Link>;
}

export default function ArticlesPage() {
  return <div className="mx-auto w-full max-w-6xl px-4 pb-24 pt-8 sm:px-6 lg:px-8"><header className="mx-auto max-w-3xl text-center"><p className="text-xs font-bold uppercase tracking-[0.2em] text-[var(--accent)]">inDex</p><h1 className="mt-3 text-4xl font-semibold tracking-tight text-[var(--text-primary)] sm:text-5xl">Articles</h1><p className="mt-4 text-base leading-7 text-[var(--text-secondary)] sm:text-lg">I built inDex to answer one question: what is actually worth opening? These are the tests, tradeoffs, and weird problems behind the answer.</p></header><div className="mt-12 space-y-12">{groups.map(group => <section key={group}><h2 className="text-xl font-semibold text-[var(--text-primary)]">{group}</h2><ul className="mt-4 grid gap-5 md:grid-cols-2">{ARTICLES.filter(article => article.category === group).map((article, index) => <li key={article.href} className={group === "Analysis & Guides" ? "md:col-span-2" : ""}><ArticleCard article={article} featured={group === "Analysis & Guides" || index === 0} /></li>)}</ul></section>)}</div></div>;
}
