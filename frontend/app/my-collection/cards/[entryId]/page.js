import { notFound } from "next/navigation";
import MarketModule from "@/components/Collectibles/MarketModule";
import PortfolioModule from "@/components/Collectibles/PortfolioModule";
import { getOwnedEntryPortfolioPageData } from "@/lib/collectibles/portfolioDataLoader";

export default async function MyCollectionCardEntryPage({ params }) {
  const { entryId } = await params;
  const data = await getOwnedEntryPortfolioPageData(entryId);

  if (!data.found || data.metadata?.collectible_type !== "card") {
    notFound();
  }

  return (
    <section className="mx-auto w-full max-w-5xl space-y-6 px-4 py-8 sm:px-6 lg:px-8">
      <header className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-page)] p-5">
        <p className="text-xs font-semibold uppercase tracking-[0.1em] text-[var(--text-secondary)]">Private Portfolio Entry</p>
        <h1 className="mt-1 text-2xl font-bold text-[var(--text-primary)]">{data.metadata.name}</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">Entry #{data.metadata.entry_id} • {data.metadata.set_name}</p>
      </header>
      <MarketModule market={data.market} />
      <PortfolioModule portfolio={data.portfolio} canViewPortfolio={data.canViewPortfolio} />
    </section>
  );
}
