import PublicOverviewSection from "@/components/Profile/PublicOverviewSection";

export default function PublicFeaturedItemsSection({ items = [] }) {
  return (
    <PublicOverviewSection title="Featured Items" subtitle="Curated showcase picks from this collector.">
      {items.length === 0 ? (
        <EmptyPanel message="No featured items yet." />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {items.map((item) => (
            <article
              key={item.id}
              className="group overflow-hidden rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]"
            >
              <div className="relative aspect-[16/10] overflow-hidden bg-[var(--surface-hover)]">
                {item.imageUrl ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={item.imageUrl}
                    alt={item.name}
                    className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
                  />
                ) : (
                  <div className="flex h-full items-center justify-center text-xs text-[var(--text-secondary)]">
                    No image
                  </div>
                )}
              </div>

              <div className="space-y-1 p-4">
                <p className="truncate text-sm font-semibold text-[var(--text-primary)]">{item.name}</p>
                <p className="text-xs text-[var(--text-secondary)]">{item.context}</p>
                <p className="pt-2 text-sm font-medium text-[var(--text-primary)]">{item.valueLabel}</p>
              </div>
            </article>
          ))}
        </div>
      )}
    </PublicOverviewSection>
  );
}

function EmptyPanel({ message }) {
  return (
    <div className="rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--surface-page)] p-10 text-center text-sm text-[var(--text-secondary)]">
      {message}
    </div>
  );
}
