import Link from "next/link";
import { getRipStatisticsTargets } from "@/lib/explore/ripStatisticsServer";
import RankBadge from "@/components/ui/RankBadge";
import SetIdentity from "@/components/explore/SetIdentity";
import InfoPopover from "@/components/ui/InfoPopover";
import ExploreTableClient from "@/components/explore/ExploreTableClient";
import { getDangerValueStyle } from "@/lib/explore/interpretationTone";
import { isPublicAnalyticsEligiblePokemonSet } from "@/lib/pokemon/pokemonSetPublicCoverage";

const currencyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

function toNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function normalizeProbability(value) {
  const parsed = toNumber(value);
  if (parsed === null) {
    return null;
  }
  return parsed > 1 ? parsed / 100 : parsed;
}

function formatScore(value) {
  const parsed = toNumber(value);
  return parsed === null ? "-" : parsed.toFixed(1);
}

function formatCurrency(value) {
  const parsed = toNumber(value);
  return parsed === null ? "-" : currencyFormatter.format(parsed);
}

function formatLossCurrency(value) {
  const parsed = toNumber(value);
  return parsed === null ? "-" : `-${currencyFormatter.format(Math.abs(parsed))}`;
}

function shortenCanonicalLabel(value) {
  const text = String(value || "").trim();
  if (!text) {
    return null;
  }
  for (const separator of [",", " - ", " — "]) {
    if (text.includes(separator)) {
      const [head] = text.split(separator, 1);
      return head.trim() || text;
    }
  }
  return text;
}

function getLeaderboardRecommendationLabel(target) {
  return (
    target?.leaderboard_label ||
    shortenCanonicalLabel(target?.canonical_recommendation_header) ||
    null
  );
}

function getExploreRankingBadgeLabel(label) {
  return String(label || "").replace(/\s+PROFILE$/i, "").trim();
}

function formatPercent(value, probability = false) {
  const parsed = toNumber(value);
  if (parsed === null) {
    return "-";
  }
  const normalized = probability ? normalizeProbability(parsed) * 100 : parsed;
  return `${normalized.toFixed(1)}%`;
}

function estimateAverageLoss(target) {
  const packCost = toNumber(target?.pack_cost);
  const meanValue = toNumber(target?.mean_value);
  if (packCost === null || meanValue === null) {
    return null;
  }
  return packCost - meanValue;
}

function buildRipLink(target) {
  if (!target?.target_type || !target?.target_id) {
    return "/Explore/rip-statistics";
  }
  return `/Explore/rip-statistics?target_type=${encodeURIComponent(target.target_type)}&target_id=${encodeURIComponent(target.target_id)}`;
}

function rankTargets(targets) {
  return [...targets].sort((left, right) => {
    const leftRank = toNumber(left?.pack_rank);
    const rightRank = toNumber(right?.pack_rank);

    if (leftRank !== null && rightRank !== null && leftRank !== rightRank) {
      return leftRank - rightRank;
    }

    if (leftRank !== null && rightRank === null) {
      return -1;
    }

    if (leftRank === null && rightRank !== null) {
      return 1;
    }

    const leftScore = toNumber(left?.relative_pack_score) ?? -Infinity;
    const rightScore = toNumber(right?.relative_pack_score) ?? -Infinity;
    if (leftScore !== rightScore) {
      return rightScore - leftScore;
    }

    return String(left?.name || "").localeCompare(String(right?.name || ""));
  });
}

function RipStatisticsCardArt() {
  return (
    <div className="relative h-full w-full bg-[radial-gradient(circle_at_top,_rgba(36,60,88,0.35)_0%,_rgba(9,14,22,0.95)_62%)]">
      <div className="absolute inset-0 opacity-40 [background-image:linear-gradient(rgba(255,255,255,0.05)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.05)_1px,transparent_1px)] [background-size:22px_22px]" />

      <div className="relative z-10 flex h-full gap-3 p-3 sm:p-4">
        <div className="flex w-[36%] flex-col gap-2 rounded-lg border border-white/10 bg-black/35 p-2.5">
          <span className="text-[10px] uppercase tracking-[0.1em] text-white/65">Rip Score</span>
          <div className="text-3xl font-semibold leading-none text-white sm:text-4xl">64</div>
          <span className="inline-flex w-fit rounded-full border border-emerald-300/35 bg-emerald-400/15 px-2 py-0.5 text-[10px] font-medium text-emerald-200">
            Rank A
          </span>
        </div>

        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <div className="grid grid-cols-3 gap-2">
            <div className="rounded-md border border-white/10 bg-black/30 p-1.5">
              <div className="h-9 w-full rounded bg-emerald-300/70" />
            </div>
            <div className="rounded-md border border-white/10 bg-black/30 p-1.5">
              <div className="h-9 w-full rounded bg-sky-300/65" />
            </div>
            <div className="rounded-md border border-white/10 bg-black/30 p-1.5">
              <div className="h-9 w-full rounded bg-amber-300/65" />
            </div>
          </div>

          <div className="flex min-h-0 flex-1 items-end gap-1 rounded-md border border-white/10 bg-black/30 px-2 pb-2 pt-3">
            <div className="h-[22%] w-2 rounded-sm bg-slate-200/65" />
            <div className="h-[36%] w-2 rounded-sm bg-slate-200/65" />
            <div className="h-[50%] w-2 rounded-sm bg-slate-200/70" />
            <div className="h-[62%] w-2 rounded-sm bg-slate-100/75" />
            <div className="h-[74%] w-2 rounded-sm bg-white/80" />
            <div className="h-[58%] w-2 rounded-sm bg-slate-100/75" />
            <div className="h-[43%] w-2 rounded-sm bg-slate-200/70" />
            <div className="h-[29%] w-2 rounded-sm bg-slate-200/65" />
          </div>
        </div>
      </div>
    </div>
  );
}

