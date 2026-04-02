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
import { CARD_SIZING } from "@/config/collectionViewSystem";

export default function CollectionItemCard({
  item,
  variant = "compact", // compact, detailed, shelf
  onClick = null,
  onSetAsSpotlight = null,
  className = "",
}) {
  const isPlaceholder = !item.imageUrl;
  const supportsSpotlightAction = typeof onSetAsSpotlight === "function";
  const interactiveClass = onClick
    ? "cursor-pointer hover:-translate-y-0.5 hover:scale-[1.03] hover:shadow-[0_14px_34px_rgba(15,23,42,0.16)]"
    : "hover:-translate-y-0.5 hover:scale-[1.03] hover:shadow-[0_12px_30px_rgba(15,23,42,0.12)]";

  const renderContent = () => {
    if (variant === "shelf") {
      return (
        <>
          <div className="relative w-full overflow-hidden bg-[var(--surface-hover)]" style={{ aspectRatio: CARD_SIZING.imageAspectRatio }}>
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
          <div className={`relative w-full overflow-hidden bg-[var(--surface-hover)] ${CARD_SIZING.detailedHeight}`} style={{ aspectRatio: CARD_SIZING.imageAspectRatio }}>
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
              <div className="absolute right-2 top-2 rounded-full bg-amber-500 px-2 py-1 text-[10px] font-bold uppercase tracking-wide text-white shadow-sm">
                Foil
              </div>
            )}
            {item.gradingLabel && (
              <div className="absolute bottom-2 left-2 rounded-full bg-[rgba(0,0,0,0.62)] px-2 py-1 text-[10px] font-semibold text-white">
                {item.gradingLabel}
              </div>
            )}
          </div>
          <div className="flex min-h-[152px] flex-col gap-2.5 p-4">
            <div className="space-y-1">
              <p className="truncate text-xs text-[var(--text-secondary)]">
                {item.set || "Unknown Set"}
              </p>
              <p className="line-clamp-2 min-h-[2.5rem] text-sm font-semibold leading-tight text-[var(--text-primary)]">
                {item.name}
              </p>
            </div>
            <div className="mt-auto space-y-1.5 pt-1">
              {item.cardNumber && (
                <p className="text-xs text-[var(--text-secondary)]">#{item.cardNumber}</p>
              )}
              {item.condition && (
                <p className="text-xs font-medium text-[var(--text-secondary)]">
                  Condition: {item.condition}
                </p>
              )}
              {item.valueLabel && (
                <p className="pt-1.5 text-sm font-semibold text-[var(--text-primary)]">
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
        <div className="relative w-full overflow-hidden bg-[var(--surface-hover)]" style={{ aspectRatio: CARD_SIZING.imageAspectRatio }}>
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
      className={`group relative flex h-full flex-col overflow-hidden rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)] transition-all duration-200 ${interactiveClass} ${className}`}
      onClick={onClick}
      role={onClick ? "button" : "article"}
      tabIndex={onClick ? 0 : undefined}
    >
      {supportsSpotlightAction ? (
        <div className="absolute right-2 top-2 z-20" onClick={(event) => event.stopPropagation()}>
          <details className="group/menu relative">
            <summary
              className="list-none cursor-pointer rounded-full border border-[var(--border-subtle)] bg-[rgba(15,23,42,0.72)] px-2 py-1 text-xs font-semibold text-white hover:bg-[rgba(15,23,42,0.9)]"
              aria-label="Asset actions"
              title="Asset actions"
            >
              ...
            </summary>
            <div className="absolute right-0 mt-1 w-40 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-1 shadow-lg">
              <button
                type="button"
                onClick={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  onSetAsSpotlight(item);
                }}
                className="w-full rounded-md px-2 py-1.5 text-left text-xs font-medium text-[var(--text-primary)] hover:bg-[var(--surface-hover)]"
              >
                Set as Spotlight
              </button>
            </div>
          </details>
        </div>
      ) : null}
      {renderContent()}
    </article>
  );
}
