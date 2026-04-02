"use client";

import { useRouter } from "next/navigation";

import MyCollectionQuickActions from "@/components/Profile/MyCollectionQuickActions";
import RouteTabsNav from "@/components/Profile/RouteTabsNav";

const myCollectionTabs = [
  { label: "Overview", href: "/my-portfolio", exact: true },
  { label: "Collection", href: "/my-portfolio/collection" },
  { label: "Binder", href: "/my-portfolio/binder" },
  { label: "Shelf", href: "/my-portfolio/shelf" },
  { label: "Wishlist", href: "/my-portfolio/wishlist" },
];

export default function MyCollectionLayout({ children }) {
  const router = useRouter();

  const handleAddCard = () => {
    router.push("/cards");
  };

  const handleAddSealedProduct = () => {
    router.push("/products");
  };

  const handleImportCollection = () => {
    router.push("/my-portfolio");
  };

  return (
    <main className="w-full">
      <div className="mx-auto w-full max-w-7xl px-6 py-8">
        <section className="dashboard-container rounded-3xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/70 p-4 sm:p-5">
          <div className="space-y-6">
            <section className="page-hero-panel rounded-2xl px-6 py-8 sm:px-8">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">Private Workspace</p>
                  <h1 className="mt-1 text-[28px] font-bold text-[var(--text-primary)]">My Portfolio</h1>
                  <p className="mt-2 text-sm text-[var(--text-secondary)]">Owner-only tools for building, importing, and managing your collection.</p>
                </div>

                <MyCollectionQuickActions
                  heroCluster
                  onAddCard={handleAddCard}
                  onAddSealedProduct={handleAddSealedProduct}
                  onImportCollection={handleImportCollection}
                />
              </div>
            </section>
            <RouteTabsNav items={myCollectionTabs} ariaLabel="My Portfolio sections" />
            {children}
          </div>
        </section>
      </div>
    </main>
  );
}
