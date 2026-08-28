import { POSITIVE_VALUE_COLOR } from "../../lib/explore/interpretationTone";

export const PRIMARY_LINE_COLOR = POSITIVE_VALUE_COLOR;
export const PRIMARY_GLOW_OPACITY = 0.16;
export const AREA_GRADIENT_TOP_OPACITY = 0.2;
export const AREA_GRADIENT_BOTTOM_OPACITY = 0;
export const GRID_STROKE = "var(--border-subtle)";
export const REFERENCE_STROKE = "rgba(255,255,255,0.3)";
export const ACTIVE_DOT_STYLE = Object.freeze({
  r: 4,
  fill: PRIMARY_LINE_COLOR,
  stroke: "var(--surface-page)",
  strokeWidth: 2,
});
