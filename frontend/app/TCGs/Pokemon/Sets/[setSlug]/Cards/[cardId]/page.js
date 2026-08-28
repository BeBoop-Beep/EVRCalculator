import { notFound, redirect } from "next/navigation";
import { buildRouteMetadata } from "@/lib/seo/routeMetadata.mjs";
import { getPokemonCardDetailServer } from "@/lib/pokemon/pokemonCardDetailServer";
import PokemonCardDetailClient from "@/components/pokemon/card-detail/PokemonCardDetailClient";

async function load(params, searchParams) {
  const route = (await params) || {};
  const query = (await searchParams) || {};
  return getPokemonCardDetailServer(
    route.setSlug,
    route.cardId,
    query.variant || null,
  );
}

export async function generateMetadata({ params, searchParams }) {
  try {
    const detail = await load(params, searchParams);
    const path = `/TCGs/Pokemon/Sets/${encodeURIComponent(detail.set.slug)}/Cards/${encodeURIComponent(detail.card.id)}`;
    const cardNumber = detail.card.printedNumber || detail.card.cardNumber;
    return buildRouteMetadata({
      path,
      title: `${detail.card.name} — ${detail.set.name} Chase Analysis | inDex`,
      description: `${detail.card.name}${cardNumber ? ` ${cardNumber}` : ""} from ${detail.set.name}: current market price, modeled pull odds, probability milestones, and sealed-product Chase economics.`,
    });
  } catch {
    return {};
  }
}

export default async function PokemonCardPage({ params, searchParams }) {
  const route = (await params) || {};
  const query = (await searchParams) || {};
  let detail;
  try {
    detail = await getPokemonCardDetailServer(
      route.setSlug,
      route.cardId,
      query.variant || null,
    );
  } catch (error) {
    if (error?.status === 404) notFound();
    throw error;
  }
  if (detail?.set?.slug && String(route.setSlug) !== detail.set.slug) {
    const canonical = `/TCGs/Pokemon/Sets/${encodeURIComponent(detail.set.slug)}/Cards/${encodeURIComponent(detail.card.id)}`;
    redirect(
      query.variant
        ? `${canonical}?variant=${encodeURIComponent(query.variant)}`
        : canonical,
    );
  }
  return <PokemonCardDetailClient initialDetail={detail} />;
}
