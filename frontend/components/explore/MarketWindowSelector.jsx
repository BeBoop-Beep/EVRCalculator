"use client";


// React is imported explicitly (rather than relying on the bundler's automatic
// JSX runtime) so this control can be rendered directly under `tsx --test`,
// which compiles JSX to React.createElement.
import React from "react";
import TimeRangeSelector from "./TimeRangeSelector";

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
