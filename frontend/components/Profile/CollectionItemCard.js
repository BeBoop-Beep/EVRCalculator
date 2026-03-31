/**
 * Reusable card component for collection items, wishlist items, and shelf items.
 * Displays card/product image with metadata and optional value/grade info.
 */
export default function CollectionItemCard({
  item,
  variant = "compact", // compact, detailed, shelf
  onClick = null,
  className = "",
}) {
  const isPlaceholder = !item.imageUrl;

  const renderContent = () => {
    if (variant === "shelf") {
      return (
        <>
          <div className="relative aspect-square overflow-hidden bg-[var(--surface-hover)]">
            {isPlaceholder ? (
              <div className="flex h-full items-center justify-center text-xs text-[var(--text-secondary)]">
                No image
              </div>
            ) : (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={item.imageUrl}
                alt={item.name}
                className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
              />
            )}
          </div>
          <div className="space-y-2 p-3">
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
              {item.productType || "Sealed Product"}
            </p>
            <p className="line-clamp-2 text-sm font-semibold text-[var(--text-primary)]">{item.name}</p>
            {item.quantity && <p className="text-xs text-[var(--text-secondary)]">Qty: {item.quantity}</p>}
            {item.valueLabel && (
              <p className="pt-1 text-sm font-medium text-[var(--text-primary)]">{item.valueLabel}</p>
            )}
          </div>
        </>
      );
    }

    if (variant === "detailed") {
      return (
        <>
          <div className="relative aspect-[16/10] overflow-hidden bg-[var(--surface-hover)]">
            {isPlaceholder ? (
              <div className="flex h-full items-center justify-center text-xs text-[var(--text-secondary)]">
                No image
              </div>
            ) : (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={item.imageUrl}
                alt={item.name}
                className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
              />
            )}
            {item.isFoil && (
              <div className="absolute right-2 top-2 rounded-md bg-amber-500 px-2 py-1 text-[10px] font-bold uppercase text-white">
                Foil
              </div>
            )}
            {item.gradingLabel && (
              <div className="absolute bottom-2 left-2 rounded-md bg-[rgba(0,0,0,0.6)] px-2 py-1 text-[10px] font-semibold text-white">
                {item.gradingLabel}
              </div>
            )}
          </div>
          <div className="space-y-2 p-4">
            <div>
              <p className="truncate text-xs text-[var(--text-secondary)]">{item.set || "Unknown Set"}</p>
              <p className="line-clamp-2 text-sm font-semibold text-[var(--text-primary)]">{item.name}</p>
            </div>
            {item.cardNumber && (
              <p className="text-xs text-[var(--text-secondary)]">#{item.cardNumber}</p>
            )}
            {item.condition && (
              <p className="text-xs font-medium text-[var(--text-secondary)]">Condition: {item.condition}</p>
            )}
            {item.valueLabel && (
              <p className="pt-2 text-sm font-medium text-[var(--text-primary)]">{item.valueLabel}</p>
            )}
          </div>
        </>
      );
    }

    // compact variant (default)
    return (
      <>
        <div className="relative aspect-[16/10] overflow-hidden bg-[var(--surface-hover)]">
          {isPlaceholder ? (
            <div className="flex h-full items-center justify-center text-xs text-[var(--text-secondary)]">
              No image
            </div>
          ) : (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={item.imageUrl}
              alt={item.name}
              className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
            />
          )}
        </div>
        <div className="space-y-1 p-4">
          <p className="truncate text-sm font-semibold text-[var(--text-primary)]">{item.name}</p>
          <p className="text-xs text-[var(--text-secondary)]">{item.context}</p>
          {item.valueLabel && <p className="pt-2 text-sm font-medium text-[var(--text-primary)]">{item.valueLabel}</p>}
        </div>
      </>
    );
  };

  return (
    <article
      className={`group overflow-hidden rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)] ${
        onClick ? "cursor-pointer transition-colors hover:border-[var(--border-prominent)]" : ""
      } ${className}`}
      onClick={onClick}
      role={onClick ? "button" : "article"}
      tabIndex={onClick ? 0 : undefined}
    >
      {renderContent()}
    </article>
  );
}