function TopRankingsPreview() {
  const groups = [
    {
      label: "Sets",
      description: "Best set-level opens and tier movement.",
    },
    {
      label: "Cards",
      description: "Top card movers and value concentration.",
    },
    {
      label: "Chases",
      description: "High-upside targets and hit probability.",
    },
  ];

  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[linear-gradient(180deg,rgba(13,22,36,0.98)_0%,rgba(10,16,28,0.98)_100%)] p-3.5 sm:p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="inline-flex items-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
          Rankings Preview
        </span>
      </div>

      <div className="mt-3 space-y-2.5">
        {groups.map((group) => (
          <div
            key={group.label}
            className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)]/55 px-3 py-2.5"
          >
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-primary)]">{group.label}</p>
            <p className="mt-1 text-xs text-[var(--text-secondary)]">{group.description}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

export default async function ExplorePage({ searchParams }) {
  const resolvedSearchParams = (await searchParams) || {};
  const payload = await getRipStatisticsTargets({ limit: 60 }).catch(() => null);
  const targets = Array.isArray(payload?.targets) ? payload.targets : [];
  // Sword & Shield's simulator-era data is not yet validated for public
  // analytics (incomplete pull/hit-rate model, unblended subsets) — see
  // pokemonSetPublicCoverage.js. Filtering here means every consumer below
  // (the ranked table, its "N RANKED SETS" count) only ever sees eligible
  // sets; this never touches how pack_score/relative scores are computed.
  const eligibleTargets = targets.filter(isPublicAnalyticsEligiblePokemonSet);
  const sortedTargets = rankTargets(eligibleTargets);
  const leaderboardTargets = sortedTargets;
  // requestFailed marks a genuine fetch/backend failure (see
  // ripStatisticsServer.js's withTargetsRequestFailureMeta) as distinct from
  // a real "no ranked sets yet" empty result — payload === null covers the
  // unexpected-throw case the .catch above guards against.
  const rankingsLoadError = payload === null || Boolean(payload?.meta?.requestFailed);

  return (
    <main className="mx-auto w-full max-w-7xl px-4 py-8 pb-24 sm:px-6 lg:px-8">
      <div className="dashboard-container space-y-6 !border-0 !bg-transparent !p-0 md:!rounded-2xl md:!border md:!border-[rgba(255,255,255,0.04)] md:!bg-[rgba(255,255,255,0.02)] md:!p-6">
        <div className="px-1 sm:px-0">
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-semibold text-[var(--text-primary)]">Explore</h1>
            <InfoPopover text="Explore highlights the strongest sets, cards, chases, and market signals based on current data." />
          </div>
        </div>

        <ExploreTableClient targets={leaderboardTargets} loadError={rankingsLoadError} />

        <section className="grid grid-cols-1 gap-4">
          <article className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-5 sm:p-6">
            <h2 className="text-xl font-semibold text-[var(--text-primary)]">Top Rankings</h2>
            <p className="mt-2 text-sm leading-relaxed text-[var(--text-secondary)]">
              Compare the strongest sets, cards, chases, and market movers in one rankings view.
            </p>

            <div className="mt-5">
              <TopRankingsPreview />
            </div>

            <div className="mt-5">
              <Link
                href="/Explore/top-10"
                className="inline-flex items-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] px-4 py-2 text-sm font-medium text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-hover)]"
              >
                Preview Top Rankings
                <span aria-hidden="true">→</span>
              </Link>
            </div>
          </article>
        </section>
      </div>
    </main>
  );
}
