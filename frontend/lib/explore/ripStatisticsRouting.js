import { toSetSlug as toCanonicalSetSlug } from "@/utils/slugify";

const TCG_SETS_BASE_PATH = "/TCGs/Pokemon/Sets";
const SET_DETAIL_TABS = new Set(["overview", "cards", "pull-rates", "insights"]);
const SET_DETAIL_TAB_ALIASES = {
  market: "overview",
};

function normaliseString(value) {
  return String(value || "").trim();
}

function appendSetDetailParams(href, options = {}) {
  const rawTab = normaliseString(options.tab).toLowerCase();
  const tab = SET_DETAIL_TAB_ALIASES[rawTab] || rawTab;
  const section = normaliseString(options.section);
  const params = new URLSearchParams();

  if (SET_DETAIL_TABS.has(tab)) {
    params.set("tab", tab);
  }

  if (section) {
    params.set("section", section);
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
