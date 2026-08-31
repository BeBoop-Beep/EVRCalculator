import { validateTopChasePayload } from "../lib/pokemon/topChasePayloadContract.mjs";

const BASE = process.env.LIVE_BACKEND_BASE || "http://127.0.0.1:8001";
const sets = [
  ["prismatic-evolutions", "7a3dd188-4375-41af-94de-c5247fe0b1a6"],
  ["ascended-heroes", "75cd439d-aaa2-41cb-86f3-2fefa5b26e29"],
];

async function get(path) {
  const response = await fetch(`${BASE}${path}`);
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json();
}

for (const [slug, id] of sets) {
  const [shell, market, topChase, cards, pullRates, rip] = await Promise.all([
    get(`/tcgs/pokemon/sets/${id}/shell`),
    get(`/tcgs/pokemon/sets/${id}/market/bootstrap?window=365d`),
    get(`/tcgs/pokemon/sets/${id}/market/top-chase?snapshot_contract=pricing-v4&window=365d&limit=10`),
    get(`/tcgs/pokemon/sets/${id}/cards/page?snapshot_contract=pricing-v4&page=1&page_size=60&section=all-cards&sort=set-number&sort_direction=asc&movement_filter=all`),
    get(`/tcgs/pokemon/sets/${id}/pull-rates`),
    get(`/tcgs/pokemon/sets/${id}/rip/bootstrap`),
  ]);
  const verdict = validateTopChasePayload(topChase, { requestedSetId: id, expectedLimit: 10 });
  const histories = topChase.topChaseCardHistories || topChase.priceHistories || {};
  const points = (topChase.cards || []).map((card) => (card.priceHistory || histories[card.cardVariantId] || []).length);
  const currentDate = market.latestMarketDate || market.meta?.latestMarketDate;
  const marketHistory = market.setValueHistory || market.marketValueHistory || market.cardsMarket?.history || [];
  const cardRows = cards.cards || cards.items || cards.results || [];
  if (!shell?.set?.id && !shell?.id) throw new Error(`${slug}: shell identity missing`);
  if (!currentDate || Number.isNaN(Date.parse(currentDate))) throw new Error(`${slug}: market date missing`);
  if (!marketHistory.length) throw new Error(`${slug}: Set Value history missing`);
  if ((topChase.cards || []).length !== 10 || Math.min(...points) < 2 || !verdict.complete || !verdict.renderable) throw new Error(`${slug}: Top Chase incomplete`);
  if (!cardRows.length) throw new Error(`${slug}: cards empty`);
  if (!pullRates || !rip) throw new Error(`${slug}: Pull Rates or RIP missing`);
  console.log(JSON.stringify({ slug, id, marketDate: currentDate, cards: cardRows.length, topChaseCards: topChase.cards.length, minHistoryPoints: Math.min(...points), validatorStatus: verdict.status, complete: verdict.complete, renderable: verdict.renderable }));
}

console.log("Set live data contract PASS");
