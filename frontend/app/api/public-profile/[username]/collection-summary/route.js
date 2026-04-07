// Active route handler for public profile collection summary. Consumed via publicCollectionSummaryAccessor.js.
import { NextResponse } from "next/server";
import { createSupabaseAdminClient } from "@/lib/supabaseServer";
import { normalizeUsernameForRoute } from "@/lib/profile/publicIdentity";

/** @param {unknown} value */
function toPositiveInt(value) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value > 0 ? Math.trunc(value) : 0;
  }

  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) && parsed > 0 ? Math.trunc(parsed) : 0;
  }

  return 0;
}

/** @param {unknown} value */
function toNullableFiniteNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }

  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/** @param {unknown} row */
function extractMarketPrice(row) {
  if (!row || typeof row !== "object" || Array.isArray(row)) {
    return 0;
  }

  const priceRow = /** @type {{ market_price?: unknown; current_market_price?: unknown; price?: unknown }} */ (row);
  const value = priceRow.market_price ?? priceRow.current_market_price ?? priceRow.price ?? null;
  const parsed = Number(value);

  if (!Number.isFinite(parsed) || parsed <= 0) {
    return 0;
  }

  return parsed;
}

/**
 * @param {ReturnType<typeof createSupabaseAdminClient>} adminClient
 * @param {string | number | null | undefined} cardVariantId
 * @param {string | number | null | undefined} conditionId
 */
async function getLatestCardMarketPrice(adminClient, cardVariantId, conditionId, holdingId) {
  if (cardVariantId === null || cardVariantId === undefined) {
    return 0;
  }

  let query = adminClient
    .from("card_market_usd_latest")
    .select("*")
    .eq("variant_id", cardVariantId);

  if (conditionId === null || conditionId === undefined) {
    query = query.is("condition_id", null);
  } else {
    query = query.eq("condition_id", conditionId);
  }

  const { data } = await query.maybeSingle();
  return extractMarketPrice(data);
}

/**
 * @param {ReturnType<typeof createSupabaseAdminClient>} adminClient
 * @param {string | number | null | undefined} sealedProductId
 */
async function getLatestSealedMarketPrice(adminClient, sealedProductId, holdingId) {
  if (sealedProductId === null || sealedProductId === undefined) {
    console.log(`[sealed-pricing] holding_id=${holdingId ?? "unknown"} sealed_product_id=null — skipping price lookup`);
    return 0;
  }

  const { data, error } = await adminClient
    .from("sealed_product_price_observations")
    .select("market_price,captured_at")
    .eq("sealed_product_id", sealedProductId)
    .order("captured_at", { ascending: false })
    .limit(1)
    .maybeSingle();

  if (error) {
    console.error(`[sealed-pricing] holding_id=${holdingId ?? "unknown"} sealed_product_id=${sealedProductId} query_error=${error.message}`);
    return 0;
  }

  const raw = data?.market_price ?? null;
  const marketPrice = raw !== null && Number.isFinite(Number(raw)) && Number(raw) > 0 ? Number(raw) : 0;
  console.log(
    `[sealed-pricing] holding_id=${holdingId ?? "unknown"} sealed_product_id=${sealedProductId} row_found=${Boolean(data)} captured_at=${data?.captured_at ?? "n/a"} market_price=${marketPrice}`
  );
  return marketPrice;
}

/**
 * @param {ReturnType<typeof createSupabaseAdminClient>} adminClient
 * @param {string | number | null | undefined} gradedCardVariantId
 */
async function getLatestGradedMarketPrice(adminClient, gradedCardVariantId, holdingId) {
  if (gradedCardVariantId === null || gradedCardVariantId === undefined) {
    console.log(`[graded-pricing] holding_id=${holdingId ?? "unknown"} graded_card_variant_id=null — skipping price lookup`);
    return 0;
  }

  const { data, error } = await adminClient
    .from("graded_card_variant_price_observations")
    .select("market_price,captured_at")
    .eq("graded_card_variant_id", gradedCardVariantId)
    .order("captured_at", { ascending: false })
    .limit(1)
    .maybeSingle();

  if (error) {
    console.error(`[graded-pricing] holding_id=${holdingId ?? "unknown"} graded_card_variant_id=${gradedCardVariantId} query_error=${error.message}`);
    return 0;
  }

  const raw = data?.market_price ?? null;
  const marketPrice = raw !== null && Number.isFinite(Number(raw)) && Number(raw) > 0 ? Number(raw) : 0;
  console.log(
    `[graded-pricing] holding_id=${holdingId ?? "unknown"} graded_card_variant_id=${gradedCardVariantId} row_found=${Boolean(data)} captured_at=${data?.captured_at ?? "n/a"} market_price=${marketPrice}`
  );
  return marketPrice;
}

