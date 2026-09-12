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
  targets,
  sessionCache,
}) {
  const [lens, setLens] = useState("collector");
  return (
    <div className="space-y-4" data-card-rankings-hub>
      <section className={`${styles.surface} set-glass-surface p-3`}>
        <SegmentedControl
          options={[
            { value: "collector", label: "Collector Appeal" },
            { value: "chase", label: "Chase Efficiency" },
          ]}
          value={lens}
          onChange={setLens}
          ariaLabel="Card ranking lens"
          equalWidth
          mobileFullWidth
        />
      </section>
      {lens === "collector" ? (
        <Collector
          entitled={canViewCollectorAppeal}
          targets={targets}
          sessionCache={sessionCache}
        />
      ) : null}
      {lens === "chase" ? (
        <Chase
          entitled={canViewChaseEfficiency}
          targets={targets}
          sessionCache={sessionCache}
        />
      ) : null}
    </div>
  );
}
