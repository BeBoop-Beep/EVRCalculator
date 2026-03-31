import RoutePageShell from "@/components/Profile/RoutePageShell";

export default function MyCollectionCardsPage() {
  return (
    <RoutePageShell
      eyebrow="Manage Cards"
      title="My Cards"
      subtitle="Add, edit, import, and organize your singles inventory."
    >
      <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-5 text-sm text-[var(--text-secondary)]">
        Card management workspace placeholder.
      </div>
    </RoutePageShell>
  );
}
