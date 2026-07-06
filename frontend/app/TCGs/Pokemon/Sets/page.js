import Link from "next/link";
import SecondaryNav from "@/components/SecondaryNav";
import { toSetSlug } from "@/utils/slugify";
import { getPokemonSets } from "@/lib/pokemon/pokemonSetsServer";
import { isHiddenFromPublicPokemonSetsCatalog } from "@/lib/pokemon/pokemonSetPublicCoverage";

function toTimestamp(value) {
  if (!value) {
    return null;
  }
  const parsed = Date.parse(String(value));
  return Number.isFinite(parsed) ? parsed : null;
}

function toDisplayDate(value) {
  const text = String(value || "").trim();
  if (!text) {
    return null;
  }
  const directDateMatch = /^(\d{4})-(\d{2})-(\d{2})$/.exec(text);
  if (directDateMatch) {
    return `${directDateMatch[1]}/${directDateMatch[2]}/${directDateMatch[3]}`;
  }
  const timestamp = toTimestamp(text);
  if (timestamp === null) {
    return null;
  }
  const parsedDate = new Date(timestamp);
  const year = parsedDate.getUTCFullYear();
  const month = String(parsedDate.getUTCMonth() + 1).padStart(2, "0");
  const day = String(parsedDate.getUTCDate()).padStart(2, "0");
  return `${year}/${month}/${day}`;
}

function getCardCount(setSummary) {
  const parsed = Number(setSummary?.cardCount ?? null);
  if (!Number.isFinite(parsed) || parsed < 0) {
    return null;
  }
  return Math.round(parsed);
}

function getSetImageUrl(setSummary) {
  return setSummary?.logoUrl || setSummary?.symbolUrl || setSummary?.imageUrl || null;
}

function getSetInitials(name) {
  const words = String(name || "")
    .split(/\s+/)
    .map((word) => word.trim())
    .filter(Boolean)
    .slice(0, 2);

  if (words.length === 0) {
    return "PK";
  }

  return words.map((word) => word[0]).join("").toUpperCase();
}

function groupSetsByEra(sets) {
  const eraMap = new Map();

  (Array.isArray(sets) ? sets : []).forEach((setSummary, index) => {
    const eraName = String(setSummary?.era || setSummary?.series || "Other").trim() || "Other";
    const currentGroup = eraMap.get(eraName) || {
      eraName,
      sets: [],
      earliestTimestamp: null,
      latestTimestamp: null,
      firstSeenIndex: index,
    };

    const releaseTimestamp = toTimestamp(setSummary?.releaseDate ?? null);

    if (releaseTimestamp !== null) {
      currentGroup.latestTimestamp =
        currentGroup.latestTimestamp === null
          ? releaseTimestamp
          : Math.max(currentGroup.latestTimestamp, releaseTimestamp);
      currentGroup.earliestTimestamp =
        currentGroup.earliestTimestamp === null
          ? releaseTimestamp
          : Math.min(currentGroup.earliestTimestamp, releaseTimestamp);
    }

    currentGroup.sets.push(setSummary);
    eraMap.set(eraName, currentGroup);
  });

  return Array.from(eraMap.values())
    .map((group) => ({
      ...group,
      sets: group.sets
        .map((setSummary, index) => ({
          ...setSummary,
          __releaseTimestamp: toTimestamp(setSummary?.releaseDate ?? null),
          __fallbackIndex: index,
        }))
        .sort((a, b) => {
          if (a.__releaseTimestamp !== null && b.__releaseTimestamp !== null) {
            return b.__releaseTimestamp - a.__releaseTimestamp;
          }
          if (a.__releaseTimestamp !== null) {
            return -1;
          }
          if (b.__releaseTimestamp !== null) {
            return 1;
          }
          return a.__fallbackIndex - b.__fallbackIndex;
        }),
    }))
    .sort((a, b) => {
      if (a.latestTimestamp !== null && b.latestTimestamp !== null) {
        return b.latestTimestamp - a.latestTimestamp;
      }
      if (a.latestTimestamp !== null) {
        return -1;
      }
      if (b.latestTimestamp !== null) {
        return 1;
      }
      return a.firstSeenIndex - b.firstSeenIndex;
    });
}

function formatYearRange(earliestTimestamp, latestTimestamp) {
  if (earliestTimestamp === null || latestTimestamp === null) {
    return null;
  }

  const earliestYear = new Date(earliestTimestamp).getUTCFullYear();
  const latestYear = new Date(latestTimestamp).getUTCFullYear();

  if (!Number.isFinite(earliestYear) || !Number.isFinite(latestYear)) {
    return null;
  }

  if (earliestYear === latestYear) {
    return String(latestYear);
  }

  return `${earliestYear} - ${latestYear}`;
}

