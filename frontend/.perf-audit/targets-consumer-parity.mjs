// §16 golden consumer parity: run every known Rankings-targets consumer surface
// against the FULL payload and the SLIM (projected) payload, and compare the
// resulting MODELS rather than raw JSON.
import fs from "node:fs";
import { resolveCanonicalRipV7, readCanonicalBlock, hasCanonicalOverallRipV7 } from "../components/explore/canonicalRipV7.mjs";

const SP = "C:/Users/Owner/AppData/Local/Temp/claude/d--EVRCalculator/85861793-771a-47aa-95cc-4d8d924b1fff/scratchpad";
const full = JSON.parse(fs.readFileSync(`${SP}/payload_full.json`, "utf8"));
const slim = JSON.parse(fs.readFileSync(`${SP}/payload_slim.json`, "utf8"));

const num = (v) => (v === null || v === undefined ? null : v);

// The model each consumer actually renders/derives from one target.
function targetModel(t) {
  const bundle = resolveCanonicalRipV7(t);
  const overall = readCanonicalBlock(bundle?.overall);
  const financial = readCanonicalBlock(bundle?.financialRip);
  const appeal = readCanonicalBlock(bundle?.collectorAppeal);
  return {
    // --- identity / routing: set route, sitemap, metadata, set picker ---
    id: t.id, set_id: t.set_id, target_id: t.target_id,
    slug: t.slug, canonical_key: t.canonical_key, name: t.name,
    era: t.era, era_id: t.era_id, pokemon_api_set_id: t.pokemon_api_set_id,
    logo: t.logo_image_url, symbol: t.symbol_image_url, hero: t.hero_image_url,
    // --- canonical scoring resolution (source matters, not just value) ---
    canonicalShape: bundle?.shape ?? null,
    hasCanonicalV7: hasCanonicalOverallRipV7(t),
    overall: { score: num(overall?.score), abs: num(overall?.absoluteScore), rel: num(overall?.relativeScore), rank: num(overall?.rank), tier: overall?.tier ?? null, cohort: num(overall?.rankedSetCount) },
    financial: { score: num(financial?.score), abs: num(financial?.absoluteScore), rel: num(financial?.relativeScore), rank: num(financial?.rank), tier: financial?.tier ?? null, cohort: num(financial?.rankedSetCount) },
    appeal: { score: num(appeal?.score), abs: num(appeal?.absoluteScore), rel: num(appeal?.relativeScore), rank: num(appeal?.rank), tier: appeal?.tier ?? null, cohort: num(appeal?.rankedSetCount) },
    // --- Rankings/Explore table columns ---
    packCost: num(t.pack_cost), meanValue: num(t.mean_value), medianValue: num(t.median_value),
    roi: num(t.roi_percent), probProfit: num(t.prob_profit), packScore: num(t.pack_score),
    packRank: num(t.pack_rank), packTier: t.pack_tier ?? null,
    profitRank: num(t.profit_rank), profitTier: t.profit_tier ?? null,
    safetyRank: num(t.safety_rank), safetyTier: t.safety_tier ?? null,
    // --- Set Value (publication contract surface) ---
    setValue: num(t.currentChecklistSetValue), setValueAsOf: t.checklistSetValueAsOf ?? null,
    setValuePrev7d: num(t.previousChecklistSetValue7d), setValueCmp7d: t.setValueComparisonStatus7d ?? null,
    // --- 1D rank movement (history-derived) ---
    prevOverallRank1d: num(t.previousOverallRipRank1d), overallMove1d: num(t.overallRipRankMovement1d),
    prevFinancialRank1d: num(t.previousFinancialRipRank1d), financialMove1d: num(t.financialRipRankMovement1d),
    overallCmp1d: t.overallRipRankComparisonStatus1d ?? null,
    // --- other rendered families ---
    openingExperience: JSON.stringify(t.openingExperience ?? null),
    universalSetDesirability: JSON.stringify(t.universalSetDesirability ?? null),
    financialRipV3: JSON.stringify(t.financialRipV3 ?? null),
    overallRipV7: JSON.stringify(t.overallRipV7 ?? null),
    collectorAppealScore: num(t.collector_appeal_score), collectorAppealRank: num(t.collector_appeal_rank),
  };
}

// Consumer-level derivations.
const orderOf = (p) => p.targets.map((t) => t.canonical_key ?? t.set_id);
const sitemapUrls = (p) => p.targets.map((t) => `/TCGs/Pokemon/Sets/${t.slug ?? t.canonical_key}`);
const landingHero = (p) => { const t = p.targets[0]; return t ? JSON.stringify(targetModel(t)) : null; };
const defaultTarget = (p) => JSON.stringify(p.default_target ?? null);
const metaModel = (p) => JSON.stringify(p.meta ?? null);

const diffs = [];
function cmp(label, a, b) {
  const x = JSON.stringify(a), y = JSON.stringify(b);
  if (x !== y) diffs.push({ label, full: x?.slice(0, 300), slim: y?.slice(0, 300) });
}

cmp("target count", full.targets.length, slim.targets.length);
cmp("ordering", orderOf(full), orderOf(slim));
cmp("sitemap URLs", sitemapUrls(full), sitemapUrls(slim));
cmp("landing hero model", landingHero(full), landingHero(slim));
cmp("default_target", defaultTarget(full), defaultTarget(slim));
cmp("meta", metaModel(full), metaModel(slim));

let compared = 0;
for (let i = 0; i < full.targets.length; i += 1) {
  cmp(`target[${i}] ${full.targets[i].canonical_key} model`, targetModel(full.targets[i]), targetModel(slim.targets[i]));
  compared += 1;
}

const fieldsPerTarget = Object.keys(targetModel(full.targets[0])).length;
console.log(`Consumers compared : Rankings/Explore table, Market, landing hero, set route+picker, sitemap, metadata, canonical RIP resolver`);
console.log(`Targets compared   : ${compared}`);
console.log(`Fields per target  : ${fieldsPerTarget}  (=> ${compared * fieldsPerTarget} field comparisons)`);
console.log(`Scenario checks    : target count, ordering, sitemap URLs, landing hero, default_target, meta`);
console.log(`\nDIFFERENCES: ${diffs.length}`);
for (const d of diffs.slice(0, 10)) console.log(`  ${d.label}\n    full=${d.full}\n    slim=${d.slim}`);

// Canonical source must remain publicRipContractV7 for every target, not a fallback.
const sources = new Set(slim.targets.map((t) => resolveCanonicalRipV7(t)?.shape));
console.log(`\nCanonical resolution source on SLIM payload: ${[...sources].join(", ")}`);
process.exit(diffs.length === 0 ? 0 : 1);
