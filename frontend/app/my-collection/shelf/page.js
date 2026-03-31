import RoutePageShell from "@/components/Profile/RoutePageShell";

export default function MyCollectionShelfPage() {
  return (
    <RoutePageShell
      eyebrow="Manage Shelf"
      title="My Shelf"
      subtitle="Track sealed inventory and display placements."
    >
      <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-5 text-sm text-[var(--text-secondary)]">
        Shelf management workspace placeholder.
      </div>
    </RoutePageShell>
  );
}
