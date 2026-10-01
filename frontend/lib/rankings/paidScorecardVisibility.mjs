/**
 * Pure visibility rule: paid rows are only ever exposed to an entitled viewer
 * and only when they were loaded under the CURRENT access identity.  Losing
 * entitlement (or switching identity) hides them on the very next render.
 */
export function resolvePaidScorecards({ entitled, identity, state }) {
  const current = Boolean(entitled) && identity != null && state?.identity === identity;
  return current ? { status: state.status, scorecards: state.scorecards } : { status: entitled ? "loading" : "idle", scorecards: null };
}
