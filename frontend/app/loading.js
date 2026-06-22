import InDexLogoLoader from "@/components/brand/InDexLogoLoader";
import { FULL_LOADER_DELAY_MS, MIN_FULL_LOADER_VISIBLE_MS } from "@/lib/navigation/loadingPolicy";

export default function Loading() {
  return (
    <InDexLogoLoader
      fullScreen
      label="Loading inDex"
      shouldDelay={true}
      isLoading={true}
      delayConfig={{
        showDelayMs: FULL_LOADER_DELAY_MS,
        minVisibleMs: MIN_FULL_LOADER_VISIBLE_MS,
        debugLabel: "root-route",
      }}
    />
  );
}
