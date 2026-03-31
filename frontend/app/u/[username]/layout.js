import PublicProfileHeader from "@/components/Profile/PublicProfileHeader";
import PublicProfileTabs from "@/components/Profile/PublicProfileTabs";
import { getCachedPublicRouteContextByUsername } from "@/lib/profile/publicProfileServer";

export default async function PublicProfileLayout({ children, params }) {
  const { username } = await params;
  const { publicProfile, identity } = await getCachedPublicRouteContextByUsername(username || "");
  const joinDateLabel = publicProfile?.created_at
    ? new Date(publicProfile.created_at).toLocaleDateString("en-US", {
        year: "numeric",
        month: "short",
      })
    : "New collector";

  return (
    <main className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <div className="dashboard-container space-y-6">
        <PublicProfileHeader
          identity={identity}
          avatarUrl={publicProfile?.avatar_url || null}
          bio={publicProfile?.bio || "Collector profile details will appear here."}
          favoriteTcg={publicProfile?.favorite_tcg_name || "Favorite TCG not set"}
          joinDateLabel={joinDateLabel}
          visibility={
            publicProfile?.is_profile_public === true
              ? "Public"
              : publicProfile?.is_profile_public === false
                ? "Private"
                : "Visibility TBD"
          }
        />

        <PublicProfileTabs
          profileBaseHref={identity.profileHref}
          items={[
            { label: "Overview", href: identity.profileHref, exact: true },
            { label: "Collection", href: `${identity.profileHref}/collection` },
            { label: "Binder", href: `${identity.profileHref}/binder` },
            { label: "Shelf", href: `${identity.profileHref}/shelf` },
            { label: "Wishlist", href: `${identity.profileHref}/wishlist` },
            { label: "Activity", href: `${identity.profileHref}/activity` },
          ]}
        />

        {children}
      </div>
    </main>
  );
}
