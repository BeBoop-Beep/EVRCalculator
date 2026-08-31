"use client";

import dynamic from "next/dynamic";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState, useTransition } from "react";
import PublicProfileLocalScaffold from "@/components/Profile/PublicProfileLocalScaffold";
import PageArtworkAtmosphere from "@/components/ui/PageArtworkAtmosphere";
import ReturnToTopButton from "@/components/ui/ReturnToTopButton";
import InDexLogoLoader from "@/components/brand/InDexLogoLoader";
import useMediaQuery from "@/hooks/useMediaQuery";
import useSetRipBootstrapController from "@/hooks/pokemon/useSetRipBootstrapController";
import { useRankingsAccess } from "@/lib/rankings/useRankingsAccess";
import { optimizedImageUrl, SET_LOGO_WIDTH } from "@/lib/images/remoteImageDelivery.mjs";
import { resolvePokemonPublicSetSlug } from "@/lib/pokemon/pokemonCardDetailClient";
import { resolvePokemonBoosterPackAsset } from "@/lib/pokemon/pokemonBoosterPackAssets.mjs";
import { isPublicAnalyticsEligiblePokemonSet } from "@/lib/pokemon/pokemonSetPublicCoverage";
import { selectRequestedPokemonSetTarget } from "@/lib/pokemon/pokemonSetSimulationEvidence.mjs";
import { resolveCanonicalRipV7 } from "@/components/explore/canonicalRipV7.mjs";
import { selectRipHeroScoreMode } from "@/components/explore/ripHeroScoreMode.mjs";
import { getRipTierPresentation } from "@/lib/explore/interpretationTone";
import { selectMobileHeroModel } from "@/components/pokemon/set-page/PokemonSetHero/mobileHeroModel.mjs";
import { selectSetRichSharedViewModel } from "./rich/setRichSharedViewModel.mjs";
import RichSetContextChrome from "./rich/RichSetContextChrome";
import { buildSameSetViewUrl, normalizeSetViewTab } from "./setViewUrl.mjs";

const loadRichRipSetTab = () => import("./rich/RichRipSetTab");
const loadRichMarketSetTab = () => import("./rich/RichMarketSetTab");
const loadRichCardsSetTab = () => import("./rich/RichCardsSetTab");
const loadRichPullRatesSetTab = () => import("./rich/RichPullRatesSetTab");
const RichRipSetTab = dynamic(loadRichRipSetTab, { ssr: false });
const RichMarketSetTab = dynamic(loadRichMarketSetTab, { ssr: false });
const RichCardsSetTab = dynamic(loadRichCardsSetTab, { ssr: false });
const RichPullRatesSetTab = dynamic(loadRichPullRatesSetTab, { ssr: false });

const MOBILE_SET_MENU_HIDE_DISTANCE_PX = 10;
const MOBILE_SET_MENU_REVEAL_DISTANCE_PX = 56;
const MOBILE_SET_MENU_SCROLL_NOISE_PX = 2;
const MOBILE_SET_MENU_TOP_BOUNDARY_PX = 20;
const MOBILE_SET_MENU_BOTTOM_EDGE_PX = 64;
const MOBILE_SET_MENU_GESTURE_NOISE_PX = 4;
const MOBILE_RETURN_TO_TOP_THRESHOLD_PX = 12;
const number = (value) => { const parsed = Number(value); return Number.isFinite(parsed) ? parsed : null; };
function hrefWithState(pathname, searchParams, tab, section = null, extra = {}) { return buildSameSetViewUrl({ pathname, searchParams, tab, section, extra }); }

