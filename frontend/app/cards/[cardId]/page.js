import { notFound } from "next/navigation";

import CardDetailPageClient from "@/components/cards/CardDetailPageClient";
import { getCardDetailPagePayload } from "@/lib/cards/cardDetailServer";

export default async function CardCanonicalPage({ params }) {
  const { cardId } = await params;
  const payload = await getCardDetailPagePayload(cardId);

  if (!payload?.identity) {
    notFound();
  }

  return <CardDetailPageClient payload={payload} />;
}
