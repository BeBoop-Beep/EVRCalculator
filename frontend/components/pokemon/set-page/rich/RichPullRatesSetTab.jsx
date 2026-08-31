"use client";

import PullRatesTab from "@/components/pokemon/set-page/PullRates/PullRatesTab";
import useSetPullRatesController from "@/hooks/pokemon/useSetPullRatesController";

export default function RichPullRatesSetTab({ setId, canFetch, fallbackAssumptions = null }) {
  const {
    pullRateAssumptions,
    activePullRatesState,
    pullRatesTabPending,
    pullRatesPendingTimedOut,
  } = useSetPullRatesController({
    setId,
    enabled: true,
    canFetch,
    fallbackAssumptions,
  });

  return (
    <PullRatesTab
      pullRateAssumptions={pullRateAssumptions}
      pullRatesTabPending={pullRatesTabPending}
      pullRatesPendingTimedOut={pullRatesPendingTimedOut}
      activePullRatesState={activePullRatesState}
      resolvedSetResourceId={setId}
    />
  );
}
