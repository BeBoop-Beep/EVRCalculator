import { redirect } from "next/navigation";
import { getPublicCollectionRedirectCollectible } from "@/lib/collectibles/portfolioDataLoader";
import { buildCardRoute, buildSealedProductRoute } from "@/lib/profile/collectionRoutes";

export default async function PublicCollectionItemPage({ params, searchParams }) {
  const { username, itemId } = await params;
  await searchParams;

  const collectible = await getPublicCollectionRedirectCollectible(username, itemId);
  if (!collectible) {
    redirect(`/u/${encodeURIComponent(username)}/collection`);
  }

  if (collectible.collectible_type === "sealed_product") {
    redirect(buildSealedProductRoute(collectible.collectible_id));
  }

  redirect(buildCardRoute(collectible.collectible_id));
}
