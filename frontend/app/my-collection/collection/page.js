import MyCollectionPageClient from "@/components/Profile/MyCollectionPageClient";
import { getPrivateCollectionEntries } from "@/lib/profile/collectionEntryLoader";

export default async function MyCollectionPage() {
  const initialItems = await getPrivateCollectionEntries();
  return <MyCollectionPageClient initialItems={initialItems} />;
}
