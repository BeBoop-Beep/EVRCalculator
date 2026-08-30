"use client";

import dynamic from "next/dynamic";
import InDexLogoLoader from "@/components/brand/InDexLogoLoader";

const RipStatisticsPageClient = dynamic(
  () => import("@/components/explore/RipStatisticsPageClient"),
  {
    ssr: false,
    loading: () => (
      <div
        className="index-environment flex min-h-[55vh] items-center justify-center px-4 py-12"
        aria-busy="true"
        aria-label="Loading set intelligence"
      >
        <InDexLogoLoader label="Loading set intelligence" />
      </div>
    ),
  },
);

export default function PokemonSetPageClient(props) {
  return <RipStatisticsPageClient {...props} setDetailMode />;
}
