"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import ConfirmModal from "@/components/Profile/ConfirmModal";
import PublicCollectionViewWrapper from "@/components/Profile/PublicCollectionViewWrapper";

function parseCurrencyValue(valueLabel) {
  if (!valueLabel) return 0;
  const numeric = Number(String(valueLabel).replace(/[^\d.-]/g, ""));
  return Number.isFinite(numeric) ? numeric : 0;
}

function buildOwnerCollectionStats(items) {
  const totalValue = items.reduce((sum, item) => sum + parseCurrencyValue(item.valueLabel), 0);
  const investedValue = items.reduce((sum, item) => {
    const parsedCostBasis = Number(item?.cost_basis);
    const currentValue = parseCurrencyValue(item.valueLabel);
    const base = Number.isFinite(parsedCostBasis) && parsedCostBasis > 0
      ? parsedCostBasis
      : currentValue * 0.84;
    return sum + base;
  }, 0);
  const sealedItems = items.filter((item) => item.productType || !item.cardNumber);
  const cardItems = items.filter((item) => item.cardNumber && !item.productType);
  const gradedItems = items.filter((item) => Boolean(item.gradingLabel));

  return {
    totalItems: items.length,
    totalValue: `$${totalValue.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
    investedValue: `$${investedValue.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
    sealedCount: sealedItems.length,
    cardsCount: cardItems.length,
    gradedCount: gradedItems.length,
  };
}

export default function MyCollectionPageClient({
  initialItems = [],
  localNavToolState = null,
}) {
  const router = useRouter();
  const [collectionItems, setCollectionItems] = useState(Array.isArray(initialItems) ? initialItems : []);
  const [pendingItemIds, setPendingItemIds] = useState(new Set());
  const [confirmRemovalItem, setConfirmRemovalItem] = useState(null);

  useEffect(() => {
    setCollectionItems(Array.isArray(initialItems) ? initialItems : []);
  }, [initialItems]);

  const stats = useMemo(() => {
    return buildOwnerCollectionStats(collectionItems);
  }, [collectionItems]);

  const executeHoldingMutation = useCallback(async (item, action) => {
    const itemId = String(item.id);
    setPendingItemIds((prev) => new Set([...prev, itemId]));

    try {
      const res = await fetch("/api/my-collection/holdings/mutate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          holding_type: item.collectible_type,
          holding_id: itemId,
          action,
        }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        console.error("[owner-holdings-mutate] request_failed", err?.message || res.status);
        return;
      }

      // Authoritative refresh: rerun the same server read path used by this page.
      router.refresh();
    } catch (error) {
      console.error("[owner-holdings-mutate] unexpected_error", error);
    } finally {
      setPendingItemIds((prev) => {
        const next = new Set(prev);
        next.delete(itemId);
        return next;
      });
    }
  }, [router]);

  const handleQuantityMutate = useCallback((item, action) => {
    if (action === "decrement" && (item.quantity ?? 1) <= 1) {
      setConfirmRemovalItem(item);
      return;
    }
    executeHoldingMutation(item, action);
  }, [executeHoldingMutation]);

  const handleConfirmRemoval = useCallback(() => {
    if (!confirmRemovalItem) return;
    const item = confirmRemovalItem;
    setConfirmRemovalItem(null);
    executeHoldingMutation(item, "remove");
  }, [confirmRemovalItem, executeHoldingMutation]);

  return (
    <section className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {[
          { label: "Portfolio Value", value: stats.totalValue || "$0.00" },
          { label: "Cards", value: stats.cardsCount || 0 },
          { label: "Sealed", value: stats.sealedCount || 0 },
          { label: "Graded", value: stats.gradedCount || 0 },
        ].map((stat) => (
          <div
            key={stat.label}
            className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-4 text-center"
          >
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">
              {stat.label}
            </p>
            <p className="mt-2 text-2xl font-semibold text-[var(--text-primary)]">
              {typeof stat.value === "number" ? stat.value.toLocaleString() : stat.value}
            </p>
          </div>
        ))}
      </div>

      <PublicCollectionViewWrapper
        mode="owner"
        items={collectionItems}
        stats={stats}
        showPerformanceCard={false}
        localNavToolState={localNavToolState}
        localNavControlsActive
        serverPreparedAt={Date.now()}
        onQuantityMutate={handleQuantityMutate}
        pendingItemIds={pendingItemIds}
      />

      <ConfirmModal
        isOpen={confirmRemovalItem !== null}
        title="Remove item from collection?"
        body={
          confirmRemovalItem
            ? `You only have 1 copy of \"${confirmRemovalItem.name}\". This will remove it entirely.`
            : undefined
        }
        confirmLabel="Remove"
        cancelLabel="Cancel"
        onConfirm={handleConfirmRemoval}
        onCancel={() => setConfirmRemovalItem(null)}
      />
    </section>
  );
}
