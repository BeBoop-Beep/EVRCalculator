import { redirect } from "next/navigation";
import { getPrivateCollectionEntryById } from "@/lib/profile/collectionEntryLoader";

export default async function MyCollectionEntryPage({ params, searchParams }) {
  const { entryId } = await params;
  await searchParams;

  const entry = await getPrivateCollectionEntryById(entryId);
  if (!entry) {
    redirect("/my-portfolio/collection");
  }

  if (entry.collectible_type === "sealed_product") {
    redirect(`/my-portfolio/products/${encodeURIComponent(String(entry.id))}`);
  }

  redirect(`/my-portfolio/cards/${encodeURIComponent(String(entry.id))}`);
}
