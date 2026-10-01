import SevenDayMarketMoversTicker from "./SevenDayMarketMoversTicker";

// Wrapper only. The ticker's imagery, item selection and interaction are
// shared — this file contributes only the section heading and Market-wide 50-item cap
// needs now that it opens the page directly beneath the header metadata. The
// heading stands alone: no descriptive subtitle between it and the ticker.
export default function ExploreMarketMovers({ payload }) {
  const failed = Boolean(payload?.meta?.requestFailed);
  return <section aria-labelledby="explore-market-movers-heading">
    <div className="mb-2">
      <h2 id="explore-market-movers-heading" className="text-[18px] font-semibold text-[var(--text-primary)] desk:text-[15px]">7D Market Movers</h2>
    </div>
    <SevenDayMarketMoversTicker entry={payload?.marketMovers} maxItems={50} scope="explore" thumbnailSize="medium"
      status={failed ? "error" : "success"} error="Global 7-day movers are currently unavailable." />
  </section>;
}
