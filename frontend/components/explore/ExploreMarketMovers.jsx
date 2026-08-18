import SevenDayMarketMoversTicker from "./SevenDayMarketMoversTicker";

// Wrapper only. The ticker's imagery, item selection and interaction are
// unchanged — the section gains the explicit heading it needs now that it sits
// below Market Overview and Market Performance as supporting detail.
export default function ExploreMarketMovers({ payload }) {
  const failed = Boolean(payload?.meta?.requestFailed);
  return <section aria-labelledby="explore-market-movers-heading">
    <div className="mb-2">
      <h2 id="explore-market-movers-heading" className="text-[18px] font-semibold text-[var(--text-primary)] desk:text-[15px]">7D Market Movers</h2>
      <p className="mt-0.5 text-xs text-[var(--text-secondary)]">Largest card-price moves across tracked sets.</p>
    </div>
    <SevenDayMarketMoversTicker entry={payload?.marketMovers} maxItems={30} scope="explore" thumbnailSize="medium"
      status={failed ? "error" : "success"} error="Global 7-day movers are currently unavailable." />
  </section>;
}
