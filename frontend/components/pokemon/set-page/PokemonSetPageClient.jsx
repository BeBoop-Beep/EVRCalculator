"use client";

import dynamic from "next/dynamic";
import InDexLogoLoader from "@/components/brand/InDexLogoLoader";

// RipStatisticsPageClient is intentionally kept out of the set route's initial
// client chunk. It currently owns all set analytical tabs and their chart
// dependencies; loading it through a separate chunk prevents that 700KB+
// source module graph from blocking the route shell/hydration. The deeper tab
// extraction can now happen behind this stable boundary without regressing the
// canonical set route.
const RipStatisticsPageClient = dynamic(
  () => import("@/components/explore/RipStatisticsPageClient"),
  {
    ssr: false,
    loading: () => (
      <div className="index-environment flex min-h-[55vh] items-center justify-center px-4 py-12" aria-busy="true" aria-label="Loading set intelligence">
        <InDexLogoLoader label="Loading set intelligence" />
      </div>
    ),
  },
);

export default function PokemonSetPageClient(props) {
  return <RipStatisticsPageClient {...props} setDetailMode />;
}
