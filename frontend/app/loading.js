import InDexLogoLoader from "@/components/brand/InDexLogoLoader";

export default function Loading() {
  return (
    <InDexLogoLoader
      fullScreen
      label="Loading inDex"
      shouldDelay={true}
      isLoading={true}
      delayConfig={{
        showDelayMs: 200,
        minVisibleMs: 450,
      }}
    />
  );
}