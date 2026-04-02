import PublicCollectionViewWrapper from "@/components/Profile/PublicCollectionViewWrapper";
import { buildCollectionStats, getPublicCollectionEntries } from "@/lib/profile/collectionEntryLoader";

export default async function PublicCollectionPage({ params }) {
  const { username } = await params;
  const collectionItems = await getPublicCollectionEntries(username);

  return (
    <div className="space-y-6">
      <PublicCollectionViewWrapper
        username={username}
        items={collectionItems}
        stats={buildCollectionStats(collectionItems)}
      />
    </div>
  );
}
