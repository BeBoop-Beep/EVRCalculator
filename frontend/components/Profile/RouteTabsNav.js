"use client";

import StandardizedTabsNav from "@/components/Profile/StandardizedTabsNav";

export default function RouteTabsNav({ items, ariaLabel }) {
  return (
    <StandardizedTabsNav
      items={items}
      ariaLabel={ariaLabel}
      className="mt-4"
    />
  );
}
