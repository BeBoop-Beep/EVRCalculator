// Focus-mode colour helper, kept dependency-free so the shared chart can import it.

/** Desaturate any CSS colour the chart may hold to a mid-tone grey. */
export function toGrayscaleColor(color) {
  const fallback = "rgb(148,163,184)";
  if (typeof color !== "string") return fallback;
  let r; let g; let b;
  const hex = color.trim().match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
  if (hex) {
    const digits = hex[1].length === 3 ? [...hex[1]].map((c) => c + c).join("") : hex[1];
    [r, g, b] = [0, 2, 4].map((i) => parseInt(digits.slice(i, i + 2), 16));
  } else {
    const rgb = color.match(/^rgba?\(\s*(\d+(?:\.\d+)?)[\s,]+(\d+(?:\.\d+)?)[\s,]+(\d+(?:\.\d+)?)/i);
    if (!rgb) return fallback;
    [r, g, b] = [Number(rgb[1]), Number(rgb[2]), Number(rgb[3])];
  }
  const luma = Math.round(0.299 * r + 0.587 * g + 0.114 * b);
  const level = Math.max(90, Math.min(190, luma));
  return `rgb(${level},${level},${level})`;
}

