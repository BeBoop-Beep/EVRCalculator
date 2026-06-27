"use client";

import { useMemo } from "react";
import {
  adaptCardDemandValidation,
  adaptDesirabilityValidation,
} from "../../../lib/pokemon/set-page/setPageAdapters.mjs";

export function usePokemonSetValidationQuery({ targets, cards, cardAppealMarketPriceCorrelation, metricKey, scopeKey } = {}) {
  return useMemo(
    () => ({
      status: "success",
      desirabilityValidation: adaptDesirabilityValidation({ targets }, { metricKey }),
      cardDemandValidation: adaptCardDemandValidation(
        { cards },
        { metricKey: metricKey || "pure", scopeKey: scopeKey || "priced", correlation: cardAppealMarketPriceCorrelation }
      ),
      error: null,
    }),
    [cardAppealMarketPriceCorrelation, cards, metricKey, scopeKey, targets]
  );
}
