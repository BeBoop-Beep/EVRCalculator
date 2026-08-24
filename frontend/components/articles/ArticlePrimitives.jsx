import Image from "next/image";
import Link from "next/link";
import RipDistributionChart from "@/components/explore/RipDistributionChart";

export function ArticleJsonLd({ title, description, path }) {
  const url = `https://www.inthedex.io${path}`;
  const data = { "@context": "https://schema.org", "@type": "Article", headline: title, description, url, mainEntityOfPage: url, publisher: { "@type": "Organization", name: "inDex", url: "https://www.inthedex.io" } };
  return <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(data) }} />;
}

export function ArticleShell({ category, title, deck, children, related = [] }) {
  return (
    <article className="mx-auto w-full max-w-5xl px-4 pb-24 pt-8 sm:px-6 lg:px-8">
      <header className="mx-auto max-w-3xl">
        <p className="text-xs font-bold uppercase tracking-[0.2em] text-[var(--accent)]">{category}</p>
        <h1 className="mt-3 text-4xl font-semibold tracking-tight text-[var(--text-primary)] sm:text-5xl">{title}</h1>
        {deck ? <p className="mt-5 text-lg leading-8 text-[var(--text-secondary)]">{deck}</p> : null}
      </header>
      <div className="article-copy mx-auto mt-8 max-w-3xl space-y-5 text-[16px] leading-7 text-[var(--text-secondary)]">{children}</div>
      {related.length ? <div className="mx-auto max-w-3xl"><RelatedArticles items={related} /></div> : null}
    </article>
  );
}

export function H2({ children }) { return <h2 className="!mt-12 text-2xl font-semibold tracking-tight text-[var(--text-primary)] sm:text-3xl">{children}</h2>; }
export function H3({ children }) { return <h3 className="!mt-8 text-xl font-semibold text-[var(--text-primary)]">{children}</h3>; }

export function Citation({ href, children }) {
  return <a href={href} target="_blank" rel="noreferrer" className="rounded-sm font-medium text-[var(--accent)] underline decoration-[var(--accent)]/45 underline-offset-4 hover:decoration-[var(--accent)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]">{children}</a>;
}

export function ReferenceList({ items }) {
  return <ol className="!mt-6 space-y-4 pl-5 text-sm leading-6">{items.map(item => <li key={item.href} id={item.id} className="pl-1"><Citation href={item.href}>{item.citation}</Citation>{item.note ? <span> {item.note}</span> : null}</li>)}</ol>;
}

