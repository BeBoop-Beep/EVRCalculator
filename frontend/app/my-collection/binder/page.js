import RoutePageShell from "@/components/Profile/RoutePageShell";

export default function MyCollectionBinderPage() {
  return (
    <RoutePageShell
      eyebrow="Manage Binder"
      title="My Binder"
      subtitle="Build and rearrange binder pages privately."
    >
      <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-5 text-sm text-[var(--text-secondary)]">
        Binder management workspace placeholder.
      </div>
    </RoutePageShell>
  );
}
