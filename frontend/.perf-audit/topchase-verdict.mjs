import { normalizeTopChasePayload } from "../lib/pokemon/pokemonSetMarketClient.js";
import { validateTopChasePayload } from "../lib/pokemon/topChasePayloadContract.mjs";

const SETS = ["ascendedheroes", "shroudedfable", "prismaticevolutions", "scarletandviolet151"];
for (const s of SETS) {
  const url = `http://127.0.0.1:8000/tcgs/pokemon/sets/${s}/market/top-chase?snapshot_contract=pricing-v4&window=365d&limit=10`;
  const res = await fetch(url);
  const raw = await res.json();
  const normalized = normalizeTopChasePayload(raw);
  const v = validateTopChasePayload(normalized, { setId: s, window: "365d", limit: 10 });
  console.log(
    s.padEnd(22),
    "status=", String(v.status).padEnd(24),
    "complete=", String(v.complete).padEnd(5),
    "renderable=", String(v.renderable).padEnd(5),
    "cards=", v.cardCount,
    "priced=", v.pricedCardCount,
    "renderableCards=", v.renderableCardCount,
    "maxPts=", v.maxHistoryPoints,
    "reasons=", JSON.stringify(v.reasons)
  );
}
