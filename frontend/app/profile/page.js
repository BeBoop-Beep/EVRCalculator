"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import ProfileSection from "@/components/Profile/ProfileSection";
import ProfileStatCard from "@/components/Profile/ProfileStatCard";
import { getCurrentUserProfile } from "@/lib/profile/profileClient";

/** @typedef {import("@/types/profile").UserProfileRow} UserProfileRow */
/** @typedef {import("@/types/profile").PortfolioSnapshot} PortfolioSnapshot */

const PLACEHOLDER_SNAPSHOT = {
  totalCollectionValue: null,
  cardsOwned: null,
  sealedProductsOwned: null,
  costBasis: null,
  profitLoss: null,
};

function formatDateLabel(dateValue) {
  if (!dateValue) return "Unknown";

  const parsedDate = new Date(dateValue);
  if (Number.isNaN(parsedDate.getTime())) return "Unknown";

  return parsedDate.toLocaleDateString(undefined, {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

function formatMoney(value) {
  if (typeof value !== "number") return "--";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value);
}

function formatCount(value) {
  if (typeof value !== "number") return "--";
  return new Intl.NumberFormat("en-US").format(value);
}

function getAvatarText(profile) {
  const source = profile?.display_name || profile?.username || profile?.email || "U";
  return source.trim().slice(0, 1).toUpperCase();
}

function formatPercent(value) {
  if (typeof value !== "number") return "0%";
  const sign = value > 0 ? "+" : "";
  return sign + value + "%";
}

function PlaceholderPanel({ title, description, ctaHref, ctaLabel }) {
  return (
    <ProfileSection title={title} subtitle={description}>
      <div className="rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--surface-page)] px-4 py-8 text-center">
        <p className="text-sm text-[var(--text-secondary)]">No data available yet. This section is ready for live data wiring.</p>
        {ctaHref && ctaLabel ? (
          <Link
            href={ctaHref}
            className="mt-4 inline-flex rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-dark"
          >
            {ctaLabel}
          </Link>
        ) : null}
      </div>
    </ProfileSection>
  );
}

export default function ProfilePage() {
  const router = useRouter();
  const pathname = usePathname();
  /** @type {[UserProfileRow | null, Function]} */
  const [profile, setProfile] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    let mounted = true;

    const loadProfile = async () => {
      setIsLoading(true);
      setErrorMessage("");

      try {
        const data = await getCurrentUserProfile();
        if (!mounted) return;
        setProfile(data.profile);
      } catch (error) {
        if (!mounted) return;

        if (error?.status === 401) {
          router.push("/login");
          return;
        }

        setErrorMessage(error?.message || "Unable to load your profile right now.");
      } finally {
        if (mounted) setIsLoading(false);
      }
    };

    loadProfile();

    return () => {
      mounted = false;
    };
  }, [router]);

  /** @type {PortfolioSnapshot} */
  const portfolioSnapshot = useMemo(() => ({ ...PLACEHOLDER_SNAPSHOT }), []);
  const totalOwnedCount =
    (typeof portfolioSnapshot.cardsOwned === "number" ? portfolioSnapshot.cardsOwned : 0) +
    (typeof portfolioSnapshot.sealedProductsOwned === "number" ? portfolioSnapshot.sealedProductsOwned : 0);
  const portfolioChange30d = 0;
  const collectionNavItems = [
    { label: "Collection", href: "/dashboard/Collection" },
    { label: "Binder", href: "/dashboard/Binder" },
    { label: "Shelf", href: "/dashboard/Shelf" },
    { label: "Wishlist", href: "/dashboard/Watchlist" },
  ];

  if (isLoading) {
    return (
      <main className="mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
        <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-8">
          <p className="text-sm font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Profile</p>
          <p className="mt-3 text-base text-[var(--text-primary)]">Loading profile...</p>
        </div>
      </main>
    );
  }

  if (errorMessage) {
    return (
      <main className="mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
        <div className="rounded-2xl border border-red-500/30 bg-[var(--surface-panel)] p-8">
          <h1 className="text-2xl font-semibold text-[var(--text-primary)]">Profile unavailable</h1>
          <p className="mt-2 text-sm text-red-300">{errorMessage}</p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="mt-4 rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-dark"
          >
            Retry
          </button>
        </div>
      </main>
    );
  }

  if (!profile) {
    return (
      <main className="mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
        <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-8">
          <h1 className="text-2xl font-semibold text-[var(--text-primary)]">Profile not found</h1>
          <p className="mt-2 text-sm text-[var(--text-secondary)]">We could not find a profile record for this account yet.</p>
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto w-full max-w-7xl space-y-6 px-4 py-8 sm:px-6 lg:px-8">
      <section className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] px-6 py-5">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-[1fr_auto] md:items-end">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">inDex</p>
            <h1 className="mt-1 text-2xl font-semibold text-[var(--text-primary)]">Profile</h1>
            <p className="mt-2 text-sm text-[var(--text-secondary)]">Collector identity, portfolio snapshot, and insights in one place.</p>
          </div>

          <div className="inline-flex w-fit items-center gap-3 self-start rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)] px-3 py-2 text-sm md:self-auto">
            <span className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Portfolio Value</span>
            <span className="font-semibold text-[var(--text-primary)]">{formatMoney(portfolioSnapshot.totalCollectionValue || 0)}</span>
            <span className="text-xs font-medium text-[var(--text-secondary)]">{formatPercent(portfolioChange30d)}</span>
          </div>
        </div>
      </section>

      <ProfileSection
        title="Collector"
        subtitle="Identity and account overview"
        actions={
          <Link href="/account-settings" className="rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-dark">
            Edit Settings
          </Link>
        }
      >
        <div className="grid gap-5 md:grid-cols-[auto_1fr]">
          <div className="flex h-20 w-20 items-center justify-center overflow-hidden rounded-full border border-[var(--border-subtle)] bg-brand text-2xl font-semibold text-white">
            {profile.avatar_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={profile.avatar_url} alt="Profile avatar" className="h-full w-full object-cover" />
            ) : (
              getAvatarText(profile)
            )}
          </div>

          <div>
            <h1 className="text-2xl font-semibold text-[var(--text-primary)]">{profile.display_name || "Collector"}</h1>
            <p className="mt-1 text-sm text-[var(--text-secondary)]">@{profile.username || "collector"}</p>
            <div className="mt-4 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] px-4 py-3">
              <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Collector Stats</p>
              <div className="mt-2 flex flex-wrap items-center gap-2 text-sm font-medium text-[var(--text-secondary)]">
                <span>• {formatCount(totalOwnedCount)} cards</span>
                <span>• {formatCount(portfolioSnapshot.sealedProductsOwned || 0)} sealed</span>
                <span>• {formatMoney(portfolioSnapshot.totalCollectionValue || 0)} portfolio</span>
              </div>
            </div>
            <div className="mt-4 rounded-lg border border-dashed border-[var(--border-subtle)] bg-[var(--surface-page)] px-4 py-3">
              <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Badges</p>
              <p className="mt-2 text-sm text-[var(--text-secondary)]">Badge showcase coming soon.</p>
            </div>
            <p className="mt-3 text-sm text-[var(--text-secondary)]">{profile.bio || "No bio added yet."}</p>

            <div className="mt-4 grid gap-2 text-sm text-[var(--text-secondary)] sm:grid-cols-2">
              <p>
                <span className="font-semibold text-[var(--text-primary)]">Location:</span> {profile.location || "Not set"}
              </p>
              <p>
                <span className="font-semibold text-[var(--text-primary)]">Joined:</span> {formatDateLabel(profile.created_at)}
              </p>
              <p>
                <span className="font-semibold text-[var(--text-primary)]">Favorite TCG:</span> {profile.favorite_tcg_name || "Not selected"}
              </p>
              <p>
                <span className="font-semibold text-[var(--text-primary)]">Visibility:</span>{" "}
                {profile.is_profile_public ? "Public profile" : "Private profile"}
              </p>
            </div>
          </div>
        </div>
      </ProfileSection>

      <ProfileSection
        title="Portfolio Snapshot"
        subtitle="Live metrics will populate as portfolio entities are connected"
      >
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          <ProfileStatCard
            label="Total Collection Value"
            value={formatMoney(portfolioSnapshot.totalCollectionValue)}
            subValue={formatPercent(portfolioChange30d) + " (30d)"}
            hint="Market value across your collection"
          />
          <ProfileStatCard label="Cards Owned" value={formatCount(portfolioSnapshot.cardsOwned)} hint="Singles tracked in your inventory" />
          <ProfileStatCard label="Sealed Products" value={formatCount(portfolioSnapshot.sealedProductsOwned)} hint="Boxes, ETBs, and sealed items" />
          <ProfileStatCard label="Cost Basis" value={formatMoney(portfolioSnapshot.costBasis)} hint="Total amount invested" />
          <ProfileStatCard
            label="Profit / Loss"
            value={formatMoney(portfolioSnapshot.profitLoss)}
            hint="Current valuation minus cost basis"
            valueClassName={
              typeof portfolioSnapshot.profitLoss === "number"
                ? portfolioSnapshot.profitLoss > 0
                  ? "text-success"
                  : portfolioSnapshot.profitLoss < 0
                    ? "text-danger"
                    : "text-[var(--text-secondary)]"
                : ""
            }
          />
        </div>

        <div className="mt-6 rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-5">
          <p className="text-xs font-semibold uppercase tracking-[0.1em] text-[var(--text-secondary)]">My Collection</p>
          <nav aria-label="My Collection" className="mt-3">
            <div className="flex flex-wrap gap-2">
              {collectionNavItems.map((item) => {
                const isActive = pathname === item.href || pathname?.startsWith(item.href + "/");

                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    aria-current={isActive ? "page" : undefined}
                    className={[
                      "inline-flex items-center rounded-xl border px-4 py-2 text-sm font-medium transition-colors",
                      isActive
                        ? "border-[var(--border-subtle)] bg-[var(--surface-hover)] text-[var(--text-primary)]"
                        : "border-[var(--border-subtle)] bg-[var(--surface-page)] text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]",
                    ].join(" ")}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </div>
          </nav>
          <p className="mt-3 text-xs text-[var(--text-secondary)]">Jump directly into each collection workspace.</p>
        </div>

        <div className="mt-4 rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-5">
          <p className="text-xs font-semibold uppercase tracking-[0.1em] text-[var(--text-secondary)]">Quick Actions</p>
          <div className="mt-3 flex flex-wrap gap-2.5">
            <button
              type="button"
              className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)] px-4 py-2 text-sm font-medium text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]"
            >
              Add Card
            </button>
            <button
              type="button"
              className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)] px-4 py-2 text-sm font-medium text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]"
            >
              Add Sealed Product
            </button>
            <button
              type="button"
              className="rounded-xl border border-[var(--border-subtle)] bg-brand px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-brand-dark"
            >
              Import Collection
            </button>
          </div>
        </div>
      </ProfileSection>

      <PlaceholderPanel
        title="Collection Breakdown"
        description="Category and TCG distribution"
      />

      <ProfileSection
        title="Portfolio Performance"
        subtitle="Track how your collection value changes over time"
      >
        <div className="rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--surface-page)] px-4 py-12 text-center">
          <p className="text-sm text-[var(--text-secondary)]">No data available yet. Chart container is ready for Recharts or Chart.js integration.</p>
        </div>
      </ProfileSection>

      <ProfileSection
        title="Featured Items"
        subtitle="Card and sealed spotlights"
      >
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((item) => (
            <article key={item} className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-6">
              <div className="flex aspect-[4/3] items-center justify-center rounded-lg border border-dashed border-[var(--border-subtle)] bg-[var(--surface-page)]">
                <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Card Image</p>
              </div>
              <p className="mt-4 text-base font-semibold text-[var(--text-primary)]">Item Name Placeholder</p>
              <div className="mt-2 flex items-center justify-between text-sm">
                <span className="font-semibold text-[var(--text-primary)]">$0.00</span>
                <span className="font-semibold text-[var(--text-secondary)]">0.0%</span>
              </div>
            </article>
          ))}
        </div>
      </ProfileSection>

      {profile.show_activity ? (
        <ProfileSection title="Activity" subtitle="Your recent collector actions">
          <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)] p-6">
            <div className="space-y-4">
              {[
                "Default example: Added Charizard EX",
                "Default example: Added Evolving Skies Booster Box",
                "Default example: Price update detected",
              ].map((entry) => (
                <div key={entry} className="flex items-start gap-3 border-l-2 border-[var(--border-subtle)] pl-4">
                  <div className="mt-2 h-2 w-2 rounded-full bg-brand" />
                  <div>
                    <p className="text-sm font-medium text-[var(--text-primary)]">{entry}</p>
                    <p className="mt-1 text-xs text-[var(--text-secondary)]">Default message shown until live activity data is connected.</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </ProfileSection>
      ) : null}

      <ProfileSection
        title="Analytics Insights"
        subtitle="Signals and recommendations powered by your portfolio"
      >
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
          <article className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-6">
            <p className="text-sm font-medium text-[var(--text-primary)]">Default example insight: Your portfolio outperformed the Pokemon market by 8% this month.</p>
            <p className="mt-2 text-xs text-[var(--text-secondary)]">Not based on live portfolio analytics yet.</p>
          </article>
          <article className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-6">
            <p className="text-sm font-medium text-[var(--text-primary)]">Default example insight: Sealed products grew 22% in the last 90 days.</p>
            <p className="mt-2 text-xs text-[var(--text-secondary)]">Not based on live portfolio analytics yet.</p>
          </article>
          <article className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-6">
            <p className="text-sm font-medium text-[var(--text-primary)]">Default state: Insights will update automatically once analytics data is available.</p>
            <p className="mt-2 text-xs text-[var(--text-secondary)]">This card currently uses fallback copy.</p>
          </article>
        </div>
      </ProfileSection>
    </main>
  );
}
