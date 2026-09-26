"use client";

import { FOCUS_TOOL_STATE } from "@/lib/explore/marketExplorerAccess.mjs";

// ---------------------------------------------------------------------------
// FOCUS TOOL CONTROLS -- Demand Pressure and inDex Fair Value.
//
// CONTROLS ONLY. Neither renders a value: a fabricated metric is worse than none.
// State is resolved by marketExplorerAccess.resolveFocusToolStates:
//   locked      entitlement missing  -> badge + upgrade link, control disabled
//   unavailable entitled, no backend authority for THIS market -> disabled + reason
//   available   backend explicitly published data -> live toggle
// ---------------------------------------------------------------------------
const CONTROL = "inline-flex min-h-8 items-center gap-1.5 rounded-md border px-2.5 text-[11px] font-semibold";

function ToolControl({ id, label, tool, badge, pressed, onToggle }) {
  const { state, reason } = tool;
  const available = state === FOCUS_TOOL_STATE.available;
  return (
    <span data-market-explorer-focus-tool={id} data-focus-tool-state={state} className="inline-flex flex-wrap items-center gap-1.5">
      <button
        type="button"
        data-market-explorer-focus-tool-button={id}
        aria-pressed={available ? Boolean(pressed) : undefined}
        aria-disabled={available ? undefined : true}
        disabled={!available}
        title={reason || undefined}
        onClick={() => onToggle?.(id)}
        className={`${CONTROL} ${available && pressed ? "border-sky-300/70 bg-sky-400/[.22] text-sky-50" : "border-sky-300/40 text-sky-100"} disabled:cursor-not-allowed disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-300/80`}
      >
        {label}
        {badge ? <span data-focus-tool-badge className="rounded-full bg-violet-500/25 px-1.5 py-px text-[9px] uppercase tracking-wide text-violet-100">{badge}</span> : null}
      </button>
      {reason ? (
        <span data-focus-tool-reason className="text-[10px] text-[var(--text-secondary)]">
          {reason}
          {state === FOCUS_TOOL_STATE.locked ? <> <a href="/pricing" data-focus-tool-upgrade className="font-semibold text-sky-200 underline">Upgrade</a></> : null}
        </span>
      ) : null}
    </span>
  );
}

/**
 * Builds the `focusTools` seam entries the Chart strip renders.
 * `states` comes from resolveFocusToolStates(plan, focusedKey, backendCapabilities).
 */
export function buildFocusTools({ states, fairValueOn = false, demandPressureOn = false, onToggle }) {
  return [
    {
      id: "demand-pressure",
      render: () => (
        <ToolControl id="demand-pressure" label="Demand Pressure" tool={states.demandPressure}
          badge={states.demandPressure.state === FOCUS_TOOL_STATE.locked ? "Index+" : null}
          pressed={demandPressureOn} onToggle={onToggle} />
      ),
    },
    {
      id: "fair-value",
      render: () => (
        <ToolControl id="fair-value" label="inDex Fair Value" tool={states.fairValue}
          badge={states.fairValue.state === FOCUS_TOOL_STATE.available ? null : "Premium"}
          pressed={fairValueOn} onToggle={onToggle} />
      ),
    },
  ];
}
