import InDexLogoLoader from "@/components/brand/InDexLogoLoader";

export default function SetRuntimeLoading({ label = "Loading set intelligence" }) {
  return (
    <div className="index-environment flex min-h-[40vh] items-center justify-center px-4 py-12" aria-busy="true" aria-label={label}>
      <InDexLogoLoader label={label} />
    </div>
  );
}
