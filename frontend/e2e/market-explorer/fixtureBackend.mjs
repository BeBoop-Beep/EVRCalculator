// ---------------------------------------------------------------------------
// FIXTURE MODE ONLY. A stand-in for the FastAPI backend, used to drive the real
// Next frontend in a real browser without credentials or a serving V2 generation.
//
//   FIXTURE_BACKEND_MODE=v1 -> V1 fallback mode (what production serves today)
//   FIXTURE_BACKEND_MODE=v2 -> V2 mode (NOT live; proves the UI before promotion)
//
// Point a Next server at one of them:
//   BACKEND_API_BASE_URL=http://127.0.0.1:8201 npx next dev -p 3202
//
// Plans are FIXTURE identities, never real auth: the `token` cookie values
// `fixture-plus` / `fixture-premium` resolve to a fake user via /auth/me; anything
// else is anonymous. The compare/constituent entitlement rules below mirror
// backend/api/main.py (two unique keys across marketKeys + contextMarketKeys is a
// comparison and needs Index+; constituents need Index+).
// ---------------------------------------------------------------------------
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const overview = JSON.parse(fs.readFileSync(path.join(here, "fixtures", "setValueMarket.slim.json"), "utf8"));

const AS_OF = "2026-09-22";
let ART_ORIGIN = "http://127.0.0.1:8201";
const GEN = { v1: "fixture-gen-v1", v2: "fixture-gen-v2" };
const ERA = { base: "era-base", neo: "era-neo", hgss: "era-hgss" };
const SET = { fossil: "set-fossil", jungle: "set-jungle", bs2: "set-bs2", hgss: "set-hgss", neoGenesis: "set-neo-genesis", neoDiscovery: "set-neo-discovery", neoRevelation: "set-neo-revelation", neoDestiny: "set-neo-destiny" };
// FIXTURE-ONLY commercial limits, mirroring backend MARKET_EXPLORER_ACTIVE_MARKET_LIMIT.
const PLAN_LIMIT = { plus: 3, premium: 10 };

const money = (n) => Math.round(n * 100) / 100;
function base(over) {
  return {
    market_key: "", market_type: "set", label: "", asset: "cards", set_id: null, era_id: null, parent_era_id: null,
    prepared_series_key: "", comparison_as_of: AS_OF, source_as_of: AS_OF, current_value: 1800, comparison_value: 1800,
    comparison_index_value: 101.5, history_available: true, history_start_date: "2026-05-01", history_end_date: AS_OF, history_point_count: 60,
    return_7d_pct: 1.2, return_30d_pct: -2.1, return_90d_pct: 4.4, return_1y_pct: null, current_drawdown_pct: -3, max_drawdown_pct: -12,
    relative_7d_vs_era_pct: 0.2, relative_30d_vs_era_pct: -0.3, relative_90d_vs_era_pct: null, relative_1y_vs_era_pct: null,
    screen_group: null, screen_eligible: false, source_kind: "public_set_snapshot", source_status: "current", metadata: {},
    generation_id: GEN.v1, generated_at: "2026-09-24T06:00:00+00:00", ...over,
  };
}
const v1Set = (id, label, era) => base({ market_key: `set:${id}`, label, set_id: id, parent_era_id: era, prepared_series_key: `set-cards-market-index:${id}` });
const v1Era = (id, label) => base({ market_key: `era:${id}`, market_type: "era", label, era_id: id, prepared_series_key: `era:${id}` });

function directoryV1() {
  return [
    v1Era(ERA.base, "Base/WOTC"), v1Era(ERA.neo, "Neo"), v1Era(ERA.hgss, "HeartGold & SoulSilver"),
    v1Set(SET.fossil, "Fossil", ERA.base), v1Set(SET.jungle, "Jungle", ERA.base), v1Set(SET.bs2, "Base Set 2", ERA.base),
    v1Set(SET.hgss, "HeartGold & SoulSilver", ERA.hgss), v1Set(SET.neoGenesis, "Neo Genesis", ERA.neo),
    ...["obtainable:Obtainable", "intermediate:Intermediate", "premium:Premium", "new-releases:New Releases", "established:Established", "global-top10:Global Top 10"]
      .map((entry) => { const [k, l] = entry.split(":"); return base({ market_key: `curated:${k}`, market_type: "curated", label: l, source_kind: "maintained_query_cache" }); }),
    ...["rareHolo:Rare Holo", "rareUltra:Rare Ultra", "rareSecret:Rare Secret", "ultraRare:Ultra Rare"]
      .map((entry) => { const [k, l] = entry.split(":"); return base({ market_key: `rarity:${k}`, market_type: "prepared_rarity", label: l, source_kind: "maintained_query_cache" }); }),
    ...["boosterBox:Booster Boxes", "packs:Packs"].map((entry) => { const [k, l] = entry.split(":"); return base({ market_key: `sealed-format:${k}`, market_type: "prepared_format", label: l, asset: "sealed", source_kind: "prepared_sealed_snapshots" }); }),
  ];
}

