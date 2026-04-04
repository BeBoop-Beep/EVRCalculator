import { redirect } from "next/navigation";

export default async function MyCollectionCardEntryTabRedirect({ params }) {
  const { entryId } = await params;
  redirect(`/my-portfolio/cards/${encodeURIComponent(String(entryId))}`);
}
