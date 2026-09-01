function validOffer(offer) {
  return offer && typeof offer.offerKey === "string" && Number.isInteger(offer.unitAmount) &&
    offer.unitAmount > 0 && typeof offer.currency === "string" && /^[a-z]{3}$/i.test(offer.currency);
}

export function formatMinorAmount(unitAmount, currency, locale = "en-US") {
  if (!Number.isInteger(unitAmount) || unitAmount < 0 || !/^[a-z]{3}$/i.test(currency || "")) return null;
  return new Intl.NumberFormat(locale, { style: "currency", currency: currency.toUpperCase() }).format(unitAmount / 100);
}

export function pricingByOfferKey(dto) {
  return Object.fromEntries((Array.isArray(dto?.offers) ? dto.offers : [])
    .filter(validOffer).map(offer => [offer.offerKey, offer]));
}

export function annualPricingSummary(monthly, annual) {
  if (!validOffer(monthly) || !validOffer(annual) || monthly.plan !== annual.plan ||
      monthly.billingInterval !== "month" || annual.billingInterval !== "year" ||
      monthly.currency.toLowerCase() !== annual.currency.toLowerCase()) return null;
  const annualizedMonthlyAmount = monthly.unitAmount * 12;
  const annualSavings = annualizedMonthlyAmount - annual.unitAmount;
  if (annualSavings <= 0) return null;
  return { annualizedMonthlyAmount, annualSavings,
    annualDiscountPercent: Math.round((annualSavings / annualizedMonthlyAmount) * 100),
    effectiveMonthlyAnnualRate: Math.round(annual.unitAmount / 12), currency: annual.currency.toLowerCase() };
}

export function planPricingSummary(dto, plan) {
  const offers = Object.values(pricingByOfferKey(dto)).filter(offer => offer.plan === plan);
  const monthly = offers.find(offer => offer.billingInterval === "month") || null;
  const annual = offers.find(offer => offer.billingInterval === "year") || null;
  return { monthly, annual, annualSummary: monthly && annual ? annualPricingSummary(monthly, annual) : null };
}
