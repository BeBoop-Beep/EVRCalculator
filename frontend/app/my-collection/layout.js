import PublicProfileLocalScaffold from "@/components/Profile/PublicProfileLocalScaffold";

const ownerSectionItems = [
  { label: "Collection", href: "/my-collection/collection", exact: true },
  { label: "Cards", href: "/my-collection/cards" },
  { label: "Products", href: "/my-collection/products" },
  { label: "Wishlist", href: "/my-collection/wishlist" },
];

const ownerMobileNavItems = [
  {
    label: "Collection",
    href: "/my-collection/collection",
    exact: true,
    icon: (
      <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.85" strokeLinecap="round" strokeLinejoin="round">
        <rect x="4.25" y="4" width="10.5" height="14" rx="2" />
        <rect x="9.25" y="6" width="10.5" height="14" rx="2" />
      </svg>
    ),
  },
  {
    label: "Cards",
    href: "/my-collection/cards",
    icon: (
      <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.85" strokeLinecap="round" strokeLinejoin="round">
        <rect x="5" y="4.5" width="14" height="15" rx="2" />
        <path d="M8.5 8.2h7" />
        <path d="M8.5 12h7" />
        <path d="M8.5 15.8h4.5" />
      </svg>
    ),
  },
  {
    label: "Products",
    href: "/my-collection/products",
    icon: (
      <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.85" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4 8.2 12 4l8 4.2" />
        <path d="M4 8.2V16l8 4 8-4V8.2" />
        <path d="M12 12v8" />
      </svg>
    ),
  },
  {
    label: "Wishlist",
    href: "/my-collection/wishlist",
    icon: (
      <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.85" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 19.3s-6-3.6-7.9-6.9a4.7 4.7 0 0 1 7.9-4.8 4.7 4.7 0 0 1 7.9 4.8c-1.9 3.3-7.9 6.9-7.9 6.9Z" />
      </svg>
    ),
  },
];

export default function MyCollectionLayout({ children }) {
  return (
    <main className="w-full pb-8 pt-4 lg:py-8">
      <PublicProfileLocalScaffold
        profileBaseHref="/my-collection"
        mode="owner"
        sectionItems={ownerSectionItems}
        mobileNavItems={ownerMobileNavItems}
      >
        {children}
      </PublicProfileLocalScaffold>
    </main>
  );
}
