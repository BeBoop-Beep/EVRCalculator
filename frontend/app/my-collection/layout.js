import RouteTabsNav from "@/components/Profile/RouteTabsNav";

const myCollectionTabs = [
  { label: "Overview", href: "/my-collection" },
  { label: "Collection", href: "/my-collection/collection" },
  { label: "Binder", href: "/my-collection/binder" },
  { label: "Shelf", href: "/my-collection/shelf" },
  { label: "Wishlist", href: "/my-collection/wishlist" },
];

export default function MyCollectionLayout({ children }) {
  return (
    <main className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <div className="dashboard-container space-y-6">
        <section className="page-hero-panel rounded-2xl px-6 py-8 sm:px-8">
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">Private Workspace</p>
          <h1 className="mt-1 text-[28px] font-bold text-[var(--text-primary)]">My Collection</h1>
          <p className="mt-2 text-sm text-[var(--text-secondary)]">Owner-only tools for building, importing, and managing your collection.</p>
          <RouteTabsNav items={myCollectionTabs} ariaLabel="My Collection sections" />
        </section>
        {children}
      </div>
    </main>
  );
}
