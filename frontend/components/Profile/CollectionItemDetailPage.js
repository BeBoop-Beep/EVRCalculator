import Link from "next/link";
import RouteTabsNav from "@/components/Profile/RouteTabsNav";

export default function CollectionItemDetailPage({
  mode = "public",
  entry,
  ownerLabel,
  backHref,
  tabs = [],
  activeTab = "overview",
  defaultTab = "overview",
  baseDetailHref,
}) {
  const safeItem = entry || {};
  const isPrivateMode = mode === "private";
  const title = safeItem.name || `Entry ${safeItem.id || ""}`;
  const subtitle = isPrivateMode
    ? "Owner view with collection management controls."
    : `Read-only public showcase item from ${ownerLabel || "this collector"}.`;
  const tabItems = tabs.map((tab) => ({
    label: tab.label,
    href: tab.id === defaultTab ? baseDetailHref : `${baseDetailHref}/${tab.id}`,
    exact: tab.id === defaultTab,
  }));

  return (
    <section className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">
            {isPrivateMode ? "My Collection Item" : "Public Collection Item"}
          </p>
          <h1 className="mt-1 text-2xl font-bold text-[var(--text-primary)]">{title || "Collection Item"}</h1>
          {subtitle ? <p className="mt-1 text-sm text-[var(--text-secondary)]">{subtitle}</p> : null}
        </div>

        <div className="flex items-center gap-2">
          {isPrivateMode ? (
            <>
              <button className="inline-flex items-center rounded-lg border border-[var(--border-subtle)] px-3 py-2 text-sm font-medium text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-hover)]">
                Edit
              </button>
              <button className="inline-flex items-center rounded-lg border border-[var(--border-subtle)] px-3 py-2 text-sm font-medium text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-hover)]">
                Manage
              </button>
              <button className="inline-flex items-center rounded-lg border border-[var(--border-subtle)] px-3 py-2 text-sm font-medium text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-hover)]">
                Spotlight
              </button>
            </>
          ) : null}

          <Link
            href={backHref}
            className="inline-flex items-center rounded-lg border border-[var(--border-subtle)] px-3 py-2 text-sm font-medium text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-hover)]"
          >
            Back to Collection
          </Link>
        </div>
      </div>

      <RouteTabsNav ariaLabel="Collection detail sections" items={tabItems} />

      <div className="grid gap-6 rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-page)] p-5 sm:grid-cols-[220px_minmax(0,1fr)]">
        <div className="overflow-hidden rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-hover)]" style={{ aspectRatio: "3 / 4" }}>
          {safeItem.imageUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={safeItem.imageUrl} alt={safeItem.name || "Collection item"} className="h-full w-full object-cover" />
          ) : (
            <div className="flex h-full w-full items-center justify-center text-sm text-[var(--text-secondary)]">No image</div>
          )}
        </div>

        <dl className="grid gap-4 sm:grid-cols-2">
          <DetailField label="Name" value={safeItem.name} />
          <DetailField label="Set" value={safeItem.set} />
          <DetailField label="Card Number" value={safeItem.cardNumber} />
          <DetailField label="Product Type" value={safeItem.productType} />
          <DetailField label="Condition" value={safeItem.condition} />
          <DetailField label="Value" value={safeItem.valueLabel} />
          <DetailField label="Rarity" value={safeItem.rarity} />
          <DetailField label="Foil" value={safeItem.isFoil ? "Yes" : "No"} />
        </dl>
      </div>

      <section className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-page)] p-5">
        <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Active Section</p>
        <h2 className="mt-1 text-lg font-semibold text-[var(--text-primary)] capitalize">{activeTab}</h2>
        <p className="mt-2 text-sm text-[var(--text-secondary)]">
          Shared subsection content for {activeTab}. This panel stays structurally consistent across public and private modes.
        </p>
      </section>
    </section>
  );
}

function DetailField({ label, value }) {
  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-3">
      <dt className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">{label}</dt>
      <dd className="mt-1 text-sm font-medium text-[var(--text-primary)]">{value || "-"}</dd>
    </div>
  );
}
