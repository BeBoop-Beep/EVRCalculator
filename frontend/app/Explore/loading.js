import InDexLogoLoader from "@/components/brand/InDexLogoLoader";

export default function ExploreLoading() {
  return (
    <InDexLogoLoader
      fullScreen
      label="Loading Explore"
      shouldDelay={true}
      isLoading={true}
      delayConfig={{
        showDelayMs: 200,
        minVisibleMs: 450,
      }}
    />
  );
}