import Link from "next/link";
import SectionEmptyState from "@/components/Profile/SectionEmptyState";

function toCountLabel(count) {
  return count === 1 ? "1 item" : `${count} items`;
}

function isMissingValue(value) {
  if (value == null) return true;
  if (typeof value === "string") return value.trim().length === 0;
  return false;
}

function buildPortfolioTasks(collectionItems = []) {
  const cards = collectionItems.filter((item) => item?.collectible_type === "card");
  const sealedProducts = collectionItems.filter((item) => item?.collectible_type === "sealed_product");

  const missingCardPurchase = cards.filter((item) => {
    const value = Number(item?.purchase_price);
    return !Number.isFinite(value) || value <= 0;
  }).length;

  const missingSealedPurchase = sealedProducts.filter((item) => {
    const value = Number(item?.purchase_price);
    return !Number.isFinite(value) || value <= 0;
  }).length;

  const missingCondition = collectionItems.filter((item) => isMissingValue(item?.condition)).length;
  const missingAcquisitionDate = collectionItems.filter((item) => isMissingValue(item?.acquisition_date)).length;
  const missingImages = collectionItems.filter((item) => isMissingValue(item?.imageUrl)).length;
  const missingGrading = cards.filter((item) => isMissingValue(item?.gradingLabel)).length;

  const unpricedAssets = collectionItems.filter((item) => {
    const priced = item?.valueLabel ?? item?.estimated_value;
    return isMissingValue(priced);
  }).length;

  return [
    {
      id: "cards-missing-price",
      title: "Cards missing purchase price",
      detail: `${toCountLabel(missingCardPurchase)} need cost basis for accurate ROI tracking.`,
      count: missingCardPurchase,
      tone: missingCardPurchase > 0 ? "watch" : "ok",
      href: "/my-portfolio/collection?task=missing-card-purchase-price",
      cta: "Review cards",
      category: "data-completion",
    },
    {
      id: "sealed-missing-price",
      title: "Sealed products missing purchase price",
      detail: `${toCountLabel(missingSealedPurchase)} need entry pricing to complete performance analytics.`,
      count: missingSealedPurchase,
      tone: missingSealedPurchase > 0 ? "watch" : "ok",
      href: "/my-portfolio/shelf?task=missing-sealed-purchase-price",
      cta: "Review sealed",
      category: "data-completion",
    },
    {
      id: "missing-condition",
      title: "Assets missing condition",
      detail: `${toCountLabel(missingCondition)} should be normalized for cleaner valuation assumptions.`,
      count: missingCondition,
      tone: missingCondition > 0 ? "watch" : "ok",
      href: "/my-portfolio/collection?task=missing-condition",
      cta: "Add condition",
      category: "data-completion",
    },
    {
      id: "missing-acquisition",
      title: "Assets missing acquisition date",
      detail: `${toCountLabel(missingAcquisitionDate)} are missing timeline data for hold-duration analysis.`,
      count: missingAcquisitionDate,
      tone: missingAcquisitionDate > 0 ? "watch" : "ok",
      href: "/my-portfolio/collection?task=missing-acquisition-date",
      cta: "Add dates",
      category: "data-completion",
    },
    {
      id: "missing-images",
      title: "Assets missing images",
      detail: `${toCountLabel(missingImages)} still need photos for a complete visual catalog.`,
      count: missingImages,
      tone: missingImages > 0 ? "watch" : "ok",
      href: "/my-portfolio/collection?task=missing-images",
      cta: "Upload images",
      category: "data-completion",
    },
    {
      id: "missing-grading",
      title: "Cards missing grading details",
      detail: `${toCountLabel(missingGrading)} have no slab metadata yet.`,
      count: missingGrading,
      tone: missingGrading > 0 ? "watch" : "ok",
      href: "/my-portfolio/binder?task=missing-grading",
      cta: "Update grading",
      category: "data-completion",
    },
    {
      id: "wishlist-below-target",
      title: "Wishlist items below target price",
      detail: "Live wishlist target-price alerts are coming soon. This slot is production-shaped with a safe fallback.",
      count: null,
      tone: "todo",
      href: "/my-portfolio/wishlist",
      cta: "Open wishlist",
      fallbackNote: "TODO: wire wishlist target-price signal from backend pricing service.",
      category: "opportunity",
      signalPending: true,
    },
    {
      id: "unpriced-or-stale",
      title: "Unpriced assets or stale valuation",
      detail: unpricedAssets > 0
        ? `${toCountLabel(unpricedAssets)} currently have no valuation. Staleness detection will be wired next.`
        : "No unpriced assets detected. Staleness detection will be wired next.",
      count: unpricedAssets,
      tone: unpricedAssets > 0 ? "watch" : "todo",
      href: "/my-portfolio/collection?task=unpriced-or-stale",
      cta: "Check valuations",
      fallbackNote: "TODO: add stale-valuation threshold once valuation timestamp is available.",
      category: "system-maintenance",
      signalPending: unpricedAssets === 0,
    },
  ];
}

