"use client";

import styles from "@/components/explore/explore.module.css";

// This is the canonical search shape for table/browser toolbars. Reuse it instead of
// reconstructing table search inputs locally. Set Market is the visual authority.
export default function TableSearchInput({
  value,
  onChange,
  placeholder,
  ariaLabel,
  className = "",
  containerClassName = "",
  // Pass-through for a caller's own hook/test attribute (data-*). Deliberately
  // spread on the input LAST but before className, so a caller can label its
  // field without forking the component or reintroducing local dimensions.
  inputProps = {},
}) {
  return (
    <label className={`min-w-0 w-full flex-1 desk:max-w-[16rem] ${containerClassName} ${className}`.trim()}>
      <span className="sr-only">{ariaLabel}</span>
      <input
        {...inputProps}
        type="search"
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        aria-label={ariaLabel}
        className={`${styles.setMarketControl} min-h-11 w-full px-2.5 py-1 text-xs desk:min-h-0 desk:py-1.5`}
      />
    </label>
  );
}
