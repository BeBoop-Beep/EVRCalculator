"use client";

import DarkSelect from "@/components/ui/DarkSelect";

function ArrowUpDownIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <path d="M6 16V4m0 0L3.5 6.5M6 4l2.5 2.5M14 4v12m0 0-2.5-2.5M14 16l2.5-2.5" />
    </svg>
  );
}

export default function SortMenuButton(props) {
  return <DarkSelect {...props} className={`flex-none ${props.className || ""}`} triggerVariant="sort" triggerIcon={<ArrowUpDownIcon />} />;
}
