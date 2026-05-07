import PackSimulator from "@/components/tools/PackSimulator";
import { getRipStatisticsTargets } from "@/lib/explore/ripStatisticsServer";

export default async function ToolsPage() {
  const targetsPayload = await getRipStatisticsTargets({ limit: 150 });
  const targets = Array.isArray(targetsPayload?.targets) ? targetsPayload.targets : [];
  const defaultTargetId = String(targetsPayload?.default_target?.target_id || "");

  return (
    <PackSimulator targets={targets} defaultTargetId={defaultTargetId} />
  );
}
