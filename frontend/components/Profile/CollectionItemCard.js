/**
 * Reusable card component for collection items, wishlist items, and shelf items.
 * Displays card/product image with metadata and optional value/grade info.
 * 
 * Layout improvements:
 * - Uniform card height with flex column structure
 * - Fixed 3:4 aspect ratio for image containers
 * - Consistent content area spacing and alignment
 * - Minimum card height ensures alignment in grids
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
          {/* Image container with fixed 3:4 aspect ratio */}
          <div className="relative w-full overflow-hidden bg-[var(--surface-hover)]" style={{ aspectRatio: "3 / 4" }}>
            {isPlaceholder ? (
              <div className="flex h-full w-full items-center justify-center text-xs text-[var(--text-secondary)]">
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
          {/* Content area with flex column layout */}
          <div className="flex flex-col gap-2 p-3">
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
              {item.productType || "Sealed Product"}
            </p>
            <p className="line-clamp-2 min-h-[2.5rem] text-sm font-semibold leading-tight text-[var(--text-primary)]">
              {item.name}
            </p>
            <div className="mt-auto">
              {item.quantity && (
                <p className="text-xs text-[var(--text-secondary)]">Qty: {item.quantity}</p>
              )}
              {item.valueLabel && (
                <p className="pt-1 text-sm font-medium text-[var(--text-primary)]">
                  {item.valueLabel}
                </p>
              )}
            </div>
          </div>
        </>
      );
    }

    if (variant === "detailed") {
      return (
        <>
          {/* Image container with fixed 3:4 aspect ratio */}
          <div className="relative w-full overflow-hidden bg-[var(--surface-hover)]" style={{ aspectRatio: "3 / 4" }}>
            {isPlaceholder ? (
              <div className="flex h-full w-full items-center justify-center text-xs text-[var(--text-secondary)]">
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
          {/* Content area with flex column layout */}
          <div className="flex flex-col gap-2 p-4">
            <div>
              <p className="truncate text-xs text-[var(--text-secondary)]">
                {item.set || "Unknown Set"}
              </p>
              <p className="line-clamp-2 min-h-[2.5rem] text-sm font-semibold leading-tight text-[var(--text-primary)]">
                {item.name}
              </p>
            </div>
            <div className="mt-auto space-y-1">
              {item.cardNumber && (
                <p className="text-xs text-[var(--text-secondary)]">#{item.cardNumber}</p>
              )}
              {item.condition && (
                <p className="text-xs font-medium text-[var(--text-secondary)]">
                  Condition: {item.condition}
                </p>
              )}
              {item.valueLabel && (
                <p className="pt-1 text-sm font-medium text-[var(--text-primary)]">
                  {item.valueLabel}
                </p>
              )}
            </div>
          </div>
        </>
      );
    }

    // compact variant (default)
    return (
      <>
        {/* Image container with fixed 3:4 aspect ratio */}
        <div className="relative w-full overflow-hidden bg-[var(--surface-hover)]" style={{ aspectRatio: "3 / 4" }}>
          {isPlaceholder ? (
            <div className="flex h-full w-full items-center justify-center text-xs text-[var(--text-secondary)]">
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
        {/* Content area with flex column layout */}
        <div className="flex flex-col gap-1 p-4">
          <p className="line-clamp-2 min-h-[2.5rem] text-sm font-semibold leading-tight text-[var(--text-primary)]">
            {item.name}
          </p>
          <div className="mt-auto">
            <p className="text-xs text-[var(--text-secondary)]">{item.context}</p>
            {item.valueLabel && (
              <p className="pt-2 text-sm font-medium text-[var(--text-primary)]">
                {item.valueLabel}
              </p>
            )}
          </div>
        </div>
      </>
    );
  };

  return (
    <article
      className={`group flex h-full flex-col overflow-hidden rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)] transition-colors ${
        onClick ? "cursor-pointer hover:border-[var(--border-prominent)]" : ""
      } ${className}`}
      onClick={onClick}
      role={onClick ? "button" : "article"}
      tabIndex={onClick ? 0 : undefined}
    >
      {renderContent()}
    </article>
  );
}
