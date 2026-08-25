"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import PokemonMarketOverview from "./PokemonMarketOverview";
import PokemonMarketPerformance from "./PokemonMarketPerformance";
import {
  buildMarketWindowOptions,
  resolveDefaultMarketWindow,
} from "@/lib/explore/marketOverviewPresentation.mjs";
import styles from "./explore.module.css";

// ONE analytical surface, two panes, ONE timeframe.
//
// Market Overview and Pokémon Market Performance describe the same markets:
// the left pane is the numeric summary, the right pane is those same markets
// through time. They share a single border, background and context, separated
// only by a hairline.
//
// The timeframe state lives HERE rather than in either pane. That is the whole
// reason this component is a client boundary: the overview's dynamic period
// column and the chart must never be able to disagree about which window is
// being read. One selection, one window, both panes.
//
// This component owns NO market data. Both panes read the same published
// `overview` object they always did, and neither computes a market number.
export default function PokemonMarketAnalysis({ overview }) {
  const options = useMemo(() => buildMarketWindowOptions(overview), [overview]);
  // 7D is the page-wide default. resolveDefaultMarketWindow still falls back to
  // the first window the snapshot actually supports, so a short history
  // degrades rather than charting a span that does not exist.
  const defaultWindow = useMemo(() => resolveDefaultMarketWindow(overview, "7D"), [overview]);
  const [requestedWindow, setRequestedWindow] = useState(null);
  const familyKeys = useMemo(
    () => (overview?.families || []).map((family) => family.key),
    [overview]
  );
  const [visibleMarketKeys, setVisibleMarketKeys] = useState(() => new Set(familyKeys));
  const knownMarketKeysRef = useRef(new Set(familyKeys));
  useEffect(() => {
    setVisibleMarketKeys((current) => {
      const published = new Set(familyKeys);
      const next = new Set([...current].filter((key) => published.has(key)));
      for (const key of familyKeys) {
        if (!knownMarketKeysRef.current.has(key)) next.add(key);
      }
      knownMarketKeysRef.current = published;
      return next;
    });
  }, [familyKeys]);
  const toggleMarket = (key) => {
    setVisibleMarketKeys((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };
  // A selection survives only while the backend still reports that window
  // available; otherwise it falls back to the default rather than reading a
  // span the snapshot does not support.
  const selectedWindow = options.find((entry) => entry.key === requestedWindow && entry.available)
    ? requestedWindow
    : defaultWindow;
  const selectedLabel = options.find((entry) => entry.key === selectedWindow)?.label || "";
  const selectedOption = options.find((entry) => entry.key === selectedWindow) || null;

  return (
    <section
      data-market-analysis
      className={`${styles.surfaceQuiet} ${styles.marketAnalysis} ${styles.marketMobileSection} set-glass-surface`}
      aria-label="Pokémon market summary and performance"
    >
      <PokemonMarketOverview
        overview={overview}
        selectedWindow={selectedWindow}
        selectedLabel={selectedLabel}
        visibleMarketKeys={visibleMarketKeys}
        onToggleMarket={toggleMarket}
        isSinceFirstAvailable={selectedOption?.isSinceFirstAvailable === true}
      />
      <PokemonMarketPerformance
        overview={overview}
        options={options}
        selectedWindow={selectedWindow}
        selectedLabel={selectedLabel}
        onWindowChange={setRequestedWindow}
        visibleMarketKeys={visibleMarketKeys}
        onToggleMarket={toggleMarket}
        isSinceFirstAvailable={selectedOption?.isSinceFirstAvailable === true}
        displayStartDate={selectedOption?.displayStartDate || null}
      />
    </section>
  );
}