export default async function SetsPage() {
  let sets = [];
  let loadError = null;

  try {
    const payload = await getPokemonSets();
    const summaries = Array.isArray(payload?.sets) ? payload.sets : [];
    // Sword & Shield's simulator-era data is not yet validated for public
    // analytics (see pokemonSetPublicCoverage.js) — hidden from the catalog
    // entirely for now rather than shown with no way to explain why its
    // analytics are unavailable (no status-badge UI exists yet). This is
    // narrower than the Explore rankings filter: it must not also hide
    // unrelated non-SWSH products (POP Series, promo-only collections) that
    // were already catalog-visible before this change.
    sets = summaries
      .filter((setSummary) => setSummary?.id && setSummary?.name)
      .filter((setSummary) => !isHiddenFromPublicPokemonSetsCatalog(setSummary));
  } catch (error) {
    loadError = error?.message || "Failed to load sets";
  }

  const groupedEras = groupSetsByEra(sets);

  return (
    <div className="min-h-screen bg-[var(--surface-page)]">
      <SecondaryNav basePath="/TCGs/Pokemon" />
      <main className="w-full px-2 md:px-6 lg:px-10 py-8">
        <div className="max-w-6xl mx-auto">
          <div className="dashboard-container">
            <h1 className="text-3xl md:text-4xl font-bold text-[var(--text-primary)] mb-3">
              Pokémon TCG Sets
            </h1>
            <p className="text-base md:text-lg text-[var(--text-secondary)] mb-8">
              Browse Pokémon sets by era, newest to oldest.
            </p>

            {loadError ? (
              <div className="rounded-xl border border-[rgba(239,68,68,0.35)] bg-[rgba(239,68,68,0.08)] p-6 text-center text-[var(--text-primary)]">
                Unable to load Pokémon sets.
              </div>
            ) : null}

            {!loadError && groupedEras.length === 0 ? (
              <div className="bg-[var(--surface-panel)] rounded-xl border border-[var(--border-subtle)] p-8 text-center text-[var(--text-secondary)]">
                No Pokémon sets available yet.
              </div>
            ) : !loadError ? (
              <div className="space-y-8">
                {groupedEras.map((eraGroup) => {
                  const yearRange = formatYearRange(eraGroup.earliestTimestamp, eraGroup.latestTimestamp);
                  return (
                    <section
                      key={eraGroup.eraName}
                      className="rounded-2xl border border-[var(--border-subtle)] bg-[linear-gradient(180deg,rgba(16,27,45,0.95)_0%,rgba(9,16,27,0.95)_100%)] p-4 md:p-5"
                    >
                      <header className="mb-4">
                        <div className="mb-3 h-[2px] w-16 rounded-full bg-[var(--accent)]/80" aria-hidden="true" />
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <h2 className="text-xl md:text-2xl font-semibold text-[var(--text-primary)]">{eraGroup.eraName}</h2>
                          <div className="flex items-center gap-2">
                            <span className="inline-flex items-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)] px-3 py-1 text-xs font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
                              {eraGroup.sets.length} {eraGroup.sets.length === 1 ? "Set" : "Sets"}
                            </span>
                            {yearRange ? (
                              <span className="inline-flex items-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)] px-3 py-1 text-xs font-semibold text-[var(--text-secondary)]">
                                {yearRange}
                              </span>
                            ) : null}
                          </div>
                        </div>
                      </header>

                      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4 md:gap-5">
                        {eraGroup.sets.map((setSummary) => {
                          const setName = String(setSummary?.name || setSummary?.id || "Unknown Set");
                          const cardCount = getCardCount(setSummary);
                          const releaseDateText = toDisplayDate(setSummary?.releaseDate ?? null);
                          const setImageUrl = getSetImageUrl(setSummary);
                          const slug = toSetSlug(setName, setSummary?.slug || setSummary?.id);
                          const setHref = slug ? `/TCGs/Pokemon/Sets/${encodeURIComponent(slug)}?tab=cards` : "/TCGs/Pokemon/Sets";

                          return (
                            <Link
                              key={String(setSummary?.id || setName)}
                              href={setHref}
                              className="group relative overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[linear-gradient(180deg,rgba(19,29,52,0.94)_0%,rgba(16,27,45,0.95)_58%,rgba(9,16,27,0.96)_100%)] p-4 md:p-5 transition-colors duration-200 hover:border-[var(--accent)]/55"
                            >
                              {setImageUrl ? (
                                <img
                                  src={setImageUrl}
                                  alt=""
                                  aria-hidden="true"
                                  className="pointer-events-none absolute -right-[28%] -top-[24%] h-72 w-72 max-w-none opacity-[0.08] object-contain"
                                  loading="lazy"
                                  decoding="async"
                                />
                              ) : null}

                              <div className="relative z-10 space-y-4">
                                <div className="flex h-20 w-full items-center justify-center rounded-xl border border-[var(--border-subtle)] bg-[rgba(9,16,27,0.72)]">
                                  {setImageUrl ? (
                                    <img
                                      src={setImageUrl}
                                      alt={`${setName} logo`}
                                      className="h-[78%] w-[78%] object-contain"
                                      loading="lazy"
                                      decoding="async"
                                    />
                                  ) : (
                                    <span className="text-sm font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
                                      {getSetInitials(setName)}
                                    </span>
                                  )}
                                </div>

                                <div>
                                  <h3 className="text-base md:text-lg font-semibold text-[var(--text-primary)] leading-snug">
                                    {setName}
                                  </h3>

                                  <div className="mt-2 space-y-1 text-sm text-[var(--text-secondary)]">
                                    {releaseDateText ? <p>Released: {releaseDateText}</p> : null}
                                    {cardCount !== null ? <p>{cardCount} cards</p> : null}
                                  </div>
                                </div>
                              </div>
                            </Link>
                          );
                        })}
                      </div>
                    </section>
                  );
                })}
              </div>
            ) : null}
          </div>
        </div>
      </main>
    </div>
  );
}
