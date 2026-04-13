import { redirect } from "next/navigation";
import { getPrivateCollectionEntryById } from "@/lib/profile/collectionEntryLoader";

export default async function LegacyMyCollectionItemTabRedirect({ params }) {
  const { itemId } = await params;
  const entry = await getPrivateCollectionEntryById(itemId);

  if (!entry) {
    redirect("/my-portfolio/collection");
  }

  if (entry.collectible_type === "sealed_product") {
    redirect(`/my-portfolio/products/${encodeURIComponent(String(entry.id))}`);
  }

  redirect(`/my-portfolio/cards/${encodeURIComponent(String(entry.id))}`);
}
