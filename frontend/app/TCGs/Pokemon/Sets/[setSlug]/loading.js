import InDexLogoLoader from "@/components/brand/InDexLogoLoader";

export default function TcgSetLoading() {
  return (
    <InDexLogoLoader
      fullScreen
      label="Loading Rip Statistics"
      shouldDelay={false}
      isLoading={true}
    />
  );
}
