"use client";

import SegmentedGridControl from "@/components/ui/SegmentedGridControl";

export default function SimulationSectionSelector({ options, selectedValue, onValueChange, className = "" }) {
  const items = (Array.isArray(options) ? options : [])
    .filter(Boolean)
    .map((option) => ({
      value: option.value,
      label: option.shortLabel || option.label,
      ariaLabel: option.label,
      title: option.label,
      disabled: option.disabled,
    }));

  if (items.length === 0) {
    return null;
  }

  return (
    <SegmentedGridControl
      items={items}
      selectedValue={selectedValue}
      onValueChange={onValueChange}
      ariaLabel="Simulation section"
      className={className}
      columnClassName="grid-cols-3 tab:grid-cols-6"
      desktopPill
    />
  );
}
