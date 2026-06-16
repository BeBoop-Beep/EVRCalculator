import { toSetSlug as toCanonicalSetSlug } from "@/utils/slugify";

const TCG_SETS_BASE_PATH = "/TCGs/Pokemon/Sets";

function normaliseString(value) {
  return String(value || "").trim();
}

export function toSetSlug(name, fallback = "") {
  return toCanonicalSetSlug(normaliseString(name), normaliseString(fallback));
}

export function buildTcgSetHrefFromTarget(target) {
  const targetType = normaliseString(target?.target_type).toLowerCase();
  if (targetType !== "set") {
    return "/Explore/rip-statistics";
  }

  const slug = toSetSlug(target?.name, target?.target_id);
  if (!slug) {
    return "/Explore/rip-statistics";
  }

  return `${TCG_SETS_BASE_PATH}/${encodeURIComponent(slug)}`;
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

export function buildTargetHrefById(targets) {
  const hrefById = {};
  (Array.isArray(targets) ? targets : []).forEach((target) => {
    const targetId = normaliseString(target?.target_id);
    if (!targetId) {
      return;
    }
    hrefById[targetId] = buildTcgSetHrefFromTarget(target);
  });
  return hrefById;
}
