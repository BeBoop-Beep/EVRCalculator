import { publicRipDisplayScore } from "../../constants/exploreRankingConfig.mjs";
import { readPublicSetRip } from "./setRipPublicPresentation.mjs";

export function readSetRipLandscape(targets) {
  return (Array.isArray(targets) ? targets : []).map((target) => {
    const metric = readPublicSetRip(target);
    return { name: target?.name || "Unknown Set", rank: metric.rank, score: publicRipDisplayScore(metric.publicScore), publicScore: metric.publicScore, tier: metric.tier, logo: target?.logo_image_url || target?.symbol_image_url || null };
  }).filter((point) => point.rank !== null && point.score !== null).sort((left, right) => left.rank - right.rank);
}
