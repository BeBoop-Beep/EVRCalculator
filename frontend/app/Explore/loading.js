import InDexLogoLoader from "@/components/brand/InDexLogoLoader";
import { FULL_LOADER_DELAY_MS, MIN_FULL_LOADER_VISIBLE_MS } from "@/lib/navigation/loadingPolicy";

export default function ExploreLoading() {
  return (
    <InDexLogoLoader
      fullScreen
      label="Loading Explore"
      shouldDelay={true}
      isLoading={true}
      delayConfig={{
        showDelayMs: FULL_LOADER_DELAY_MS,
        minVisibleMs: MIN_FULL_LOADER_VISIBLE_MS,
        debugLabel: "explore-route",
      }}
    />
  );
}