export function DefinitionGrid({ items, columns = "sm:grid-cols-2" }) {
  return <dl className={`!mt-6 grid gap-3 ${columns}`}>{items.map(([name, text]) => <div key={name} className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/35 p-4"><dt className="font-semibold text-[var(--text-primary)]">{name}</dt><dd className="mt-1 text-sm leading-6">{text}</dd></div>)}</dl>;
}

export function MediaFigure({ children, caption, className = "" }) {
  return <figure className={`!my-9 overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)]/55 ${className}`}><div className="min-w-0 p-3 sm:p-5">{children}</div>{caption ? <figcaption className="border-t border-[var(--border-subtle)] px-4 py-3 text-xs leading-5 text-[var(--text-secondary)] sm:px-5">{caption}</figcaption> : null}</figure>;
}

export function EditorialSplit({ children, media, mediaFirst = false, className = "" }) {
  return <section className={`!my-10 grid items-center gap-6 rounded-3xl bg-[linear-gradient(135deg,color-mix(in_srgb,var(--surface-panel)_72%,transparent),transparent)] px-5 py-6 sm:px-7 lg:grid-cols-[minmax(0,1.35fr)_minmax(15rem,.65fr)] lg:gap-10 ${className}`}><div className={mediaFirst ? "lg:order-2" : ""}>{children}</div><div className={`min-w-0 ${mediaFirst ? "lg:order-1" : ""}`}>{media}</div></section>;
}

export function PackArt({ src = "/images/pokemon/booster-packs/perfectOrder.webp", alt = "Perfect Order Pokemon booster pack", compact = false }) {
  return <div className={`relative mx-auto ${compact ? "h-56 w-40" : "h-72 w-52"}`}><div className="absolute inset-8 rounded-full bg-[var(--accent)]/15 blur-3xl" aria-hidden="true" /><Image src={src} alt={alt} fill sizes={compact ? "160px" : "208px"} className="object-contain drop-shadow-[0_20px_32px_rgba(0,0,0,0.45)]" /></div>;
}

export function LiveDistributionFigure({ distribution, setName, simulationCount }) {
  if (!distribution?.bins?.length && !distribution?.thresholdBins?.length) return null;
  return <MediaFigure className="lg:relative lg:left-1/2 lg:w-[min(64rem,calc(100vw-3rem))] lg:-translate-x-1/2" caption={`${simulationCount ? Number(simulationCount).toLocaleString("en-US") : "Published"} simulated ${setName} openings, rendered from the same canonical distribution data used by the inDex set experience. The average is one point inside this full outcome profile.`}><div className="min-w-0"><RipDistributionChart bins={distribution.bins} thresholdBins={distribution.thresholdBins} markers={distribution.markers} showTitle={false} flush /></div></MediaFigure>;
}

export function EvDistributionDiagram() {
  return <MediaFigure caption="Hypothetical example. Both profiles have the same mean, but Profile A spreads value through ordinary outcomes while Profile B concentrates it in a rare tail."><svg viewBox="0 0 720 280" role="img" aria-label="Two hypothetical distributions with the same expected value but different typical outcomes" className="h-auto w-full"><rect width="720" height="280" rx="18" fill="rgba(10,20,28,.45)"/><g stroke="rgba(148,163,184,.35)" strokeWidth="2"><path d="M55 225H665"/><path d="M55 45V225"/></g><g fill="#23c7b8"><rect x="90" y="115" width="70" height="110" rx="5"/><rect x="175" y="80" width="70" height="145" rx="5"/><rect x="260" y="125" width="70" height="100" rx="5"/></g><g fill="#a78bfa"><rect x="405" y="185" width="70" height="40" rx="5"/><rect x="490" y="197" width="70" height="28" rx="5"/><rect x="575" y="55" width="48" height="170" rx="5"/></g><g fill="currentColor" fontSize="15"><text x="150" y="255">Profile A</text><text x="480" y="255">Profile B</text><text x="20" y="35">frequency</text></g></svg></MediaFigure>;
}

export function DragoniteFigure() {
  return <div><div className="relative mx-auto aspect-[2.5/3.5] w-52 sm:w-56"><div className="absolute inset-8 rounded-full bg-amber-400/15 blur-3xl" aria-hidden="true" /><Image src="https://images.pokemontcg.io/sv3pt5/149_hires.png" alt="Dragonite card from the Pokemon Scarlet and Violet 151 set" fill sizes="224px" className="object-contain drop-shadow-[0_18px_28px_rgba(0,0,0,0.5)]" /></div><p className="mx-auto mt-3 max-w-xs text-center text-xs leading-5 text-[var(--text-secondary)]">Dragonite from Scarlet &amp; Violet 151, supplied through the card-image pipeline already used by inDex.</p></div>;
}

export function MetricStory({ items }) {
  return <div className="!my-8 grid gap-3 sm:grid-cols-3">{items.map((item, index) => <div key={item.label} className="relative overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)]/65 p-4"><span className="absolute right-3 top-2 text-4xl font-black text-[var(--accent)]/10">{index + 1}</span><p className="text-xs font-bold uppercase tracking-[0.12em] text-[var(--accent)]">{item.label}</p><p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">{item.text}</p></div>)}</div>;
}

function RelatedArticles({ items }) {
  return <section className="mt-14 border-t border-[var(--border-subtle)] pt-8"><h2 className="text-xl font-semibold text-[var(--text-primary)]">Related Articles</h2><div className="mt-4 grid gap-3 sm:grid-cols-2">{items.map(item => <Link key={item.href} href={item.href} className="rounded-xl border border-[var(--border-subtle)] p-4 text-sm font-semibold text-[var(--text-primary)] transition-colors hover:border-[var(--accent)]">{item.title}</Link>)}</div><Link href="/Articles" className="mt-5 inline-block text-sm font-semibold text-[var(--accent)]">All Articles</Link></section>;
}