const v2 = (over) => base({ surface_version: "v2", generation_id: GEN.v2, composition_kind: "index_and_composition", availability: "available", unavailable_reason: null, source_kind: "v2_surface", ...over });
const v2Scoped = (kind, asset, id, label, parent) => {
  const prefix = asset === "sealed" ? `sealed-${kind}` : kind;
  return v2({ market_key: `${prefix}:${id}`, scope_kind: kind, market_type: kind, label, asset, set_id: kind === "set" ? id : null, era_id: kind === "era" ? id : null, parent_era_id: kind === "set" ? parent : null, base_label: label });
};

function directoryV2() {
  const rows = [];
  for (const asset of ["cards", "sealed"]) {
    rows.push(v2Scoped("era", asset, ERA.base, "Base/WOTC"), v2Scoped("era", asset, ERA.neo, "Neo"), v2Scoped("era", asset, ERA.hgss, "HeartGold & SoulSilver"));
    rows.push(v2Scoped("set", asset, SET.fossil, "Fossil", ERA.base), v2Scoped("set", asset, SET.jungle, "Jungle", ERA.base), v2Scoped("set", asset, SET.bs2, "Base Set 2", ERA.base), v2Scoped("set", asset, SET.hgss, "HeartGold & SoulSilver", ERA.hgss));
    rows.push(...[["neoGenesis", "Neo Genesis"], ["neoDiscovery", "Neo Discovery"], ["neoRevelation", "Neo Revelation"], ["neoDestiny", "Neo Destiny"]].map(([id, label]) => v2Scoped("set", asset, SET[id], label, ERA.neo)));
  }
  rows.push(
    v2({ market_key: "raw", scope_kind: "parent", market_type: "parent", label: "Raw Card Market", asset: "cards", composition_kind: "index_and_composition", availability: "available" }),
    v2({ market_key: "sealedMarket", scope_kind: "parent", market_type: "parent", label: "Total Sealed", asset: "sealed", composition_kind: "index_and_composition", availability: "available" }),
    ...["rarity:rareUltra:Rare Ultra", "rarity:rareSecret:Rare Secret", "rarity:ultraRare:Ultra Rare", "rarity:specialIllustrationRare:Special Illustration Rare"]
      .map((entry) => { const [a, k, l] = entry.split(":"); return v2({ market_key: `${a}:${k}`, scope_kind: "rarity", market_type: "prepared_rarity", label: l, asset: "cards", composition_kind: "index_and_composition" }); }),
    ...["case:Cases", "display:Displays", "booster_box:Booster Boxes", "elite_trainer_box:Elite Trainer Boxes", "three_pack_blister:Three-Pack Blisters", "collection_product:Collection Products"]
      .map((entry) => { const [k, l] = entry.split(":"); return v2({ market_key: `sealed-type:${k}`, scope_kind: "type", market_type: "prepared_format", label: l, asset: "sealed", composition_kind: "index_and_composition" }); }),
    ...["obtainable:Obtainable", "premium:Premium"].map((entry) => { const [k, l] = entry.split(":"); return v2({ market_key: `curated:${k}`, scope_kind: "quick", market_type: "curated", label: l, asset: "cards" }); }),
  );
  return rows;
}

