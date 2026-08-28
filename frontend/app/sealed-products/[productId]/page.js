import Link from "next/link";
import { notFound } from "next/navigation";
import { buildRouteMetadata } from "@/lib/seo/routeMetadata.mjs";
import { buildSealedProductHref } from "@/lib/pokemon/sealedProductRoutes";
import { getSealedProductDetailServer } from "@/lib/pokemon/sealedProductDetailServer";

async function load(params) {
  const { productId } = (await params) || {};
  return getSealedProductDetailServer(productId);
}

export async function generateMetadata({ params }) {
  try {
    const detail = await load(params);
    return buildRouteMetadata({
      path: buildSealedProductHref(detail.product.id),
      title: `${detail.product.name} — ${detail.set.name} | inDex`,
      description: `${detail.product.name} from ${detail.set.name}: real sealed market history and current published opening intelligence.`,
    });
  } catch { return {}; }
}

const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

export default async function SealedProductCanonicalPage({ params }) {
  let detail;
  try { detail = await load(params); }
  catch (error) { if (error?.status === 404) notFound(); throw error; }
  const setHref = `/TCGs/Pokemon/Sets/${encodeURIComponent(detail.set.slug)}`;
  return (
    <section className="mx-auto w-full max-w-5xl space-y-5 px-4 py-8 sm:px-6 lg:px-8">
      <Link href={setHref} className="text-sm text-[var(--accent)] hover:underline">← Back to {detail.set.name}</Link>
      <header className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-page)] p-5">
        <p className="text-xs font-semibold uppercase tracking-[0.1em] text-[var(--text-secondary)]">{detail.product.productFamilyLabel}</p>
        <h1 className="mt-1 text-2xl font-bold text-[var(--text-primary)]">{detail.product.name}</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">{detail.set.name}</p>
      </header>
      <div className="grid gap-4 sm:grid-cols-2">
        <article className="rounded-2xl border border-[var(--border-subtle)] p-5">
          <h2 className="font-semibold">Market</h2>
          <p className="mt-2 text-2xl font-bold">{detail.market.available ? money.format(detail.market.currentPrice) : "Unavailable"}</p>
          <p className="text-sm text-[var(--text-secondary)]">{detail.market.marketDate ? `As of ${detail.market.marketDate}` : detail.market.reason}</p>
        </article>
        <article className="rounded-2xl border border-[var(--border-subtle)] p-5">
          <h2 className="font-semibold">RIP Intelligence</h2>
          <p className="mt-2 text-2xl font-bold">{detail.rip.available ? `#${detail.rip.familyRank} of ${detail.rip.familySize}` : "Unavailable"}</p>
          <p className="text-sm text-[var(--text-secondary)]">{detail.rip.available ? "Format Rank" : detail.rip.reason}</p>
        </article>
      </div>
    </section>
  );
}
