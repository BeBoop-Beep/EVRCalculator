// The open-set policy for a RIP metric disclosure section.
//
// Pure and dependency-free, so it can be exercised directly rather than only
// through a rendered component: the interesting behaviour here is a decision
// about which rows stay open, and that decision is worth testing on its own.
//
// TWO POLICIES, ONE SECTION AT A TIME
// -----------------------------------
//   mobile   one row open at a time. Opening a row closes the previous one, so
//            a phone never has to scroll past four expanded panels to reach the
//            fifth.
//   desktop  any number open. There is room to compare two components side by
//            side, and applying the mobile rule there would remove that.
//
// This function knows nothing about WHICH section it is deciding for. Financial
// RIP and Collector Appeal each hold their own open-set and call this
// separately, which is what keeps their accordions independent.

/**
 * The next open-key set after toggling `key`.
 *
 * Closing is identical at both widths — a row the reader closed is closed.
 * Only OPENING differs: desktop accumulates, mobile replaces.
 *
 * Returns a new array; the input is never mutated.
 */
export function resolveNextOpenKeys(openKeys, key, { isDesktop = true } = {}) {
  const current = Array.isArray(openKeys) ? openKeys : [];

  if (current.includes(key)) {
    return current.filter((openKey) => openKey !== key);
  }

  return isDesktop ? [...current, key] : [key];
}
