/**
 * Loading state for collection sections
 * Displays skeleton loaders for grid/list layout
 */
export default function SectionLoadingState({ variant = "grid" }) {
  const itemCount = 12;
  const items = Array.from({ length: itemCount });

  if (variant === "list") {
    return (
      <div className="space-y-3">
        {items.map((_, i) => (
          <div
            key={i}
            className="h-16 animate-pulse rounded-lg bg-[var(--surface-hover)]"
          />
        ))}
      </div>
    );
  }

  // Grid variant
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {items.map((_, i) => (
        <div
          key={i}
          className="animate-pulse rounded-lg bg-[var(--surface-hover)]"
          style={{ aspectRatio: "10/12" }}
        />
      ))}
    </div>
  );
}
