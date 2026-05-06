import Link from "next/link";
import { getRipStatisticsTargets } from "@/lib/explore/ripStatisticsServer";
import RankBadge from "@/components/ui/RankBadge";
import SetIdentity from "@/components/explore/SetIdentity";
import InfoPopover from "@/components/ui/InfoPopover";
import { getDangerValueStyle } from "@/lib/explore/interpretationTone";

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
function getDisplayedScoreValue(target) {
  const relativeScore = toNumber(target?.relative_pack_score);
  return relativeScore;
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

    const leftScore = toNumber(left?.pack_score) ?? -Infinity;
    const rightScore = toNumber(right?.pack_score) ?? -Infinity;
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
  await searchParams;
  const payload = await getRipStatisticsTargets({ limit: 60 }).catch(() => null);
  const targets = Array.isArray(payload?.targets) ? payload.targets : [];
  const sortedTargets = rankTargets(targets);
  const leaderboardTargets = sortedTargets;
  const isScrollable = leaderboardTargets.length > 5;
  const leaderboardScrollClass = "index-scrollbar";

  return (
    <main className="mx-auto w-full max-w-7xl px-4 py-8 pb-24 sm:px-6 lg:px-8">
      <div className="dashboard-container space-y-6 !border-0 !bg-transparent !p-0 md:!rounded-2xl md:!border md:!border-[rgba(255,255,255,0.04)] md:!bg-[rgba(255,255,255,0.02)] md:!p-6">
        <div className="px-1 sm:px-0">
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-semibold text-[var(--text-primary)]">Explore</h1>
            <InfoPopover text="Explore highlights the strongest sets, cards, chases, and market signals based on current data." />
          </div>
        </div>

        <section className="rounded-2xl border border-[var(--border-subtle)] bg-[linear-gradient(180deg,rgba(16,26,40,0.95)_0%,rgba(10,16,28,0.95)_100%)] p-4 lg:p-6">
          <div className="flex flex-col gap-3 border-b border-[var(--border-subtle)] pb-4 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-semibold text-[var(--text-primary)]">Best Sets to Rip Right Now</h2>
                <InfoPopover text="Rankings compare simulated pack outcomes against the current market cost of each pack. A set can rank highly when its cards are paying back well relative to what the pack costs, even if the set is not the most popular." />
              </div>
            </div>
            <div className="flex items-start sm:items-center">
              <div className="inline-flex items-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)] px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
                {leaderboardTargets.length} ranked sets
              </div>
            </div>
          </div>

          <p className="mt-3 text-xs text-[var(--text-secondary)] md:text-center">
            Tap a set to see the full rip breakdown.
          </p>

          {leaderboardTargets.length > 0 ? (
            <>
              <div className="mt-4 hidden md:block">
                <div className="grid grid-cols-[minmax(0,2.3fr)_0.9fr_0.8fr_1fr_1.05fr] gap-3 px-3 pb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
                  <span>Set</span>
                  <span>Tier</span>
                  <span>Rip Score</span>
                  <span>Average Loss</span>
                  <span>Chance to Beat Cost</span>
                </div>

                <div className={isScrollable ? `max-h-[34rem] space-y-2 overflow-y-auto pr-1 ${leaderboardScrollClass}` : "space-y-2"}>
                  {leaderboardTargets.map((target) => {
                    const averageLoss = estimateAverageLoss(target);
                    const displayedScore = getDisplayedScoreValue(target);
                    const recommendationLabel = getLeaderboardRecommendationLabel(target);
                    const displayRecommendationLabel = getExploreRankingBadgeLabel(recommendationLabel);
                    const tier = String(target?.pack_tier || "").toUpperCase() || null;
                    return (
                      <Link
                        key={`${target.target_type}:${target.target_id}`}
                        href={buildRipLink(target)}
                        className="grid grid-cols-[minmax(0,2.3fr)_0.9fr_0.8fr_1fr_1.05fr] items-center gap-3 rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/65 px-4 py-3.5 transition-colors hover:bg-[var(--surface-hover)]"
                      >
                        <div className="min-w-0">
                          <SetIdentity
                            target={target}
                            interpretationLabel={displayRecommendationLabel}
                            tier={tier}
                            recommendationSeverity={target?.recommendation_severity || null}
                          />
                        </div>
                        <div className="flex items-start">
                          <RankBadge
                            rank={tier}
                            title="Set tier"
                            size="supporting"
                            format="tier"
                          />
                        </div>
                        <span className="text-sm font-semibold text-[var(--text-primary)]">{formatScore(displayedScore)}</span>
                        <span className="text-sm font-semibold" style={getDangerValueStyle()}>
                          {formatLossCurrency(averageLoss)}
                        </span>
                        <span className="text-sm text-[var(--text-primary)]">{formatPercent(target?.prob_profit, true)}</span>
                      </Link>
                    );
                  })}
                </div>
              </div>

              <div className={isScrollable ? `mt-4 grid max-h-[38rem] grid-cols-1 gap-2 overflow-y-auto pr-1 md:hidden ${leaderboardScrollClass}` : "mt-4 grid grid-cols-1 gap-2 md:hidden"}>
                {leaderboardTargets.map((target) => {
                  const recommendationLabel = getLeaderboardRecommendationLabel(target);
                  const displayRecommendationLabel = getExploreRankingBadgeLabel(recommendationLabel);
                  const tier = String(target?.pack_tier || "").toUpperCase() || null;
                  return (
                    <Link
                      key={`${target.target_type}:${target.target_id}`}
                      href={buildRipLink(target)}
                      className="flex items-center gap-3 rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/65 p-3 transition-colors hover:bg-[var(--surface-hover)]"
                    >
                      <SetIdentity
                        target={target}
                        interpretationLabel={displayRecommendationLabel}
                        tier={tier}
                        recommendationSeverity={target?.recommendation_severity || null}
                        interpretationBadgeClassName="inline-flex max-w-full min-w-0 items-center whitespace-nowrap truncate px-3 py-1 text-[10px] leading-none tracking-[0.08em] sm:px-2.5 sm:py-1 sm:text-[11px]"
                      />
                      <div className="flex flex-none items-center self-start pt-1">
                        <RankBadge
                          rank={tier}
                          title="Set tier"
                          size="supporting"
                          format="tier"
                        />
                      </div>
                    </Link>
                  );
                })}
              </div>
            </>
          ) : (
            <p className="mt-4 rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--surface-page)]/45 px-4 py-5 text-sm text-[var(--text-secondary)]">
              Ranking snapshots are still loading. Open any set in RIP Statistics once data is available.
            </p>
          )}
        </section>

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
