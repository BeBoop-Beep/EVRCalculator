import PublicProfileHeader from "@/components/Profile/PublicProfileHeader";
import PublicProfileLocalScaffold from "@/components/Profile/PublicProfileLocalScaffold";
import { getCachedPublicRouteContextByUsername } from "@/lib/profile/publicProfileServer";
import { buildCollectionStats, getPublicCollectionEntries } from "@/lib/profile/collectionEntryLoader";

export default async function PublicProfileLayout({ children, params }) {
  const { username } = await params;
  const [{ publicProfile, identity }, publicItems] = await Promise.all([
    getCachedPublicRouteContextByUsername(username || ""),
    getPublicCollectionEntries(username || ""),
  ]);
  const stats = buildCollectionStats(publicItems);
  const collectionMetrics = {
    portfolioValue: stats.totalValue,
    cards: stats.cardsCount,
    sealed: stats.sealedCount,
    graded: stats.gradedCount,
  };
  const joinDateLabel = publicProfile?.created_at
    ? new Date(publicProfile.created_at).toLocaleDateString("en-US", {
        year: "numeric",
        month: "short",
      })
    : "New collector";
  const publicProfileHeaderProps = {
    identity,
    avatarUrl: publicProfile?.avatar_url || null,
    bio: publicProfile?.bio || "Collector profile details will appear here.",
    favoriteTcg: publicProfile?.favorite_tcg_name || "Favorite TCG not set",
    joinDateLabel,
    visibility:
      publicProfile?.is_profile_public === true
        ? "Public"
        : publicProfile?.is_profile_public === false
          ? "Private"
          : "Visibility TBD",
    collectionMetrics,
  };

  const renderProfileHeader = () => <PublicProfileHeader {...publicProfileHeaderProps} />;

  return (
    <main className="w-full pb-8 pt-4 lg:py-8">
      <div className="px-6 xl:hidden">{renderProfileHeader()}</div>

      <PublicProfileLocalScaffold
        profileBaseHref={identity.profileHref}
        desktopHeader={renderProfileHeader()}
      >
        {children}
      </PublicProfileLocalScaffold>
    </main>
  );
}
