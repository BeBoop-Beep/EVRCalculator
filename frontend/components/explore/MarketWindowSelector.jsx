"use client";

import TimeRangeSelector from "@/components/explore/TimeRangeSelector";

export default function MarketWindowSelector({ windows, value, onChange, fullWidth = false, className = "", ariaDescription }) {
  const windowOptions = Array.isArray(windows) ? windows.filter(Boolean) : [];
  if (windowOptions.length <= 1) {
    return null;
  }

  return (
    <TimeRangeSelector
      supportedValues={windowOptions.map((entry) => entry.key)}
      selectedValue={value}
      onValueChange={onChange}
      ariaLabel="Time range"
      fullWidth={fullWidth}
      className={className}
      ariaDescription={ariaDescription}
    />
  );
}