export async function GET(_req, { params }) {
  const { username: usernameParam } = await params;
  const rawUsername = typeof usernameParam === "string" ? usernameParam.trim() : "";

  if (!rawUsername) {
    return NextResponse.json({ error: "Invalid username." }, { status: 400 });
  }

  const username = normalizeUsernameForRoute(rawUsername);
  const adminClient = createSupabaseAdminClient();

  const { data: user, error: userError } = await adminClient
    .from("users")
    .select("id, username")
    .eq("username", username)
    .maybeSingle();

  if (userError) {
    return NextResponse.json({ error: "Failed to load collection summary." }, { status: 500 });
  }

  if (!user?.id) {
    return NextResponse.json({ error: "User not found." }, { status: 404 });
  }

  const [cardsResult, sealedResult, gradedResult] = await Promise.all([
    adminClient
      .from("user_card_holdings")
      .select("id,card_variant_id,condition_id,quantity")
      .eq("user_id", user.id),
    adminClient
      .from("user_sealed_product_holdings")
      .select("id,sealed_product_id,quantity")
      .eq("user_id", user.id),
    adminClient
      .from("user_graded_card_holdings")
      .select("id,graded_card_variant_id,quantity")
      .eq("user_id", user.id),
  ]);

  if (cardsResult.error || sealedResult.error || gradedResult.error) {
    return NextResponse.json({ error: "Failed to load collection summary." }, { status: 500 });
  }

  const cardHoldings = cardsResult.data || [];
  const sealedHoldings = sealedResult.data || [];
  const gradedHoldings = gradedResult.data || [];

  const [cardValue, sealedValue, gradedValue] = await Promise.all([
    Promise.all(
      cardHoldings.map(async (row) => {
        const quantity = toPositiveInt(row.quantity);
        if (!quantity) return 0;

        const marketPrice = await getLatestCardMarketPrice(adminClient, row.card_variant_id, row.condition_id, row.id);
        return quantity * marketPrice;
      })
    ).then((values) => values.reduce((sum, value) => sum + value, 0)),
    Promise.all(
      sealedHoldings.map(async (row) => {
        const quantity = toPositiveInt(row.quantity);
        if (!quantity) return 0;

        const marketPrice = await getLatestSealedMarketPrice(adminClient, row.sealed_product_id, row.id);
        return quantity * marketPrice;
      })
    ).then((values) => values.reduce((sum, value) => sum + value, 0)),
    Promise.all(
      gradedHoldings.map(async (row) => {
        const quantity = toPositiveInt(row.quantity);
        if (!quantity) return 0;

        const marketPrice = await getLatestGradedMarketPrice(adminClient, row.graded_card_variant_id, row.id);
        return quantity * marketPrice;
      })
    ).then((values) => values.reduce((sum, value) => sum + value, 0)),
  ]);

  const summary = {
    portfolio_value: toNullableFiniteNumber(cardValue + sealedValue + gradedValue) ?? 0,
    cards_count: toNullableFiniteNumber(cardHoldings.reduce((sum, row) => sum + toPositiveInt(row.quantity), 0)) ?? 0,
    sealed_count: toNullableFiniteNumber(sealedHoldings.reduce((sum, row) => sum + toPositiveInt(row.quantity), 0)) ?? 0,
    graded_count: toNullableFiniteNumber(gradedHoldings.reduce((sum, row) => sum + toPositiveInt(row.quantity), 0)) ?? 0,
  };

  return NextResponse.json({ collection_summary: summary }, { status: 200 });
}