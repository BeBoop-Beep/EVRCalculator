export const createCardsPageState = (setId = null) => ({
  status: "idle",
  setId,
  scopeKey: null,
  page: 1,
  cards: [],
  pagination: null,
  filters: null,
  meta: null,
  error: null,
});

const cardIdentity = (card) => String(card?.id || card?.cardNumber || card?.card_number || card?.name || "");

export function mergeCardsPage(previous, payload, { setId, scopeKey, requestedPage }) {
  const shouldAppend =
    requestedPage > 1 &&
    previous.setId === setId &&
    previous.scopeKey === scopeKey &&
    previous.cards.length > 0;
  const incoming = Array.isArray(payload?.cards) ? payload.cards : [];
  const cards = shouldAppend
    ? [...previous.cards, ...incoming].filter((card, index, rows) => {
        const key = cardIdentity(card);
        return !key || rows.findIndex((candidate) => cardIdentity(candidate) === key) === index;
      })
    : incoming;
  return {
    status: cards.length > 0 ? "success" : "empty",
    setId,
    scopeKey,
    page: payload?.pagination?.page ?? requestedPage,
    cards,
    pagination: payload?.pagination || null,
    filters: payload?.filters || null,
    meta: payload?.meta || null,
    error: null,
  };
}
