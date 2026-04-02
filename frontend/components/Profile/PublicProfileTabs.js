"use client";

import StandardizedTabsNav from "@/components/Profile/StandardizedTabsNav";

export default function PublicProfileTabs({ items, profileBaseHref }) {
  const tabs = items || [
    { label: "Overview", href: profileBaseHref, exact: true },
    { label: "Collection", href: `${profileBaseHref}/collection` },
    { label: "Binder", href: `${profileBaseHref}/binder` },
    { label: "Shelf", href: `${profileBaseHref}/shelf` },
    { label: "Wishlist", href: `${profileBaseHref}/wishlist` },
    { label: "Activity", href: `${profileBaseHref}/activity` },
  ];

  return (
    <StandardizedTabsNav
      items={tabs}
      ariaLabel="Public profile sections"
      className="mt-4"
    />
  );
}