// Sets that publish no roster (composition index-only) prove the "not inspectable" chip.
const IMAGE_MARKETS = new Set([`set:${SET.fossil}`, `set:${SET.hgss}`, `set:${SET.bs2}`, "rarity:rareUltra", "rarity:rareSecret", "rarity:rareHoloGx", "raw", `sealed-set:${SET.fossil}`]);
// Published image URLs that 404: the row must fall back to the neutral placeholder.
const BROKEN_IMAGE_MARKETS = new Set([`set:${SET.neoGenesis}`]);
const NO_IMAGE_MARKETS = new Set([`set:${SET.jungle}`]);

function directory(mode) { return mode === "v2" ? directoryV2() : directoryV1(); }
// PREPARED_CANDIDATE identities: absent from the directory but loadable by key through the
// same prepared loader (asset-options publishes preparedMarketKey). Rare Holo GX is one.
const candidateRows = (mode) => (mode === "v2" ? [v2({ market_key: "rarity:rareHoloGx", scope_kind: "rarity", market_type: "prepared_rarity", label: "Rare Holo GX", asset: "cards" })] : []);
const resolveRows = (mode, keys) => [...directory(mode), ...candidateRows(mode)].filter((row) => keys.includes(row.market_key));

function seeded(key) { let h = 0; for (const c of key) h = (h * 31 + c.charCodeAt(0)) >>> 0; return h; }
function historyFor(key, generation) {
  const seed = seeded(key);
  const out = [];
  const start = Date.UTC(2026, 6, 25); // 60 daily points ending on AS_OF (2026-09-22)
  for (let i = 0; i < 60; i += 1) {
    const day = new Date(start + i * 86400000).toISOString().slice(0, 10);
    out.push({ market_key: key, market_date: day, index_value: money(100 + Math.sin((i + seed % 7) / 5) * 8 + (seed % 5) * i * 0.05), tracked_value: null, chain_segment_id: 0, generation_id: generation });
  }
  return out;
}

const PLAN = { "fixture-plus": "plus", "fixture-premium": "premium" };
function planOf(req) {
  const cookie = req.headers.cookie || "";
  const token = /(?:^|;\s*)token=([^;]+)/.exec(cookie)?.[1] || String(req.headers.authorization || "").replace(/^Bearer\s+/i, "");
  return { token: token || null, plan: PLAN[token] || null };
}

function constituentRows(market, after, limit) {
  const total = 130;
  const withImages = IMAGE_MARKETS.has(market);
  const sealed = market.startsWith("sealed");
  const rows = [];
  for (let rank = after + 1; rank <= Math.min(total, after + limit); rank += 1) {
    const row = sealed
      ? { rank, sealedProductId: `${market}-p${rank}`, productName: `${market} Product ${rank}`, setName: "Fixture Set", productFamilyLabel: "Booster Box", marketPrice: money(900 - rank * 3) }
      : { rank, canonicalCardId: `${market}-c${rank}`, cardVariantId: `${market}-v${rank}`, instrumentId: `${market}-v${rank}`, cardName: `${market} Card ${rank}`, setName: "Fixture Set", setId: SET.fossil, rarity: "Rare Holo", marketPrice: money(700 - rank * 2) };
    if (BROKEN_IMAGE_MARKETS.has(market)) Object.assign(row, { imageSmallUrl: `${ART_ORIGIN}/fixture-art-broken/${rank}-s.png`, imageLargeUrl: `${ART_ORIGIN}/fixture-art-broken/${rank}-l.png` });
    if (withImages) Object.assign(row, { imageSmallUrl: `${ART_ORIGIN}/fixture-art/${encodeURIComponent(market)}-${rank}-s.svg`, imageLargeUrl: `${ART_ORIGIN}/fixture-art/${encodeURIComponent(market)}-${rank}-l.svg` });
    rows.push(row);
  }
  return { rows, total };
}

