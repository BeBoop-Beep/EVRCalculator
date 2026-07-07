import InDexLogoLoader from "@/components/brand/InDexLogoLoader";

export default function ExploreLoading() {
  return (
    <InDexLogoLoader
      fullScreen
      label="Loading Explore"
      shouldDelay={false}
      isLoading={true}
    />
  );
}
