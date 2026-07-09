"use client";

// Priority 4: source/reference details. The backend contract's `sources` and
// `assumptions` fields (get_pokemon_set_pull_rates_snapshot_payload) are
// always empty today — this renders an honest "not yet available" note
// rather than inventing placeholder data. Swap this for real content once
// the backend contract fills those fields in.
export default function SourceReferenceSection() {
  return (
    <p className="rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--surface-page)]/30 px-4 py-3 text-xs text-[var(--text-secondary)]">
      Source references for these modeled odds aren&apos;t published yet.
    </p>
  );
}