export function startFixtureBackend({ port = 8201, mode = "v2" } = {}) {
  ART_ORIGIN = `http://127.0.0.1:${port}`;
  const log = [];
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, `http://127.0.0.1:${port}`);
    const send = (status, body, headers = {}) => { res.writeHead(status, { "content-type": "application/json", ...headers }); res.end(JSON.stringify(body)); };
    if (url.pathname === "/__fixture/requests") return send(200, log);
    if (url.pathname.startsWith("/fixture-art/")) {
      res.writeHead(200, { "content-type": "image/svg+xml", "cache-control": "no-store" });
      return res.end(`<svg xmlns="http://www.w3.org/2000/svg" width="245" height="342" viewBox="0 0 245 342"><rect width="245" height="342" fill="#3b2a6b"/><text x="122" y="176" fill="#fff" font-size="18" text-anchor="middle">${decodeURIComponent(url.pathname.split("/").pop()).replace(/[<&]/g, "")}</text></svg>`);
    }
    if (url.pathname.startsWith("/fixture-art-broken/")) { res.writeHead(404); return res.end(); }
    if (url.pathname === "/__fixture/reset") { log.length = 0; return send(200, { ok: true }); }
    const route = url.pathname;
    const chunks = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => {
      let body = null;
      try { body = chunks.length ? JSON.parse(Buffer.concat(chunks).toString("utf8")) : null; } catch { body = null; }
      const { token, plan } = planOf(req);
      const entry = { mode, method: req.method, route, query: Object.fromEntries(url.searchParams), body, plan };
      const reply = (status, payload) => { entry.status = status; log.push(entry); send(status, payload, { "Cache-Control": "no-store" }); };

      if (route === "/auth/me") return token && plan ? reply(200, { user: { id: "fixture-user", email: `${plan}@fixture.test`, index_plan: plan } }) : reply(401, { message: "Not authenticated" });
      if (route === "/explore/set-value-market") return reply(200, overview);
      if (route === "/market/explorer/prepared-directory") return reply(200, { markets: directory(mode) });
      if (route === "/market/explorer/prepared-comparison") {
        const keys = new Set([...(body?.marketKeys || []), ...(body?.contextMarketKeys || [])]);
        if (keys.size > 1) {
          if (!token) return reply(401, { message: "Sign in to compare markets.", code: "AUTH" });
          if (!plan) return reply(403, { message: "Comparing markets is included with Index+.", requiredPlan: "plus" });
          if (keys.size > PLAN_LIMIT[plan]) return reply(403, { detail: { message: `Your plan supports up to ${PLAN_LIMIT[plan]} active comparison markets.`, code: "ACTIVE_MARKET_LIMIT", limit: PLAN_LIMIT[plan] } });
        }
        const rows = resolveRows(mode, body?.marketKeys || []);
        const generation = mode === "v2" ? GEN.v2 : GEN.v1;
        return reply(200, { markets: rows.map((row) => ({ ...row, window_movements: {}, constituent_count: 130 })), history: rows.flatMap((row) => historyFor(row.market_key, generation)), missingKeys: [] });
      }
      if (route === "/market/explorer/prepared-constituents") {
        if (!token) return reply(401, { message: "Sign in required", code: "AUTH" });
        if (!plan) return reply(403, { message: "Constituents are included with Index+.", requiredPlan: "plus" });
        const key = url.searchParams.get("marketKey");
        const after = Number(url.searchParams.get("afterRank") || 0);
        const limit = Math.min(100, Number(url.searchParams.get("limit") || 100));
        if (key === "fixture-fail") return reply(503, { code: "PREPARED_CONSTITUENTS_FAILED" });
        const { rows, total } = constituentRows(key, after, limit);
        const last = rows[rows.length - 1]?.rank || after;
        return reply(200, { rows, nextCursor: last < total ? last : null, totalCount: total, priceAsOf: AS_OF, generationId: url.searchParams.get("generationId"), availability: "available", movementAvailable: false, sourceKind: "fixture" });
      }
      if (route === "/market/explorer/asset-options") {
        if (mode !== "v2") return reply(503, { code: "ASSET_OPTIONS_FAILED" });
        const asset = url.searchParams.get("asset");
        if (asset === "sealed") {
          const type = (key, label, extra = {}) => ({ key, label, eligibilityState: "PREPARED", preparedMarketAvailable: true, preparedMarketKey: `sealed-type:${key}`, bulkContainer: false, parentMembership: true, ...extra });
          return reply(200, { types: [type("booster_box", "Booster Boxes"), type("elite_trainer_box", "Elite Trainer Boxes"), type("three_pack_blister", "Three-Pack Blisters"), type("collection_product", "Collection Products"), type("case", "Cases", { bulkContainer: true, parentMembership: false }), type("display", "Displays", { bulkContainer: true, parentMembership: false }), type("half_booster_box", "Half Booster Boxes", { eligibilityState: "UNAVAILABLE", preparedMarketAvailable: false, preparedMarketKey: null, reason: "No current priced inventory is available for this option." })], quickMarkets: [] });
        }
        const prepared = (key, label) => ({ key, label, eligibilityState: "PREPARED", preparedMarketAvailable: true, preparedMarketKey: `rarity:${key}` });
        const other = (key, label, eligibilityState, reason) => ({ key, label, eligibilityState, preparedMarketAvailable: false, preparedMarketKey: null, reason });
        return reply(200, { rarities: [
          { key: "rareHoloGX", label: "Rare Holo GX", eligibilityState: "PREPARED_CANDIDATE", preparedMarketAvailable: false, preparedMarketKey: "rarity:rareHoloGx" }, other("rareHoloEX", "Rare Holo EX", "INSUFFICIENT_COHORT"),
          other("rareHoloV", "Rare Holo V", "CUSTOM_BUILD_AVAILABLE"), other("rareHoloVMAX", "Rare Holo VMAX", "INSUFFICIENT_HISTORY"),
          other("rareHoloVSTAR", "Rare Holo VSTAR", "UNAVAILABLE"), prepared("rareUltra", "Rare Ultra"), prepared("rareSecret", "Rare Secret"),
          prepared("ultraRare", "Ultra Rare"), prepared("specialIllustrationRare", "Special Illustration Rare"),
        ] });
      }
      if (route === "/market/explorer/catalog/search") {
        const q = String(url.searchParams.get("q") || "").toLowerCase();
        const asset = url.searchParams.get("asset");
        if (q.startsWith("slow")) return setTimeout(() => reply(200, { results: [{ result_kind: "prepared_market", market_key: "stale:marker", label: "STALE RESULT", subtitle: asset, asset, availability: "AVAILABLE", metadata: {} }] }), 1500);
        const instruments = asset === "sealed"
          ? [{ result_kind: "instrument", instrument_id: "sealed-prod-1", label: "Fixture Booster Box", subtitle: "Fossil · Booster Box", asset: "sealed", availability: "AVAILABLE", metadata: { sealedProductId: "sealed-prod-1", setName: "Fossil", productFamily: "Booster Box" } }]
          : asset === "cards"
            ? [{ result_kind: "instrument", instrument_id: "var-gengar", label: "Fixture Gengar", subtitle: "Fossil · 5 Rare Holo", asset: "cards", set_id: SET.fossil, availability: "AVAILABLE", metadata: { cardVariantId: "var-gengar", cardNumber: "5", rarity: "Rare Holo" } }]
            : [];
        const all = [...directory(mode), ...candidateRows(mode)].filter((row) => row.asset === asset && row.label.toLowerCase().includes(q));
        const matchedInstruments = instruments.filter((item) => item.label.toLowerCase().includes(q) || q.includes("gengar") && item.label.includes("Gengar") || q.includes("product") && item.asset === "sealed");
        if (asset === "graded") return reply(200, { results: [{ result_kind: "instrument", label: "Graded cards", subtitle: "Graded markets are not available yet.", asset: "graded", availability: "INSUFFICIENT_AUTHORITY", metadata: {} }] });
        const asResult = (row) => ({ result_kind: row.market_type === "era" ? "era" : row.market_type === "set" ? "set" : "prepared_market", market_key: row.market_key, label: row.label, subtitle: row.asset, asset: row.asset, availability: "AVAILABLE", metadata: {} });
        return reply(200, { results: [...all.map(asResult), ...matchedInstruments].slice(0, 8) });
      }
      if (route === "/market/explorer/query/options") return reply(404, { message: "fixture: not modelled" });
      return reply(404, { message: `fixture: ${route} not modelled` });
    });
  });
  return new Promise((resolve) => server.listen(port, "127.0.0.1", () => resolve({ server, log, port, close: () => new Promise((r) => server.close(r)) })));
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const port = Number(process.env.FIXTURE_BACKEND_PORT || 8201);
  const mode = process.env.FIXTURE_BACKEND_MODE === "v1" ? "v1" : "v2";
  startFixtureBackend({ port, mode }).then(() => console.log(`Market Explorer FIXTURE backend (${mode}) on :${port}`));
}
