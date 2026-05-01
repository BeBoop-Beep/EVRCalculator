import { redirect } from "next/navigation";

import RipStatisticsPageClient from "@/components/explore/RipStatisticsPageClient";
import { getExplorePagePayload } from "@/lib/explore/explorePageServer";
import { getRipStatisticsTargets } from "@/lib/explore/ripStatisticsServer";

function readParamValue(searchParams, key) {
  const raw = searchParams?.[key];
  if (Array.isArray(raw)) {
    return String(raw[0] || "").trim();
  }
  return String(raw || "").trim();
}

export default async function RipStatisticsPage({ searchParams }) {
  const resolvedSearchParams = (await searchParams) || {};
  const requestedTargetType = readParamValue(resolvedSearchParams, "target_type") || "set";
  const requestedTargetId = readParamValue(resolvedSearchParams, "target_id");

  const targetsPayload = await getRipStatisticsTargets({ limit: 150 });
  const defaultTarget = targetsPayload?.default_target || null;

  if (!requestedTargetId) {
    if (defaultTarget?.target_type && defaultTarget?.target_id) {
      redirect(
        `/Explore/rip-statistics?target_type=${encodeURIComponent(defaultTarget.target_type)}&target_id=${encodeURIComponent(defaultTarget.target_id)}`
      );
    }
  }

  let explorePayload = null;
  let pageError = null;
  if (requestedTargetId) {
    try {
      explorePayload = await getExplorePagePayload(requestedTargetType, requestedTargetId);
      if (!explorePayload) {
        pageError = "No persisted RIP Statistics payload is available for this set.";
      }
    } catch (error) {
      pageError = error?.message || "Failed to load RIP Statistics.";
    }
  }

  const selectedTarget =
    targetsPayload.targets.find(
      (target) =>
        String(target?.target_type || "") === requestedTargetType &&
        String(target?.target_id || "") === requestedTargetId
    ) || null;

  return (
    <RipStatisticsPageClient
      targetsPayload={targetsPayload}
      selectedTarget={selectedTarget}
      requestedTargetType={requestedTargetType}
      requestedTargetId={requestedTargetId}
      explorePayload={explorePayload}
      pageError={pageError}
    />
  );
}