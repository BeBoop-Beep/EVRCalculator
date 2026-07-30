"use client";

// Below 1200px both time-series charts carry only their first and last date on
// the x-axis. Recharts centres every tick label on its tick position, so at
// index 0 the label straddles x=0 and at the last index it straddles the right
// edge — and an <svg> clips at its own viewport, so roughly half of each date
// was being cut off. The plot margins alone cannot fix this: widening them
// enough to fit half a date label would hand back the page width the mobile
// axis pass was built to reclaim.
//
// This renders the same tick text Recharts would, with the two edge labels
// anchored inward instead of centred: the first reads from the left edge, the
// last ends at the right edge, and anything between stays centred. Nothing
// about the scale, the tick set or the tooltip changes — only where the glyphs
// sit relative to their tick.
export default function ChartEdgeDateTick({
  x,
  y,
  payload,
  ticks,
  formatter,
  fill = "var(--text-secondary)",
  fontSize = 11,
  dy = 12,
}) {
  const value = payload?.value;
  if (value === undefined || value === null) {
    return null;
  }

  const edgeTicks = Array.isArray(ticks) ? ticks : [];
  const isFirst = edgeTicks.length > 0 && value === edgeTicks[0];
  const isLast = edgeTicks.length > 1 && value === edgeTicks[edgeTicks.length - 1];
  // A single-tick series (first and last coincide) reads from the left edge
  // rather than centred on x=0, which would clip exactly as before.
  const textAnchor = isFirst ? "start" : isLast ? "end" : "middle";

  const label = typeof formatter === "function" ? formatter(value) : value;
  if (label === "" || label === null || label === undefined) {
    return null;
  }

  return (
    <text x={x} y={y} dy={dy} textAnchor={textAnchor} fill={fill} fontSize={fontSize} className="recharts-cartesian-axis-tick-value">
      {label}
    </text>
  );
}
