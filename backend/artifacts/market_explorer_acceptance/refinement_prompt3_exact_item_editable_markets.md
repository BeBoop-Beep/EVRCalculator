# Market Explorer Refinement Prompt 3 — Exact Item Editable Markets

## A. Branch / starting HEAD

- Branch: `fix/backend-memory-restart-p0-20260904`
- Starting HEAD: `64c72c23229efed5749bf902aba684bc73ff0ae4`

## B. Market-instance architecture

Query-built series now carry a client-generated `instanceId` as stable workspace identity. The backend `queryFingerprint` remains semantic/cache identity. Updating replaces the result under the same instance key and preserves its color, position, visibility key, and inspection target.

## C. Unified search UI

One reusable exact-item picker calls the Prompt-1 unified endpoint through a same-origin authenticated proxy. It uses a 300 ms debounce, two-character minimum, `AbortController`, request tokens, hard limit 20, loading/error/empty states, Enter-first-result behavior, and Escape clearing.

## D. Physical identity presentation

Card rows include name, set, number, rarity, edition, printing, and special treatment. Sealed rows include name, set, family/type, and variant label. Unsupported graded results are never selectable.

## E. 25-item selection behavior

Selections survive subsequent searches, reject duplicate IDs, support removal, report `N of 25 selected`, and disable additions with an explanation at 25. Exact mode with zero selections disables Build instead of serializing an empty list as Global.

## F. Exact basket Build behavior

Exact mode sends one canonical `membershipMode=explicit` query with sorted IDs, yielding one series. The draft stays mounted during build and remains intact on failure. Pending semantic keys prevent double-click duplicates.

## G. Edit lifecycle

Custom query chips expose a distinct Edit action. Edit loads the normalized spec and original explicit definition into the single Builder draft. Filter and Exact Items modes share this state. Unsaved changes do not mutate active data. Cancel makes no request.

## H. Update behavior

Update executes before replacement. Success retains `instanceId`, key, color, visibility, order, and inspection while permitting fingerprint change. Failure leaves the old line and draft intact. Equivalent edits show `No changes` and issue no request. Linked Top-N benchmarks update coherently.

## I. Save-as-new behavior

Save as new uses the add lifecycle, preserving the original and assigning a new instance ID. Existing or pending semantic specs are rejected coherently.

## J. Constituents Edit Items

An explicit market exposes `Edit Items`, opening the same Builder state from its spec and retained item metadata—not the currently priced/paged roster. Paging and movement remain independent.

## K. Filter-market editing

Filter-built markets restore normalized filters and composition. No fake row-removal/exclusion control is offered.

## L. Entitlement behavior

Exact Items is marked Premium. Access evaluation disables Build/Update for lower plans without clearing the draft; backend enforcement remains unchanged.

## M. Concurrency/request safety

Search aborts and token-rejects stale responses. Semantic keys suppress duplicate concurrent operations. Updates target instance IDs; removing a market closes its edit session and a late completion cannot recreate it.

## N. Performance observations

No catalog preload or database architecture was added. Search is bounded to 20 after debounce. Builds retain the chart and use summary responses. Live latency measurement is deferred to browser acceptance.

## O. Prompt-1/2 regression

V3 normalization is unchanged. Raw/Sealed switching, contextual Screens and Composition, Per-Set Chase, movement, and paged constituents remain intact.

## P. Tests/build

- Backend exact/query/API/planner suites: 212 passed.
- Frontend focused query, instance, draft, picker, Screens, and constituent suites: 65 distinct tests passed.
- Next.js production build: passed (existing warnings only).
- Esbuild affected-component compilation and `git diff --check`: passed.
- Three broad component suites hit the pre-existing test-transform issue where `components/AuthContext.js` contains JSX in `.js`; production compilation succeeds and that infrastructure issue is excluded from this prompt.

## Q. Live QA

No authenticated Premium browser session was available. Automated interaction contracts and production build completed; full browser/mobile acceptance remains for Prompt 5.

## R. Deferred items

Persistent saved markets, exact-basket URL persistence, rename, compare-individually, and Graded selection.

## S. Genuine blockers

None for source completion. Live authenticated QA was unavailable.

## T. Prompt-4 readiness

Ready. Prompt 4 can style the mode switch, picker, selected list, edit controls, and unsaved state without changing lifecycle contracts.

## U. Commit SHA

Implementation commit: `9a7a192c`.
