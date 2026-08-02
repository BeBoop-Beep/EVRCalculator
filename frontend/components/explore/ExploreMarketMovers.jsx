import SevenDayMarketMoversTicker from "./SevenDayMarketMoversTicker";
export default function ExploreMarketMovers({ payload }) {
  const failed = Boolean(payload?.meta?.requestFailed);
  return <section aria-labelledby="explore-market-movers-heading">
    <h2 id="explore-market-movers-heading" className="sr-only">Global 7-Day Market Movers</h2>
    <SevenDayMarketMoversTicker entry={payload?.marketMovers} maxItems={30} scope="explore"
      status={failed ? "error" : "success"} error="Global 7-day movers are currently unavailable." />
  </section>;
}
