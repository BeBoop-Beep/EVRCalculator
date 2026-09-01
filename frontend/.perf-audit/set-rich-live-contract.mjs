import { validateTopChasePayload } from "../lib/pokemon/topChasePayloadContract.mjs";

const BASE = process.env.LIVE_BACKEND_BASE || "http://127.0.0.1:8001";
const sets = [
  ["prismatic-evolutions", "7a3dd188-4375-41af-94de-c5247fe0b1a6"],
  ["ascended-heroes", "75cd439d-aaa2-41cb-86f3-2fefa5b26e29"],
];

async function get(path) {
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const response = await fetch(`${BASE}${path}`);
    if (response.ok) return response.json();
    if (response.status !== 503 || attempt === 1) throw new Error(`${path}: HTTP ${response.status}`);
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
}

for (const [slug, id] of sets) {
  const shell = await get(`/tcgs/pokemon/sets/${id}/shell`);
  const market = await get(`/tcgs/pokemon/sets/${id}/market/bootstrap?window=365d`);
  const topChase = await get(`/tcgs/pokemon/sets/${id}/market/top-chase?snapshot_contract=pricing-v4&window=365d&limit=10`);
  const cards = await get(`/tcgs/pokemon/sets/${id}/cards/page?snapshot_contract=pricing-v4&page=1&page_size=60&section=all-cards&sort=set-number&sort_direction=asc&movement_filter=all`);
  const pullRates = await get(`/tcgs/pokemon/sets/${id}/pull-rates`);
  const rip = await get(`/tcgs/pokemon/sets/${id}/rip/bootstrap`);
  const rawCards = topChase.cards || topChase.topChaseCards || [];
  const histories = topChase.topChaseCardHistories || topChase.priceHistories || {};
  const normalizedTopChase = {
    ...topChase,
    cards: rawCards.map((card) => ({ ...card, priceHistory: card.priceHistory || histories[card.cardVariantId] || histories[card.card_variant_id] || [] })),
  };
  const verdict = validateTopChasePayload(normalizedTopChase, { requestedSetId: id, expectedLimit: 10 });
  const points = normalizedTopChase.cards.map((card) => card.priceHistory.length);
  const currentDate = market.latestMarketDate || market.meta?.latestMarketDate;
  const marketHistory = market.setValueHistoriesByScope?.standard || market.setValueHistory || market.marketValueHistory || market.cardsMarket?.marketIndex?.history || [];
  const cardRows = cards.cards || cards.items || cards.results || [];
  if (!shell?.set?.id && !shell?.id) throw new Error(`${slug}: shell identity missing`);
  if (!currentDate || Number.isNaN(Date.parse(currentDate))) throw new Error(`${slug}: market date missing`);
  if (!marketHistory.length) throw new Error(`${slug}: Set Value history missing`);
  if (normalizedTopChase.cards.length !== 10 || Math.min(...points) < 2 || !verdict.complete || !verdict.renderable) throw new Error(`${slug}: Top Chase incomplete`);
  if (!cardRows.length) throw new Error(`${slug}: cards empty`);
  if (!pullRates || !rip) throw new Error(`${slug}: Pull Rates or RIP missing`);
  console.log(JSON.stringify({ slug, id, marketDate: currentDate, cards: cardRows.length, topChaseCards: normalizedTopChase.cards.length, minHistoryPoints: Math.min(...points), validatorStatus: verdict.status, complete: verdict.complete, renderable: verdict.renderable }));
}

console.log("Set live data contract PASS");
