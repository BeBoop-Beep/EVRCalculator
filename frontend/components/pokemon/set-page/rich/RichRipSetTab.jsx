"use client";

import RipDecisionPage from "@/components/explore/RipDecisionPage";
import useSetRipProgressiveController from "@/hooks/pokemon/useSetRipProgressiveController";

export default function RichRipSetTab({
  canonical,
  summary,
  ripDecision,
  setId,
  calculationRunId,
  activeCalculationRunId,
  canonicalSource,
  canViewProductRipIntelligence,
  setName,
  setSlug,
  cardCount,
  pullRatesHref,
  productImage,
  initialProductId,
  familyFilter,
}) {
  const {
    rankContextState,
    simulationState,
    advancedState,
    rankContext,
    simulation,
    advanced,
    loadRankContext,
    loadSimulation,
    loadAdvanced,
  } = useSetRipProgressiveController({
    setId,
    calculationRunId,
    canonicalSource,
    rankContextEnabled: canViewProductRipIntelligence && Boolean(setId && calculationRunId),
    canViewProductRipIntelligence,
  });

  return (
    <RipDecisionPage
      canonical={canonical}
      summary={summary}
      ripDecision={ripDecision}
      productFamilyRankings={rankContext?.productFamilyRankings ?? null}
      rankContextFreshness={rankContext?.freshness ?? null}
      rankContextUpdatedAt={rankContext?.rankingUpdatedAt ?? null}
      evRepresentativeness={simulation?.evRepresentativeness ?? null}
      openingOutcomeProfile={simulation?.openingOutcomeProfile ?? null}
      calculationRunId={activeCalculationRunId}
      rankContextStatus={rankContextState.status}
      rankContextError={rankContextState.error}
      onRankContextRetry={() => loadRankContext({ force: true })}
      canViewProductRipIntelligence={canViewProductRipIntelligence}
      setRip={null}
      setName={setName}
      setSlug={setSlug}
      cardCount={cardCount}
      pullRatesHref={pullRatesHref}
      productType="booster_pack"
      productLabel="Booster Pack"
      productImage={productImage}
      distributionBins={simulation?.distributionBins ?? []}
      thresholdBins={simulation?.thresholdBins ?? []}
      percentiles={simulation?.percentiles ?? []}
      simulationSummary={simulation?.summary ?? null}
      simulationStatus={simulation ? "success" : (simulationState.setId === setId && simulationState.calculationRunId === calculationRunId ? simulationState.status : "idle")}
      simulationError={simulationState.error}
      onSimulationApproach={loadSimulation}
      onSimulationRetry={() => loadSimulation({ force: true })}
      advancedEvidence={advanced}
      advancedStatus={advanced ? "success" : (advancedState.setId === setId && advancedState.calculationRunId === calculationRunId ? advancedState.status : "idle")}
      advancedError={advancedState.error}
      onAdvancedApproach={loadAdvanced}
      onAdvancedRetry={() => loadAdvanced({ force: true })}
      initialProductId={initialProductId}
      familyFilter={familyFilter}
    />
  );
}
