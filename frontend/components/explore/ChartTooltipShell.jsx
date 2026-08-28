"use client";

export default function ChartTooltipShell({ children, className = "", style, ...props }) {
  return (
    <div
      {...props}
      className={[
        "pointer-events-none z-50 min-w-[9rem] max-w-[min(16rem,calc(100vw-1rem))] rounded-lg border border-[var(--border-subtle)] bg-[rgba(2,6,23,0.96)] px-2.5 py-2 text-left shadow-[0_14px_32px_rgba(0,0,0,0.38)]",
        className,
      ].filter(Boolean).join(" ")}
      style={style}
    >
      {children}
    </div>
  );
}