function normalizeTasks(rawTasks = []) {
  return rawTasks
    .map((task) => ({
      id: task.id,
      title: task.title,
      detail: task.detail,
      count: task.count ?? null,
      tone: task.tone || "watch",
      href: task.href || "/my-portfolio/collection",
      cta: task.cta || "Review",
      fallbackNote: task.fallbackNote || null,
      category: task.category || "data-completion",
      signalPending: Boolean(task.signalPending),
      showWhenZero: Boolean(task.showWhenZero),
    }))
    .filter((task) => task.id && task.title && task.detail);
}

function getRenderableTasks(tasks = []) {
  const withCounts = tasks.filter((task) => typeof task.count === "number" && task.count > 0);
  const pendingSignals = tasks.filter((task) => task.count == null && task.signalPending);

  if (withCounts.length > 0) {
    return [...withCounts, ...pendingSignals].slice(0, 8);
  }

  return tasks.filter((task) => task.showWhenZero || task.signalPending).slice(0, 6);
}

function toneBadgeClass(tone) {
  if (tone === "watch") return "border-amber-300/25 bg-amber-300/10 text-amber-200";
  if (tone === "todo") return "border-sky-300/25 bg-sky-300/10 text-sky-200";
  return "border-emerald-300/25 bg-emerald-300/10 text-emerald-200";
}

function toneLabel(tone) {
  if (tone === "watch") return "Action";
  if (tone === "todo") return "Pending";
  return "Clear";
}

export default function MyCollectionPortfolioTasks({ collectionItems = [], tasks = null }) {
  const sourceTasks = Array.isArray(tasks) ? tasks : buildPortfolioTasks(collectionItems);
  const normalizedTasks = normalizeTasks(sourceTasks);
  const renderableTasks = getRenderableTasks(normalizedTasks);

  return (
    <section className="dashboard-panel rounded-2xl border border-[var(--border-subtle)] p-4 sm:p-5">
      <div className="mb-3">
        <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">Owner Action Center</p>
        <h3 className="mt-1 text-lg font-semibold text-[var(--text-primary)]">Portfolio Tasks</h3>
        <p className="mt-1 text-xs text-[var(--text-secondary)] sm:text-sm">
          Finish setup, clean up missing data, and act on portfolio opportunities.
        </p>
      </div>

      {renderableTasks.length === 0 ? (
        <SectionEmptyState
          title="No outstanding portfolio tasks"
          description="Your portfolio is fully set up. No outstanding tasks right now."
          icon="✅"
        />
      ) : (
        <ul className="space-y-2.5">
          {renderableTasks.map((task) => (
          <li key={task.id}>
            <Link
              href={task.href}
              className="block rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)] px-3 py-3 transition-colors hover:bg-[var(--surface-hover)]"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-medium text-[var(--text-primary)]">{task.title}</p>
                  <p className="mt-1 text-xs text-[var(--text-secondary)]">{task.detail}</p>
                  {task.fallbackNote && (
                    <p className="mt-1 text-[11px] text-[var(--text-secondary)] opacity-80">{task.fallbackNote}</p>
                  )}
                </div>
                <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-semibold ${toneBadgeClass(task.tone)}`}>
                  {toneLabel(task.tone)}
                </span>
              </div>
              <div className="mt-2 flex items-center justify-between gap-3">
                <span className="text-xs font-medium text-[var(--text-secondary)]">
                  {task.count == null ? "Signal pending" : toCountLabel(task.count)}
                </span>
                <span className="text-xs font-semibold text-[var(--text-primary)]">{task.cta}</span>
              </div>
            </Link>
          </li>
          ))}
        </ul>
      )}
    </section>
  );
}
