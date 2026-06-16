import RipStatisticsPageClient from "@/components/explore/RipStatisticsPageClient";
import { getExplorePagePayload } from "@/lib/explore/explorePageServer";
import { getRipStatisticsTargets } from "@/lib/explore/ripStatisticsServer";
import {
  buildTargetHrefById,
  buildTcgSetHrefFromTarget,
  findTargetBySetSlug,
} from "@/lib/explore/ripStatisticsRouting";
import { redirect } from "next/navigation";

export default async function TcgSetRipStatisticsPage({ params }) {
  const resolvedParams = (await params) || {};
  const requestedSetSlug = String(resolvedParams?.setSlug || "").trim().toLowerCase();

  const targetsPayload = await getRipStatisticsTargets({ limit: 150 });
  const targets = Array.isArray(targetsPayload?.targets) ? targetsPayload.targets : [];
  const defaultTarget = targetsPayload?.default_target || null;
  const targetHrefById = buildTargetHrefById(targets);

  if (!requestedSetSlug && defaultTarget?.target_type === "set") {
    redirect(buildTcgSetHrefFromTarget(defaultTarget));
  }

  const selectedTarget = findTargetBySetSlug(targets, requestedSetSlug);
  const requestedTargetType = selectedTarget?.target_type || "set";
  const requestedTargetId = selectedTarget?.target_id || "";

  let explorePayload = null;
  let pageError = null;

  if (selectedTarget?.target_id) {
    try {
      explorePayload = await getExplorePagePayload(requestedTargetType, requestedTargetId);
      if (!explorePayload) {
        pageError = "No persisted RIP Statistics payload is available for this set.";
      }
    } catch (error) {
      pageError = error?.message || "Failed to load RIP Statistics.";
    }
  } else {
    pageError = "Set not found for this URL.";
  }

  return (
    <RipStatisticsPageClient
      targetsPayload={targetsPayload}
      selectedTarget={selectedTarget}
      requestedTargetType={requestedTargetType}
      requestedTargetId={requestedTargetId}
      explorePayload={explorePayload}
      pageError={pageError}
      profileBaseHref="/TCGs/Pokemon/Sets"
      targetHrefById={targetHrefById}
      setDetailMode
    />
  );
}
