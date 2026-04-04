import { redirect } from "next/navigation";

export default async function MyCollectionProductEntryTabRedirect({ params }) {
  const { entryId } = await params;
  redirect(`/my-portfolio/products/${encodeURIComponent(String(entryId))}`);
}
