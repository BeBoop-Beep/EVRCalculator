import InDexLogoLoader from "@/components/brand/InDexLogoLoader";

export default function TcgSetLoading() {
  return (
    <InDexLogoLoader
      fullScreen
      label="Loading Rip Statistics"
      shouldDelay={true}
      isLoading={true}
      delayConfig={{
        showDelayMs: 200,
        minVisibleMs: 450,
      }}
    />
  );
}
