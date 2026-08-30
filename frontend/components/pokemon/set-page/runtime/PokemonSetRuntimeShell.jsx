"use client";

import dynamic from "next/dynamic";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState, useTransition } from "react";
import PageArtworkAtmosphere from "@/components/ui/PageArtworkAtmosphere";
import ReturnToTopButton from "@/components/ui/ReturnToTopButton";
import SetRuntimeHeader from "./SetRuntimeHeader";
import SetRuntimeLoading from "./SetRuntimeLoading";
import SetRuntimeTabs from "./SetRuntimeTabs";
import { buildSetRuntimeHref, normalizeSetRuntimeTab, resolveSetRuntimeIdentity } from "./setRuntimeRoute.mjs";

// Transitional Effort-1 boundary. RIP and Market remain in the legacy client
// until their own extraction efforts; keeping this import dynamic prevents
// that graph (including Recharts) from entering cold Cards/Pull Rates visits.
const RipMarketSetTab = dynamic(() => import("@/components/explore/RipStatisticsPageClient"), {
  ssr: false,
  loading: () => <SetRuntimeLoading />,
});
const CardsSetTab = dynamic(() => import("../tabs/CardsSetTab"), {
  ssr: false,
  loading: () => <SetRuntimeLoading label="Loading cards" />,
});
const PullRatesSetTab = dynamic(() => import("../tabs/PullRatesSetTab"), {
  ssr: false,
  loading: () => <SetRuntimeLoading label="Loading pull rates" />,
});

export default function PokemonSetRuntimeShell(props) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();
  const [showReturnToTop, setShowReturnToTop] = useState(false);
  const activeTab = normalizeSetRuntimeTab(searchParams?.get?.("tab"));
  const targets = useMemo(() => Array.isArray(props.targetsPayload?.targets) ? props.targetsPayload.targets : [], [props.targetsPayload?.targets]);
  const setId = resolveSetRuntimeIdentity(props);
  const setSlug = props.selectedTarget?.slug || props.selectedTarget?.canonical_key || props.requestedTargetId;
  const artworkUrl = props.selectedTarget?.artwork_url || props.selectedTarget?.artworkUrl || props.shellPayload?.set?.artworkUrl || null;

  useEffect(() => {
    const onScroll = () => setShowReturnToTop(window.scrollY > 12);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const selectTab = (tab) => {
    const href = buildSetRuntimeHref(pathname, searchParams, tab);
    startTransition(() => router.push(href, { scroll: false }));
    window.requestAnimationFrame(() => document.getElementById("set-runtime-content")?.scrollIntoView({ block: "start" }));
  };
  const selectTarget = (targetId, baseHref, tab) => {
    if (!baseHref) return;
    const separator = baseHref.includes("?") ? "&" : "?";
    router.push(`${baseHref}${separator}tab=${encodeURIComponent(tab)}`);
  };
  const prefetchCards = () => {
    if (!setId) return;
    import("../tabs/CardsSetTab").then((module) => module.prefetchCardsSetTab(setId)).catch(() => {});
  };

  if (activeTab === "overview" || activeTab === "market") {
    return <RipMarketSetTab {...props} setDetailMode />;
  }

  return (
    <main className="index-environment relative min-h-screen w-full pb-[calc(5.25rem+env(safe-area-inset-bottom))] desk:pb-8">
      {artworkUrl ? <PageArtworkAtmosphere src={artworkUrl} /> : null}
      <div className="relative z-10 mx-auto w-full max-w-[1536px] px-3 py-3 sm:px-5 desk:py-6">
        <div className="set-glass-surface sticky top-[var(--app-header-offset,0px)] z-30 overflow-hidden rounded-2xl border backdrop-blur-xl">
          <SetRuntimeHeader selectedTarget={props.selectedTarget} requestedTargetId={props.requestedTargetId} targets={targets} targetHrefById={props.targetHrefById} activeTab={activeTab} onTargetChange={selectTarget} />
          <SetRuntimeTabs activeTab={activeTab} onSelect={selectTab} onCardsIntent={prefetchCards} />
          {isPending ? <div className="h-0.5 animate-pulse bg-[var(--accent)]" aria-label="Changing tab" /> : null}
        </div>
        <div id="set-runtime-content" className="scroll-mt-40 pt-4">
          {props.pageError ? <div role="alert" className="set-glass-surface rounded-xl border p-5 text-sm text-red-300">{props.pageError}</div> : null}
          {!props.pageError && activeTab === "cards" ? <CardsSetTab key={setId} setId={setId} setSlug={setSlug} /> : null}
          {!props.pageError && activeTab === "pull-rates" ? <PullRatesSetTab key={setId} setId={setId} initialData={props.initialModuleSnapshots?.pullRatesPayload || null} /> : null}
        </div>
      </div>
      <ReturnToTopButton visible={showReturnToTop} onActivate={() => window.scrollTo({ top: 0, behavior: "smooth" })} />
    </main>
  );
}