export default function PokemonSetRichPageClient({ targetsPayload, selectedTarget, requestedTargetType, requestedTargetId, explorePayload = null, shellPayload = null, initialModuleSnapshots = null, pageError, profileBaseHref = "/Explore/rip-statistics", targetHrefById = null }) {
  const router = useRouter(); const pathname = usePathname(); const searchParams = useSearchParams();
  const { canViewRankingsIntelligence: canViewProductRipIntelligence } = useRankingsAccess();
  const [isPending, startTransition] = useTransition();
  const [pickerOpen, setPickerOpen] = useState(false); const [mobileContextHidden, setMobileContextHidden] = useState(false); const [showReturnToTop, setShowReturnToTop] = useState(false); const mobileContextRef = useRef(null);
  const mobileContextHiddenRef = useRef(false);
  const mobileContextScrollRef = useRef({ currentNormalizedY: 0, maxNormalizedY: 0, previousNormalizedY: 0, cumulativeDownwardPx: 0, cumulativeUpwardPx: 0, direction: "none", nearTop: true, pickerOpen: false });
  const rawTargets = Array.isArray(targetsPayload?.targets) ? targetsPayload.targets : [];
  const activeTarget = selectRequestedPokemonSetTarget(rawTargets, requestedTargetId, selectedTarget);
  const switcherTargets = rawTargets.filter((target) => isPublicAnalyticsEligiblePokemonSet(target) || String(target?.target_id || "") === String(requestedTargetId || ""));
  const setId = requestedTargetId || activeTarget?.target_id || activeTarget?.setId || shellPayload?.set?.id || null;
  const activeTab = normalizeSetViewTab(searchParams?.get?.("tab")); const cardsSection = activeTab === "cards" && searchParams?.get?.("section") === "market-movers" ? "market-movers" : "all-cards";
  const serverRipBootstrap = initialModuleSnapshots?.ripBootstrapPayload || null;
  const ripBootstrapController = useSetRipBootstrapController({ setId, initialPayload: serverRipBootstrap, enabled: activeTab === "overview" });
  const ripBootstrap = ripBootstrapController.payload;
  const summary = useMemo(() => ({ ...(shellPayload?.summary || {}), ...(explorePayload?.summary || {}), ...(ripBootstrap?.summary || {}) }), [shellPayload?.summary, explorePayload?.summary, ripBootstrap?.summary]);
  const canonical = useMemo(() => resolveCanonicalRipV7(ripBootstrap?.canonicalSource, explorePayload, shellPayload, activeTarget, summary), [ripBootstrap?.canonicalSource, explorePayload, shellPayload, activeTarget, summary]);
  const ripScore = selectRipHeroScoreMode({ canonical });
  const shared = selectSetRichSharedViewModel({ setId, target: activeTarget, shell: shellPayload, ripBootstrap });
  const cardCount = shared.cardCount;
  const activeSetSlug = resolvePokemonPublicSetSlug(activeTarget) || activeTarget?.canonical_key || null;
  const logoUrl = optimizedImageUrl(activeTarget?.logo_image_url || activeTarget?.hero_image_url || activeTarget?.symbol_image_url || null, SET_LOGO_WIDTH);
  const ambientUrl = optimizedImageUrl(activeTarget?.hero_image_url || activeTarget?.logo_image_url || activeTarget?.symbol_image_url || null, SET_LOGO_WIDTH);
  const isDesktop = useMediaQuery("(min-width: 1200px)", true);
  const mobileHeroModel = useMemo(() => selectMobileHeroModel({ setName: activeTarget?.name || requestedTargetId || "Selected Set", era: activeTarget?.era ?? null, logoUrl }), [activeTarget?.name, activeTarget?.era, requestedTargetId, logoUrl]);
  const ripTier = String(ripScore.tier || "").trim().replace(/\s+tier$/i, ""); const ripRank = number(ripScore.rank); const ripCohort = number(ripScore.cohortSize); const ripPresentation = getRipTierPresentation({ rankTier: ripScore.tier });

  useEffect(() => setPickerOpen(false), [isDesktop, requestedTargetId]);
  useEffect(() => { if (!pickerOpen) return undefined; const outside = (event) => { if (!event.target.closest?.("[data-set-picker]")) setPickerOpen(false); }; const key = (event) => { if (event.key === "Escape") setPickerOpen(false); }; document.addEventListener("mousedown", outside); document.addEventListener("touchstart", outside, { passive: true }); document.addEventListener("keydown", key); return () => { document.removeEventListener("mousedown", outside); document.removeEventListener("touchstart", outside); document.removeEventListener("keydown", key); }; }, [pickerOpen]);
  useEffect(() => { mobileContextHiddenRef.current = mobileContextHidden; }, [mobileContextHidden]);
  useEffect(() => { mobileContextScrollRef.current.pickerOpen = pickerOpen; if (pickerOpen) setMobileContextHidden(false); }, [pickerOpen]);
  useEffect(() => {
    if (typeof window === "undefined") return undefined;
    const mediaQuery = window.matchMedia("(max-width: 1199.98px)");
    const scrollState = mobileContextScrollRef.current;
    const clampScrollY = (rawY) => { const maxY = Math.max(0, (document.documentElement?.scrollHeight || 0) - window.innerHeight); return { normalizedY: Math.min(maxY, Math.max(0, Number.isFinite(rawY) ? rawY : 0)), maxY }; };
    const reset = () => { const { normalizedY, maxY } = clampScrollY(window.scrollY || 0); Object.assign(scrollState, { currentNormalizedY: normalizedY, maxNormalizedY: maxY, previousNormalizedY: normalizedY, cumulativeDownwardPx: 0, cumulativeUpwardPx: 0, direction: normalizedY <= MOBILE_SET_MENU_TOP_BOUNDARY_PX ? "none" : "down", nearTop: normalizedY <= MOBILE_SET_MENU_TOP_BOUNDARY_PX }); setShowReturnToTop(normalizedY > MOBILE_RETURN_TO_TOP_THRESHOLD_PX); };
    let frameId = null; let lastTouchY = null;
    const revealIfNeeded = () => { if (!mediaQuery.matches) { reset(); setMobileContextHidden(false); } };
    const hideImmediately = () => { scrollState.cumulativeUpwardPx = 0; scrollState.direction = "down"; setMobileContextHidden((previous) => previous || true); };
    const updateFromScroll = () => { if (frameId !== null) return; frameId = window.requestAnimationFrame(() => { frameId = null; if (!mediaQuery.matches) { reset(); setMobileContextHidden(false); return; } const { normalizedY: nextY, maxY } = clampScrollY(window.scrollY || 0); const delta = nextY - scrollState.previousNormalizedY; const nearTop = nextY <= MOBILE_SET_MENU_TOP_BOUNDARY_PX; Object.assign(scrollState, { currentNormalizedY: nextY, maxNormalizedY: maxY, previousNormalizedY: nextY, nearTop }); setShowReturnToTop(nextY > MOBILE_RETURN_TO_TOP_THRESHOLD_PX); if (nearTop || scrollState.pickerOpen) { Object.assign(scrollState, { direction: nearTop ? "none" : "up", cumulativeDownwardPx: 0, cumulativeUpwardPx: 0 }); setMobileContextHidden(false); return; } if (Math.abs(delta) <= MOBILE_SET_MENU_SCROLL_NOISE_PX) return; if (delta > 0) { scrollState.direction = "down"; scrollState.cumulativeUpwardPx = 0; scrollState.cumulativeDownwardPx += delta; if (scrollState.cumulativeDownwardPx >= MOBILE_SET_MENU_HIDE_DISTANCE_PX) { scrollState.cumulativeDownwardPx = 0; hideImmediately(); } return; } scrollState.direction = "up"; scrollState.cumulativeDownwardPx = 0; if (!mobileContextHiddenRef.current) { scrollState.cumulativeUpwardPx = 0; return; } scrollState.cumulativeUpwardPx += Math.abs(delta); if (scrollState.cumulativeUpwardPx >= MOBILE_SET_MENU_REVEAL_DISTANCE_PX) { scrollState.cumulativeUpwardPx = 0; setMobileContextHidden((previous) => previous ? false : previous); } }); };
    const bottomEdgeIntent = () => mediaQuery.matches && !scrollState.pickerOpen && !mobileContextHiddenRef.current && scrollState.maxNormalizedY - scrollState.currentNormalizedY <= MOBILE_SET_MENU_BOTTOM_EDGE_PX;
    const wheel = (event) => { if (event.deltaY > MOBILE_SET_MENU_GESTURE_NOISE_PX && bottomEdgeIntent()) hideImmediately(); };
    const touchStart = (event) => { lastTouchY = event.touches?.[0]?.clientY ?? null; };
    const touchMove = (event) => { const nextTouchY = event.touches?.[0]?.clientY; if (nextTouchY == null) return; if (lastTouchY === null) { lastTouchY = nextTouchY; return; } const fingerDeltaUp = lastTouchY - nextTouchY; lastTouchY = nextTouchY; if (fingerDeltaUp > MOBILE_SET_MENU_GESTURE_NOISE_PX && bottomEdgeIntent()) hideImmediately(); };
    const touchEnd = () => { lastTouchY = null; };
    const mediaChange = () => { revealIfNeeded(); updateFromScroll(); };
    reset(); revealIfNeeded(); window.addEventListener("scroll", updateFromScroll, { passive: true }); window.addEventListener("resize", revealIfNeeded); window.addEventListener("wheel", wheel, { passive: true }); window.addEventListener("touchstart", touchStart, { passive: true }); window.addEventListener("touchmove", touchMove, { passive: true }); window.addEventListener("touchend", touchEnd, { passive: true }); window.addEventListener("touchcancel", touchEnd, { passive: true });
    if (typeof mediaQuery.addEventListener === "function") mediaQuery.addEventListener("change", mediaChange); else mediaQuery.addListener?.(mediaChange);
    return () => { window.removeEventListener("scroll", updateFromScroll); window.removeEventListener("resize", revealIfNeeded); window.removeEventListener("wheel", wheel); window.removeEventListener("touchstart", touchStart); window.removeEventListener("touchmove", touchMove); window.removeEventListener("touchend", touchEnd); window.removeEventListener("touchcancel", touchEnd); if (typeof mediaQuery.removeEventListener === "function") mediaQuery.removeEventListener("change", mediaChange); else mediaQuery.removeListener?.(mediaChange); if (frameId !== null) window.cancelAnimationFrame(frameId); };
  }, []);
  useEffect(() => { const scrollState = mobileContextScrollRef.current; const maxY = Math.max(0, (document.documentElement?.scrollHeight || 0) - window.innerHeight); const normalizedY = Math.min(maxY, Math.max(0, window.scrollY || 0)); Object.assign(scrollState, { currentNormalizedY: normalizedY, maxNormalizedY: maxY, previousNormalizedY: normalizedY, cumulativeDownwardPx: 0, cumulativeUpwardPx: 0, direction: normalizedY <= MOBILE_SET_MENU_TOP_BOUNDARY_PX ? "none" : "down", nearTop: normalizedY <= MOBILE_SET_MENU_TOP_BOUNDARY_PX }); }, [requestedTargetId]);
  useEffect(() => { setShowReturnToTop(false); setMobileContextHidden(false); }, [pathname, searchParams, requestedTargetId, activeTab]);
  const handlePickerKeyDown = (event) => { if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return; const options = Array.from(event.currentTarget.querySelectorAll('[role="option"]:not(:disabled)')); if (!options.length) return; event.preventDefault(); const current = options.indexOf(document.activeElement); const next = event.key === "Home" ? 0 : event.key === "End" ? options.length - 1 : event.key === "ArrowDown" ? (current + 1 + options.length) % options.length : (current - 1 + options.length) % options.length; options[next]?.focus(); };
  const selectTarget = (target) => { const id = String(target?.target_id || ""); if (!id || id === String(requestedTargetId || "")) { setPickerOpen(false); return; } const base = targetHrefById?.[id]; if (!base) return; const [path, query = ""] = String(base).split("?"); const params = new URLSearchParams(query); params.set("tab", activeTab); setPickerOpen(false); startTransition(() => router.push(`${path}?${params.toString()}`)); };
  const pushSameSetView = (href) => { const current = `${window.location.pathname}${window.location.search}`; if (href !== current) window.history.pushState(null, "", href); };
  const selectTab = (tab) => { const nextTab = normalizeSetViewTab(tab); if (nextTab === activeTab) return; pushSameSetView(hrefWithState(pathname, searchParams, nextTab)); };
  const selectCardsSection = ({ tab, section }) => { const href = hrefWithState(pathname, searchParams, tab, section); pushSameSetView(href); };
  const tabIntent = (tab, intentType) => { const nextTab = normalizeSetViewTab(tab); if (nextTab === activeTab) return; ({ overview: loadRichRipSetTab, market: loadRichMarketSetTab, cards: loadRichCardsSetTab, "pull-rates": loadRichPullRatesSetTab }[nextTab])?.(); if (nextTab === "overview" && (!(navigator.connection?.saveData) || intentType === "pointerdown")) ripBootstrapController.preload(); };
  const targetIntent = (id) => { const href = targetHrefById?.[String(id || "")]; if (href) router.prefetch(href); };
  const canFetch = Boolean(setId);
  const overviewSeed = initialModuleSnapshots?.overviewPayload || initialModuleSnapshots?.marketDashboardPayload || null;
  const moversSeed = initialModuleSnapshots?.marketMoversPayload || null; const topChaseSeed = initialModuleSnapshots?.marketDashboardPayload || null;
  const moversHref = hrefWithState(pathname, searchParams, "cards", "market-movers", { card_sort: "7d-movers", movement: "all" });
  const chaseHref = hrefWithState(pathname, searchParams, "cards", "all-cards", { card_sort: "current-price", movement: "all" });
  const canRender = !pageError && Boolean(shellPayload || setId);

  return <main className="w-full max-w-full pb-[calc(5.25rem+env(safe-area-inset-bottom)+0.875rem)] pt-0 desk:pb-8 desk:pt-8 [@media(min-width:1440px)_and_(max-height:950px)]:pt-5">
    <PublicProfileLocalScaffold profileBaseHref={profileBaseHref} mode="public" sectionItems={[]} mobileNavItems={[]} desktopSidebarContent={null} mobileToolsPanelContent={null} mobileToolsTitle="Explore Filters & Navigation" mobileToolsDescription="Switch TCG and set filters." mobileToolsPanelAriaLabel="Explore filters and navigation" mobileToolsTriggerLabel="Filters & Tools" mobileToolsTriggerTitle="Open filters and navigation" useFloatingToolsOnTablet={false} forceCompactToolsBelow2xl={false} centerContentIgnoringSidebar desktopSidebarClassName="" desktopBreakpoint="desk" desktopContentOffsetClassName="desk:flex desk:justify-center" contentShellClassName="mx-auto w-full max-w-[960px] desk:max-w-[1440px] desk:px-4 2xl:px-5" wrapDesktopContentInFrame={false} mobileBottomNavVariant="flat" hideDesktopSidebar mobileBottomNavContent={() => null}>
      <div className="dashboard-container relative isolate w-full max-w-full min-w-0 !p-0 !bg-transparent !border-0 !rounded-none set-detail-glass-scope index-environment mx-auto flex max-w-[1400px] flex-col space-y-4 xl:!p-0 xl:!bg-transparent xl:!rounded-none xl:!border-0">
        {ambientUrl ? <PageArtworkAtmosphere src={ambientUrl} dataAttribute="data-set-ambient-artwork" visibilityClassName="hidden sm:block" /> : null}
        {pageError ? <section className="rounded-2xl border border-red-500/30 bg-[var(--surface-panel)] p-5 sm:p-6"><p className="text-base font-semibold text-[var(--text-primary)]">RIP Statistics unavailable</p><p className="mt-2 text-sm text-red-300">{pageError}</p></section> : null}
        {canRender ? <>
          <RichSetContextChrome activeTab={activeTab} onTabChange={selectTab} onTabIntent={tabIntent} isTabNavPending={false} mobileContextHidden={mobileContextHidden} mobileContextRef={mobileContextRef} mobileHeroModel={mobileHeroModel} pickerOpen={pickerOpen} setPickerOpen={isDesktop && pickerOpen} onTogglePicker={() => setPickerOpen((open) => !open)} onSelectTarget={selectTarget} onPickerKeyDown={handlePickerKeyDown} onTargetIntent={targetIntent} targets={switcherTargets} selectedTargetId={requestedTargetId} pickerDisabled={isPending || !switcherTargets.length} isDesktop={isDesktop} logoUrl={logoUrl} selectedName={activeTarget?.name || requestedTargetId || "Selected Set"} selectedTarget={activeTarget} cardCount={cardCount} ripPresentation={ripPresentation} ripTier={ripTier} ripRank={ripRank} ripCohort={ripCohort} />
          {activeTab === "overview" && ripBootstrap ? <RichRipSetTab canonical={canonical} summary={summary} ripDecision={ripBootstrap?.ripDecision ?? explorePayload?.ripDecision ?? null} setId={setId} calculationRunId={ripBootstrap?.calculationRunId} activeCalculationRunId={ripBootstrap?.calculationRunId ?? activeTarget?.calculation_run_id ?? activeTarget?.calculationRunId ?? null} canonicalSource={ripBootstrap?.canonicalSource} canViewProductRipIntelligence={canViewProductRipIntelligence} setName={activeTarget?.name ?? activeTarget?.set_name ?? null} setSlug={activeSetSlug} cardCount={cardCount} pullRatesHref={hrefWithState(pathname, searchParams, "pull-rates")} productImage={resolvePokemonBoosterPackAsset(activeTarget?.canonical_key ?? activeTarget?.canonicalKey)} initialProductId={searchParams?.get?.("sealedProduct") || null} familyFilter={null} /> : null}
          {activeTab === "overview" && !ripBootstrap && ripBootstrapController.state.status !== "error" ? <div className="flex min-h-[40vh] items-center justify-center" aria-busy="true" aria-label="Loading RIP intelligence"><InDexLogoLoader label="Loading RIP intelligence" /></div> : null}
          {activeTab === "overview" && !ripBootstrap && ripBootstrapController.state.status === "error" ? <section className="rounded-2xl border border-red-500/30 bg-[var(--surface-panel)] p-5 sm:p-6"><p className="text-base font-semibold text-[var(--text-primary)]">RIP Statistics unavailable</p><p className="mt-2 text-sm text-red-300">{ripBootstrapController.state.error}</p><button type="button" onClick={ripBootstrapController.retry} className="mt-4 rounded-lg border border-[var(--border-subtle)] px-3 py-2 text-sm font-semibold text-[var(--text-primary)]">Retry</button></section> : null}
          {activeTab === "market" ? <RichMarketSetTab isDesktopHeroComposition={isDesktop} resolvedSetResourceId={setId} activeSetSlug={activeSetSlug} canFetch={canFetch} destinationSeedPending={false} overviewSeed={overviewSeed} moversSeed={moversSeed} topChaseSeed={topChaseSeed} moversTickerHref={moversHref} authoritativeSetCardCount={cardCount} topChaseRowHref={chaseHref} /> : null}
          {activeTab === "cards" ? <RichCardsSetTab cardsSection={cardsSection} handleSetDetailNavSelect={selectCardsSection} setId={setId} canFetch={canFetch} activeSetSlug={activeSetSlug} /> : null}
          {activeTab === "pull-rates" ? <RichPullRatesSetTab setId={setId} canFetch={canFetch} fallbackAssumptions={explorePayload?.pull_rate_assumptions || explorePayload?.pullRateAssumptions || null} /> : null}
          <ReturnToTopButton visible={!isDesktop && showReturnToTop} onActivate={() => { setMobileContextHidden(false); window.scrollTo({ top: 0, behavior: "smooth" }); }} className="hidden desk:bottom-6 desk:left-auto desk:right-6 desk:inline-flex desk:translate-x-0" />
        </> : null}
      </div>
    </PublicProfileLocalScaffold>
  </main>;
}
