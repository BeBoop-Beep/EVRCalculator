import { toSetSlug as toCanonicalSetSlug } from "@/utils/slugify";

const TCG_SETS_BASE_PATH = "/TCGs/Pokemon/Sets";
const SET_DETAIL_DEFAULT_TAB = "overview";
const SET_DETAIL_TABS = new Set(["overview", "market", "cards", "pull-rates", "insights"]);
const SET_MARKET_MOVER_WINDOWS = new Set(["7D", "30D"]);
// `market` is a REAL canonical tab now (user-facing Market), not an alias for
// overview. Only user-facing renames stay aliased here.
const SET_DETAIL_TAB_ALIASES = {
  rip: "overview",
  analysis: "insights",
  analytics: "insights",
};

/**
 * Resolve a raw `?tab=` query value to one of the canonical set detail tabs,
 * applying the same aliasing (rip -> overview, analysis/analytics -> insights)
 * and default (overview) used client-side by RipStatisticsPageClient.
 */
export function resolveSetDetailTab(rawTab) {
  const normalized = normaliseString(rawTab).toLowerCase();
  const alias = SET_DETAIL_TAB_ALIASES[normalized] || normalized;
  return SET_DETAIL_TABS.has(alias) ? alias : SET_DETAIL_DEFAULT_TAB;
}

function normaliseString(value) {
  return String(value || "").trim();
}

function appendSetDetailParams(href, options = {}) {
  const rawTab = normaliseString(options.tab).toLowerCase();
  const tab = SET_DETAIL_TAB_ALIASES[rawTab] || rawTab;
  const section = normaliseString(options.section);
  const window = normaliseString(options.window).toUpperCase();
  const params = new URLSearchParams();

  if (SET_DETAIL_TABS.has(tab)) {
    params.set("tab", tab);
  }

  if (section) {
    params.set("section", section);
  }

  if (SET_MARKET_MOVER_WINDOWS.has(window)) {
    params.set("window", window);
  }

  const query = params.toString();
  return query ? `${href}?${query}` : href;
}

export function toSetSlug(name, fallback = "") {
  return toCanonicalSetSlug(normaliseString(name), normaliseString(fallback));
}

export function buildTcgSetHrefFromTarget(target, options = {}) {
  const targetType = normaliseString(target?.target_type).toLowerCase();
  if (targetType !== "set") {
    return "/Explore/rip-statistics";
  }

  const slug = toSetSlug(target?.name, target?.target_id);
  if (!slug) {
    return "/Explore/rip-statistics";
  }

  return appendSetDetailParams(`${TCG_SETS_BASE_PATH}/${encodeURIComponent(slug)}`, options);
}

export function findTargetBySetSlug(targets, setSlug) {
  const resolvedSlug = normaliseString(setSlug).toLowerCase();
  if (!resolvedSlug) {
    return null;
  }

  const collection = Array.isArray(targets) ? targets : [];

  const slugMatch = collection.find((target) => {
    if (normaliseString(target?.target_type).toLowerCase() !== "set") {
      return false;
    }
    const targetSlug = toSetSlug(target?.name, target?.target_id);
    return targetSlug === resolvedSlug;
  });

  if (slugMatch) {
    return slugMatch;
  }

  return (
    collection.find(
      (target) =>
        normaliseString(target?.target_type).toLowerCase() === "set" &&
        normaliseString(target?.target_id).toLowerCase() === resolvedSlug
    ) || null
  );
}

export function buildTargetHrefById(targets, options = {}) {
  const hrefById = {};
  (Array.isArray(targets) ? targets : []).forEach((target) => {
    const targetId = normaliseString(target?.target_id);
    if (!targetId) {
      return;
    }
    hrefById[targetId] = buildTcgSetHrefFromTarget(target, options);
  });
  return hrefById;
}
