"use client";

import dynamic from "next/dynamic";
import { useState } from "react";
import SegmentedControl from "@/components/ui/SegmentedControl";
import styles from "./explore.module.css";

const Collector = dynamic(() => import("./CardCollectorAppealRankings"));
const Chase = dynamic(() => import("./CardChaseEfficiencyRankings"));

export default function CardRankingsHub({
  canViewCollectorAppeal,
  canViewChaseEfficiency,
  authStatus,
  sessionCache,
}) {
  const [lens, setLens] = useState("collector");
  return (
    <div className="space-y-4" data-card-rankings-hub>
      <div className="flex justify-start" data-card-ranking-mode-control>
        <SegmentedControl
          options={[
            { value: "collector", label: "Collector Appeal" },
            { value: "chase", label: "Chase Efficiency" },
          ]}
          value={lens}
          onChange={setLens}
          ariaLabel="Card ranking lens"
          variant="rankings"
          equalWidth
          mobileFullWidth
        />
      </div>
      {authStatus === "resolving" ? (
        <div role="status" aria-live="polite" className="min-h-40 p-5 text-sm text-[var(--text-secondary)]">Checking card accessâ€¦</div>
      ) : null}
      {authStatus !== "resolving" && lens === "collector" ? (
        <Collector
          entitled={canViewCollectorAppeal}
          authStatus={authStatus}
          sessionCache={sessionCache}
        />
      ) : null}
      {authStatus !== "resolving" && lens === "chase" ? (
        <Chase
          entitled={canViewChaseEfficiency}
          authStatus={authStatus}
          sessionCache={sessionCache}
        />
      ) : null}
    </div>
  );
}
