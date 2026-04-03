"use client";

import StandardizedTabsNav from "@/components/Profile/StandardizedTabsNav";

export default function PublicProfileTabs({ items, profileBaseHref }) {
  const tabs = items || [
    { label: "Overview", href: profileBaseHref, exact: true },
    { label: "Wishlist", href: `${profileBaseHref}/wishlist` },
    { label: "Activity", href: `${profileBaseHref}/activity` },
  ];

  return (
    <StandardizedTabsNav
      items={tabs}
      ariaLabel="Public profile sections"
      className="mt-6"
    />
  );
}
