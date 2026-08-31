"use client";

import SegmentedControl from "@/components/ui/SegmentedControl";
import SetPageIcon from "@/components/pokemon/set-page/SetPageIcon";

export default function RichSetSectionTabs({ value, onChange, onOptionIntent, options, className = "", variant = "default", mobileScroll = false, equalWidth = false, mobileFullWidth = false, ariaLabel = "Section view" }) {
  const tabOptions = Array.isArray(options) ? options : [];
  if (tabOptions.length === 0) return null;
  if (variant === "primary") {
    const sharedOptions = tabOptions.map((option) => ({
      ...option,
      onIntent: () => onOptionIntent?.(option.value),
      label: <span className="flex min-w-0 items-center justify-center gap-1.5">
        {option.icon ? <SetPageIcon name={option.icon} className={`h-3.5 w-3.5 flex-none ${option.hideIconOnMobile ? "max-desk:hidden" : ""}`} /> : null}
        <span className="whitespace-nowrap">{option.mobileLabel ? <><span className="max-desk:hidden">{option.label}</span><span className="hidden max-desk:inline">{option.mobileLabel}</span></> : option.label}</span>
      </span>,
    }));
    return <SegmentedControl className={className} options={sharedOptions} value={value} onChange={onChange} ariaLabel={ariaLabel} variant="primary" />;
  }
  if (variant === "secondary") return <SegmentedControl className={className} options={tabOptions} value={value} onChange={onChange} ariaLabel={ariaLabel} mobileScroll={mobileScroll} equalWidth={equalWidth} mobileFullWidth={mobileFullWidth} />;
  return <div className={className}><div className="grid w-full items-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] p-0.5" style={{ gridTemplateColumns: `repeat(${tabOptions.length}, minmax(0, 1fr))` }}>
    {tabOptions.map((option) => { const active = value === option.value; return <button key={option.value} type="button" onClick={() => onChange(option.value)} aria-pressed={active} className={`min-w-0 rounded-md px-1.5 py-2 text-[10px] font-semibold leading-none transition-colors sm:px-3 sm:text-[11px] ${active ? "bg-[var(--brand)] text-white" : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"}`}><span className="block truncate">{option.label}</span></button>; })}
  </div></div>;
}
