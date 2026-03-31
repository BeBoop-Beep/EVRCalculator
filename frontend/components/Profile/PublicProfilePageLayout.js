"use client";

import PublicProfileHero from "@/components/Profile/PublicProfileHero";

/**
 * @typedef {import("@/types/profile").UserProfileRow} UserProfileRow
 */

/**
 * PublicProfilePageLayout - Main layout wrapper for public profile pages
 * @param {Object} props
 * @param {UserProfileRow | null} [props.profile] - User profile data
 * @param {JSX.Element} props.children - Page content
 * @param {boolean} [props.isLoading] - Loading state
 * @returns {JSX.Element}
 */
export default function PublicProfilePageLayout({ profile, children, isLoading = false }) {
  if (isLoading) {
    return (
      <div className="space-y-8 p-6 md:p-8">
        <div className="animate-pulse">
          <div className="h-64 rounded-2xl bg-[var(--surface-hover)]" />
        </div>
      </div>
    );
  }

  if (!profile) {
    return (
      <div className="space-y-8 p-6 md:p-8">
        <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-page)] p-12 text-center">
          <p className="text-lg font-semibold text-[var(--text-primary)]">Profile not found</p>
          <p className="mt-2 text-sm text-[var(--text-secondary)]">The profile you're looking for doesn't exist or is private.</p>
        </div>
      </div>
    );
  }

  // Create identity object for PublicProfileHero
  const identity = {
    title: profile.display_name || profile.username || "Collector",
    avatarText: (profile.display_name || profile.username || "?").charAt(0).toUpperCase(),
    subtitle: profile.bio || `@${profile.username}`,
    secondaryHandle: `@${profile.username}`,
    profileHref: `/u/${profile.username}`,
  };

  const joinDate = profile.created_at
    ? new Date(profile.created_at).toLocaleDateString("en-US", {
        year: "numeric",
        month: "short",
        day: "numeric",
      })
    : null;

  return (
    <div className="space-y-8">
      {/* Header with Profile Info */}
      <div className="p-6 md:p-8">
        <PublicProfileHero identity={identity} avatarUrl={profile.avatar_url} />

        {/* Profile Meta Info */}
        <div className="mt-6 grid grid-cols-2 gap-4 md:grid-cols-4">
          {profile.location && (
            <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">
                Location
              </p>
              <p className="mt-2 font-medium text-[var(--text-primary)]">{profile.location}</p>
            </div>
          )}

          {profile.favorite_tcg_name && (
            <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">
                Favorite TCG
              </p>
              <p className="mt-2 font-medium text-[var(--text-primary)]">{profile.favorite_tcg_name}</p>
            </div>
          )}

          {joinDate && (
            <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">
                Joined
              </p>
              <p className="mt-2 font-medium text-[var(--text-primary)]">{joinDate}</p>
            </div>
          )}

          {profile.is_profile_public !== undefined && (
            <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">
                Visibility
              </p>
              <p className="mt-2 font-medium text-[var(--text-primary)]">
                {profile.is_profile_public ? "🌐 Public" : "🔒 Private"}
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Page Content */}
      <div className="px-6 pb-8 md:px-8">{children}</div>
    </div>
  );
}
