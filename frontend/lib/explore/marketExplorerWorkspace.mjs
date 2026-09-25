// ---------------------------------------------------------------------------
// Market Explorer workspace interaction state (pure).
//
// FOUR DIFFERENT FACTS, FOUR DIFFERENT OWNERS. They are never collapsed:
//
//   ACTIVE MARKET       -> the market exists in the workspace (prepared loader,
//                          selection reducer, query hook own this).
//   VISIBLE ON CHART    -> `hidden` below. Hiding is not removing.
//   CONSTITUENT TARGET  -> which ONE active market the Constituents panel is
//                          inspecting. Owned by `requestedDetailSeriesId` in the
//                          client and resolved through resolveActiveDetailSeriesId
//                          (marketExplorerConstituents.mjs); it is derived, never a
//                          label, and never touched by this reducer.
//   FOCUSED MARKET      -> `focused` below. null = comparison mode; a market key =
//                          focus mode. Presentation only: focusing never removes a
//                          market, never changes the target and never refetches.
//
// `hidden` and `focused` live in ONE reducer only because their two transition
// rules must be atomic (a hidden market cannot be focused; hiding the focused
// market ends focus). They remain separate fields.
//
// DETERMINISTIC RULES (asserted in marketExplorerWorkspace.test.mjs):
//   * focusing a HIDDEN market UNHIDES it, then focuses it;
//   * focusing the already-focused market clears focus;
//   * explicitly hiding the focused market CLEARS focus (toggle or hide-all);
//   * removing/clearing markets drops focus if its market is gone.
// No rule here depends on the number of markets or on the plan.
// ---------------------------------------------------------------------------
import { isEnumerableSeries } from "./marketExplorerConstituents.mjs";

export const WORKSPACE_VIEW_ACTIONS = Object.freeze({
  toggleVisibility: "toggleVisibility",
  showAll: "showAll",
  hideAll: "hideAll",
  focus: "focus",
  clearFocus: "clearFocus",
  reconcile: "reconcile",
  reset: "reset",
});

export const createWorkspaceViewState = () => ({ hidden: new Set(), focused: null });

export function reduceWorkspaceView(state, action) {
  switch (action?.type) {
    case WORKSPACE_VIEW_ACTIONS.toggleVisibility: {
      const hidden = new Set(state.hidden);
      if (hidden.has(action.key)) { hidden.delete(action.key); return { ...state, hidden }; }
      hidden.add(action.key);
      return { hidden, focused: state.focused === action.key ? null : state.focused };
    }
    case WORKSPACE_VIEW_ACTIONS.showAll:
      return { ...state, hidden: new Set() };
    case WORKSPACE_VIEW_ACTIONS.hideAll: {
      const keys = new Set(action.keys || []);
      return { hidden: keys, focused: null };
    }
    case WORKSPACE_VIEW_ACTIONS.focus: {
      if (!action.key) return state;
      if (state.focused === action.key) return { ...state, focused: null };
      const hidden = new Set(state.hidden);
      hidden.delete(action.key);
      return { hidden, focused: action.key };
    }
    case WORKSPACE_VIEW_ACTIONS.clearFocus:
      return state.focused === null ? state : { ...state, focused: null };
    case WORKSPACE_VIEW_ACTIONS.reconcile: {
      // Forget bookkeeping for markets that are no longer active.
      const active = new Set(action.activeKeys || []);
      const hidden = new Set([...state.hidden].filter((key) => active.has(key)));
      const focused = state.focused && active.has(state.focused) ? state.focused : null;
      return hidden.size === state.hidden.size && focused === state.focused ? state : { hidden, focused };
    }
    case WORKSPACE_VIEW_ACTIONS.reset:
      return createWorkspaceViewState();
    default:
      return state;
  }
}

/**
 * The switcher's entries: EVERY active market, with target / hidden / focused
 * flags. A market that cannot be enumerated is `disabled` (rendered unavailable,
 * never pretending to load). A chart-hidden market stays selectable.
 */
export function buildConstituentSwitcherEntries(series, { targetKey = null, hiddenKeys = new Set(), focusedKey = null } = {}) {
  return (series || []).filter(Boolean).map((entry) => {
    const enumerable = entry.available !== false && isEnumerableSeries(entry);
    return {
      key: entry.key,
      label: entry.shortLabel || entry.label,
      fullLabel: entry.label,
      color: entry.color,
      enumerable,
      disabled: !enumerable,
      isTarget: enumerable && entry.key === targetKey,
      isHidden: hiddenKeys.has(entry.key),
      isFocused: entry.key === focusedKey,
    };
  });
}

// ---------------------------------------------------------------------------
// Generation-pinned constituent page cache. Keyed by generationId + marketKey for
// prepared markets (a new generation is a new key, so pages from two generations
// can never mix) and by the normalized spec for query markets.
// ---------------------------------------------------------------------------
export function constituentPageCacheKey(identity) {
  if (!identity) return null;
  if (identity.marketKey) return `prepared:${identity.marketKey}:${identity.generationId ?? ""}`;
  return `query:${JSON.stringify(identity)}`;
}

export function createConstituentPageCache() {
  const entries = new Map();
  return {
    get: (key) => (key ? entries.get(key) : undefined),
    set: (key, value) => { if (key) entries.set(key, value); },
    delete: (key) => { entries.delete(key); },
    clear: () => entries.clear(),
    /** Drop every generation of one prepared market (its market was removed). */
    evictMarket: (marketKey) => {
      for (const key of [...entries.keys()]) if (key.startsWith(`prepared:${marketKey}:`)) entries.delete(key);
    },
    keys: () => [...entries.keys()],
    get size() { return entries.size; },
  };
}
