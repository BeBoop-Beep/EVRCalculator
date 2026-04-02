import CollectionFeaturedHighlight from "@/components/Profile/CollectionFeaturedHighlight";

export default function PublicFeaturedItemsSection({ showcase = null, username = "" }) {
  return (
    <CollectionFeaturedHighlight
      showcase={showcase}
      mode="public"
      username={username}
      title="Portfolio Showcase"
      subtitle="Read-only view of this collector's Top Conviction Hold, Spotlight Asset, and Biggest Gainer."
      emptyMessage="No showcase assets are available for this profile yet."
    />
  );
}
