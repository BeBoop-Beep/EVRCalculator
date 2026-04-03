import PublicProfileHeader from "@/components/Profile/PublicProfileHeader";
import PublicProfileLocalScaffold from "@/components/Profile/PublicProfileLocalScaffold";
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
  };

  const renderProfileHeader = () => (
    <section className="dashboard-container rounded-3xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/70 p-4 sm:p-5">
      <PublicProfileHeader {...publicProfileHeaderProps} />
    </section>
  );

  return (
    <main className="w-full">
      <div className="mx-auto w-full max-w-7xl px-6 py-8">
        <div className="mb-6 lg:hidden">{renderProfileHeader()}</div>

        <PublicProfileLocalScaffold
          profileBaseHref={identity.profileHref}
          desktopHeader={renderProfileHeader()}
        >
          {children}
        </PublicProfileLocalScaffold>
      </div>
    </main>
  );
}
