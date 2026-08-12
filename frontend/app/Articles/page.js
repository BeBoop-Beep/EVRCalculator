import Link from "next/link";
import { buildRouteMetadata } from "@/lib/seo/routeMetadata.mjs";

export const metadata = buildRouteMetadata({
  path: "/Articles",
  title: "Articles — inDex",
  description:
    "How inDex measures Pokémon sets: methodology, modeled opening simulations, and how to read the scores.",
  ogTitle: "inDex Articles",
});

/**
 * The article index. ONE array, ONE shape — a listed article is a real,
 * published route, and nothing else appears here.
 *
 * Deliberately NOT a CMS and deliberately NOT a roadmap: unwritten pieces are
 * omitted entirely rather than rendered as disabled cards or thin placeholder
 * pages, because a hub that advertises pages it cannot serve is worse than a
 * short one. Adding a future article means adding its route and one entry here.
 */
const ARTICLES = [
  {
    href: "/Articles/how-rip-score-works",
    eyebrow: "Methodology",
    title: "How the RIP Score Works",
    summary:
      "Expected Value was the first thing I calculated, and the first thing that showed me why it was not enough on its own. What Overall RIP measures instead, why the 0 to 100 scale is relative rather than absolute, and what a million simulated openings can and cannot tell you.",
  },
];

export default function ArticlesPage() {
  return (
    <div className="mx-auto w-full max-w-5xl px-4 pb-24 pt-8 sm:px-6 lg:px-8">
      <header className="mx-auto max-w-3xl text-center">
        <p className="text-xs font-bold uppercase tracking-[0.2em] text-[var(--accent)]">inDex</p>
        <h1 className="mt-3 text-4xl font-semibold tracking-tight text-[var(--text-primary)] sm:text-5xl">Articles</h1>
        <p className="mt-4 text-base leading-7 text-[var(--text-secondary)] sm:text-lg">
          Notes on how inDex actually works: what the scores measure, how the opening simulations behind
          them are built, and where the models stop being reliable.
        </p>
      </header>

      <ul className="mx-auto mt-10 grid max-w-3xl gap-4">
        {ARTICLES.map((article) => (
          <li key={article.href}>
            <Link
              href={article.href}
              className="set-glass-surface block rounded-2xl border p-5 transition-colors hover:border-[var(--accent)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] sm:p-6"
            >
              <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-[var(--accent)]">{article.eyebrow}</p>
              <h2 className="mt-1 text-xl font-semibold tracking-tight text-[var(--text-primary)] sm:text-2xl">{article.title}</h2>
              <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">{article.summary}</p>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
