"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
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

function PortfolioChartTooltip({ active, payload, label }) {
  if (!active || !payload || !payload.length) return null;

  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] px-3 py-2 shadow-[0_8px_30px_rgba(0,0,0,0.35)]">
      <p className="text-xs font-medium text-[var(--text-secondary)]">{label}</p>
      <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">{formatMoney(payload[0].value)}</p>
    </div>
  );
}

function PerformanceMetricCard({ label, value, deltaLabel, deltaValue }) {
  const isPositive = typeof deltaValue === "number" ? deltaValue > 0 : null;
  const isNegative = typeof deltaValue === "number" ? deltaValue < 0 : null;

  return (
    <article className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.1em] text-[var(--text-secondary)]">{label}</p>
      <p className="mt-3 text-2xl font-semibold text-[var(--text-primary)]">{value}</p>
      <div className="mt-3">
        <span
          className={[
            "inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold",
            isPositive
              ? "border-green-400/25 bg-green-400/10 text-green-200"
              : isNegative
                ? "border-red-400/25 bg-red-400/10 text-red-200"
                : "border-[var(--border-subtle)] bg-[var(--surface-page)] text-[var(--text-secondary)]",
          ].join(" ")}
        >
          {deltaLabel}
        </span>
      </div>
    </article>
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
  const portfolioChange30d = 0;
  const performanceTrend = useMemo(
    () => [
      { date: "Jan 02", value: 3810 },
      { date: "Jan 09", value: 3925 },
      { date: "Jan 16", value: 3862 },
      { date: "Jan 23", value: 4020 },
      { date: "Jan 30", value: 4098 },
      { date: "Feb 06", value: 4215 },
      { date: "Feb 13", value: 4173 },
      { date: "Feb 20", value: 4330 },
      { date: "Feb 27", value: 4452 },
      { date: "Mar 06", value: 4381 },
      { date: "Mar 13", value: 4528 },
      { date: "Mar 20", value: 4680 },
      { date: "Mar 27", value: 4740 },
    ],
    []
  );
  const performanceMetrics = useMemo(
    () => [
      { label: "Portfolio Value", value: "$4,740", deltaLabel: "+8.2% (30d)", deltaValue: 8.2 },
      { label: "Cost Basis", value: "$4,500", deltaLabel: "+$120 this month", deltaValue: 2.7 },
      { label: "Profit / Loss", value: "+$240", deltaLabel: "+5.3% total", deltaValue: 5.3 },
      { label: "30 Day Change", value: "+$360", deltaLabel: "+8.2%", deltaValue: 8.2 },
    ],
    []
  );
  const portfolioHighlights = useMemo(
    () => [
      {
        signal: "Top Gainer",
        name: "Umbreon VMAX Alt Art",
        metric: "+12.4%",
        detail: "7d momentum",
        imageSrc: "https://images.pokemontcg.io/swsh7/215_hires.png",
      },
      {
        signal: "Most Valuable",
        name: "Charizard Gold Star",
        metric: "$1,240",
        detail: "Market value",
        imageSrc: "https://images.pokemontcg.io/ex12/100_hires.png",
      },
      {
        signal: "Newest Addition",
        name: "Blastoise EX",
        metric: "Added 2 hours ago",
        detail: "Latest portfolio entry",
        imageSrc: "https://images.pokemontcg.io/xy1/29_hires.png",
      },
      {
        signal: "Top Decliner",
        name: "Lugia VSTAR",
        metric: "-4.8%",
        detail: "7d pullback",
        imageSrc: "https://images.pokemontcg.io/swsh12/139_hires.png",
      },
    ],
    []
  );
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
    <main className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <div className="dashboard-container space-y-10">
      <section className="page-hero-panel rounded-2xl px-6 py-10 sm:px-8">
        <div className="grid grid-cols-1 gap-5 md:grid-cols-[1fr_auto] md:items-end">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">inDex</p>
            <h1 className="mt-1 text-[28px] font-bold text-[var(--text-primary)]">Profile</h1>
            <p className="mt-2 text-sm text-[var(--text-secondary)]">Collector identity, portfolio snapshot, and insights in one place.</p>
          </div>

          <div className="flex flex-wrap items-center gap-3 self-start md:justify-end md:self-auto">
            <div className="inline-flex w-fit items-center gap-3 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)] px-3 py-2 text-sm">
              <span className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Portfolio Value</span>
              <span className="font-semibold text-[var(--text-primary)]">{formatMoney(portfolioSnapshot.totalCollectionValue || 0)}</span>
              <span className="text-xs font-medium text-[var(--text-secondary)]">{formatPercent(portfolioChange30d)}</span>
            </div>
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
          <div className="flex h-20 w-20 items-center justify-center overflow-hidden rounded-full border border-[var(--border-subtle)] bg-brand text-2xl font-semibold text-white shadow-[0_0_0_2px_rgba(255,255,255,0.08)]">
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
              <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
                <div className="min-w-0 rounded-lg bg-white/[0.03] px-3 py-3">
                  <p className="text-xl font-semibold leading-none text-[var(--text-primary)]">{formatCount(portfolioSnapshot.cardsOwned || 0)}</p>
                  <p className="mt-2 text-xs font-medium uppercase tracking-[0.08em] text-[var(--text-secondary)] opacity-70">Cards</p>
                </div>
                <div className="min-w-0 rounded-lg bg-white/[0.03] px-3 py-3">
                  <p className="text-xl font-semibold leading-none text-[var(--text-primary)]">{formatCount(portfolioSnapshot.sealedProductsOwned || 0)}</p>
                  <p className="mt-2 text-xs font-medium uppercase tracking-[0.08em] text-[var(--text-secondary)] opacity-70">Sealed</p>
                </div>
                <div className="min-w-0 rounded-lg bg-white/[0.03] px-3 py-3">
                  <p className="text-xl font-semibold leading-none text-[var(--text-primary)]">{formatMoney(portfolioSnapshot.totalCollectionValue || 0)}</p>
                  <p className="mt-2 text-xs font-medium uppercase tracking-[0.08em] text-[var(--text-secondary)] opacity-70">Portfolio</p>
                </div>
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

      <ProfileSection
        title="Portfolio Performance"
        subtitle="Track your collection value over time like an asset portfolio"
      >
        <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-xs font-semibold uppercase tracking-[0.1em] text-[var(--text-secondary)]">Portfolio Value Trend</p>
            <div className="inline-flex items-center gap-1 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] p-1 text-xs">
              <span className="rounded-md bg-[var(--surface-hover)] px-2 py-1 font-semibold text-[var(--text-primary)]">30D</span>
              <span className="px-2 py-1 text-[var(--text-secondary)]">90D</span>
              <span className="px-2 py-1 text-[var(--text-secondary)]">1Y</span>
            </div>
          </div>

          <div className="mt-4 h-[360px] w-full sm:h-[420px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={performanceTrend} margin={{ top: 10, right: 14, left: 6, bottom: 0 }}>
                <defs>
                  <linearGradient id="portfolioArea" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#38bdf8" stopOpacity={0.35} />
                    <stop offset="95%" stopColor="#38bdf8" stopOpacity={0.03} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="rgba(255,255,255,0.08)" strokeDasharray="3 4" vertical={false} />
                <XAxis
                  dataKey="date"
                  tick={{ fill: "rgba(255,255,255,0.62)", fontSize: 12 }}
                  axisLine={{ stroke: "rgba(255,255,255,0.12)" }}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fill: "rgba(255,255,255,0.62)", fontSize: 12 }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(value) => `$${Math.round(value / 1000)}k`}
                />
                <Tooltip content={<PortfolioChartTooltip />} cursor={{ stroke: "rgba(56,189,248,0.35)", strokeWidth: 1 }} />
                <Area
                  type="monotone"
                  dataKey="value"
                  stroke="#38bdf8"
                  strokeWidth={2.5}
                  fill="url(#portfolioArea)"
                  activeDot={{ r: 4, stroke: "#38bdf8", strokeWidth: 1.5, fill: "#0f172a" }}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {performanceMetrics.map((metric) => (
              <PerformanceMetricCard
                key={metric.label}
                label={metric.label}
                value={metric.value}
                deltaLabel={metric.deltaLabel}
                deltaValue={metric.deltaValue}
              />
            ))}
          </div>
        </div>
      </ProfileSection>

      <ProfileSection
        title="Portfolio Highlights"
        subtitle="Key gainers, leaders, and recent additions across your collection"
      >
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {portfolioHighlights.map((item) => {
            const isPositive = item.metric.startsWith("+");
            const isNegative = item.metric.startsWith("-");

            return (
              <article
                key={item.signal}
                className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-4 transition-all duration-200 hover:-translate-y-0.5 hover:border-[var(--border-emphasis)] hover:shadow-[0_14px_28px_rgba(0,0,0,0.3)]"
              >
                <p className="text-xs font-semibold uppercase tracking-[0.1em] text-[var(--text-secondary)]">{item.signal}</p>
                <div className="mt-3 flex items-start gap-3">
                  <div className="h-20 w-14 shrink-0 overflow-hidden rounded-md border border-[var(--border-subtle)] bg-[var(--surface-page)]">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={item.imageSrc} alt={item.name} className="h-full w-full object-cover" loading="lazy" />
                  </div>
                  <div className="min-w-0">
                    <p className="line-clamp-2 text-sm font-semibold text-[var(--text-primary)]">{item.name}</p>
                    <p
                      className={[
                        "mt-2 text-base font-semibold",
                        isPositive ? "text-green-200" : isNegative ? "text-red-200" : "text-[var(--text-primary)]",
                      ].join(" ")}
                    >
                      {item.metric}
                    </p>
                    <p className="mt-1 text-xs text-[var(--text-secondary)]">{item.detail}</p>
                  </div>
                </div>
                <div className="mt-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] px-2.5 py-2">
                  <p className="text-xs text-[var(--text-secondary)]">Signal based on portfolio movement and valuation snapshots.</p>
                </div>
              </article>
            );
          })}
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
      </div>
    </main>
  );
}
