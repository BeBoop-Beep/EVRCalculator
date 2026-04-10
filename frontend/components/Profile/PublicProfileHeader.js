"use client";

import { usePathname } from "next/navigation";

export default function PublicProfileHeader({
  identity,
  avatarUrl,
  bio,
  favoriteTcg,
  joinDateLabel,
  visibility,
  collectionMetrics,
}) {
  const pathname = usePathname();
  const isCollectionRoute = Boolean(pathname?.includes("/collection"));
  const subtitle = identity.subtitle || identity.handle;

  return (
    <section className="page-hero-panel overflow-hidden rounded-2xl px-4 py-5 sm:px-8 sm:py-5">
      <div className="grid gap-4 sm:gap-6 lg:grid-cols-[1fr_auto] lg:items-end">
        <div className="flex items-start gap-4 sm:gap-5">
          <div className="flex h-16 w-16 shrink-0 items-center justify-center overflow-hidden rounded-full border border-[var(--border-subtle)] bg-brand text-xl font-semibold text-white shadow-[0_0_0_2px_rgba(255,255,255,0.06)] sm:h-20 sm:w-20 sm:text-2xl">
            {avatarUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={avatarUrl} alt={`${identity.username} avatar`} className="h-full w-full object-cover" />
            ) : (
              identity.avatarText
            )}
          </div>

          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-secondary)]">Collector Showcase</p>
            <h1 className="mt-2 text-3xl font-bold leading-tight text-[var(--text-primary)] sm:text-4xl">{identity.title}</h1>
            <p className="mt-1 text-sm text-[var(--text-secondary)]">{subtitle}</p>
            <p className="mt-2 sm:mt-3 max-w-2xl text-sm leading-relaxed text-[var(--text-secondary)]">{bio}</p>
          </div>
        </div>

        {isCollectionRoute && collectionMetrics ? (
          <div className="w-full space-y-2 sm:mx-auto sm:max-w-[28rem] lg:mx-0 lg:w-[28rem]">
            <PortfolioValueCell
              value={collectionMetrics.portfolioValue}
              delta1d={collectionMetrics.portfolioDelta1d}
              deltaPct1d={collectionMetrics.portfolioDeltaPct1d}
            />
            <div className="grid grid-cols-3 gap-2">
              <MetricCell label="Cards" value={collectionMetrics.cards} />
              <MetricCell label="Sealed" value={collectionMetrics.sealed} />
              <MetricCell label="Graded" value={collectionMetrics.graded} />
            </div>
          </div>
        ) : (
          <div className="flex flex-wrap justify-center gap-1.5 sm:mx-auto sm:grid sm:w-full sm:max-w-[28rem] sm:grid-cols-3 sm:justify-items-center sm:gap-2 lg:mx-0 lg:w-[28rem] lg:justify-items-stretch">
            <MetaPill label="Favorite TCG" shortLabel="TCG" value={favoriteTcg} />
            <MetaPill label="Joined" shortLabel="Joined" value={joinDateLabel} />
            <MetaPill label="Visibility" shortLabel="Visibility" value={visibility} />
          </div>
        )}
      </div>
    </section>
  );
}

function toFiniteNumberOrNull(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }

  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatSignedCurrencyDelta(value) {
  const parsed = toFiniteNumberOrNull(value);
  const amount = Math.abs(parsed ?? 0);
  const formattedAmount = `$${amount.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;

  if ((parsed ?? 0) > 0) {
    return `+${formattedAmount}`;
  }

  if ((parsed ?? 0) < 0) {
    return `-${formattedAmount}`;
  }

  return formattedAmount;
}

function formatDeltaPercent(value) {
  const parsed = toFiniteNumberOrNull(value);

  if (parsed === null) {
    return "—";
  }

  const sign = parsed > 0 ? "+" : parsed < 0 ? "-" : "";
  return `${sign}${Math.abs(parsed).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}%`;
}

function getDeltaToneClass(value) {
  const parsed = toFiniteNumberOrNull(value) ?? 0;

  if (parsed > 0) {
    return "text-emerald-400";
  }

  if (parsed < 0) {
    return "text-rose-400";
  }

  return "text-[var(--text-secondary)]";
}

function PortfolioValueCell({ value, delta1d, deltaPct1d }) {
  const deltaLabel = `${formatSignedCurrencyDelta(delta1d)} (${formatDeltaPercent(deltaPct1d)}) 1D`;
  const deltaToneClass = getDeltaToneClass(delta1d);

  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-[var(--border-subtle)] bg-[rgba(255,255,255,0.02)] px-3 py-3 text-center">
      <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--text-secondary)]">Portfolio Value</p>
      <p className="mt-1 text-2xl font-bold text-[var(--text-primary)]">{value}</p>
      <p className={`mt-1 text-xs font-semibold ${deltaToneClass}`}>{deltaLabel}</p>
    </div>
  );
}

function MetricCell({ label, value }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-[var(--border-subtle)] bg-[rgba(255,255,255,0.02)] px-2 py-2 text-center">
      <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--text-secondary)]">{label}</p>
      <p className="mt-0.5 truncate text-sm font-semibold text-[var(--text-primary)]">{value}</p>
    </div>
  );
}

function MetaPill({ label, shortLabel, value }) {
  return (
    <div className="inline-flex min-w-0 items-center justify-center gap-1.5 rounded-lg border border-[var(--border-subtle)] bg-[rgba(255,255,255,0.02)] px-2 py-1.5 text-center sm:block sm:w-full sm:rounded-xl sm:px-3 sm:py-2">
      <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--text-secondary)] sm:hidden">{shortLabel}</p>
      <p className="hidden text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)] sm:block">{label}</p>
      <p className="truncate text-xs font-medium text-[var(--text-primary)] sm:mt-1 sm:text-sm">{value}</p>
    </div>
  );
}
