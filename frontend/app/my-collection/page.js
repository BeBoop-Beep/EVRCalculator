import RoutePageShell from "@/components/Profile/RoutePageShell";

export default function MyCollectionOverviewPage() {
  return (
    <RoutePageShell
      eyebrow="Workspace"
      title="Collection Overview"
      subtitle="Track your private management flow across cards, binder, shelf, and wishlist."
    >
      <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-5 text-sm text-[var(--text-secondary)]">
        This is your private command center. Add/import/edit features live in this route group.
      </div>
    </RoutePageShell>
  );
}
