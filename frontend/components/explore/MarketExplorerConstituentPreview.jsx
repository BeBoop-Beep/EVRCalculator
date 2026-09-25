"use client";

import { useCallback, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { formatBasketValue } from "@/lib/explore/marketOverviewPresentation.mjs";
import {
  buildConstituentPreviewModel,
  constituentRowName,
  positionConstituentPreview,
  resolveConstituentDetailHref,
  resolveConstituentImage,
} from "@/lib/explore/marketExplorerConstituentPresentation.mjs";

const PREVIEW_SIZE = { width: 232, height: 340 };

// A deliberate neutral placeholder, never a broken-image icon.
function ImagePlaceholder({ className }) {
  return (
    <span data-market-constituent-image-placeholder aria-hidden="true"
      className={`flex items-center justify-center rounded border border-dashed border-[var(--border-subtle)] bg-[var(--surface-page)]/40 text-[9px] text-[var(--text-secondary)] ${className}`}>
      <span>—</span>
    </span>
  );
}

/**
 * The hover/focus preview. Reusable across asset kinds: it renders whatever
 * buildConstituentPreviewModel returns, so a future Graded kind adds a branch in
 * that model and nothing here. Non-interactive (role="tooltip"), fixed-positioned
 * through a portal so table overflow cannot clip it, and never takes focus.
 */
export function ConstituentPreview({ row, asset, position, id }) {
  const model = buildConstituentPreviewModel(row, { asset, formatPrice: formatBasketValue });
  return (
    <div
      id={id}
      role="tooltip"
      data-market-constituent-preview={model.kind}
      data-market-constituent-preview-placement={position.placement}
      className="pointer-events-none fixed z-[90] overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[rgba(2,6,23,0.97)] p-2.5 text-left shadow-[0_14px_32px_rgba(0,0,0,0.45)]"
      style={{ left: position.left, top: position.top, width: position.width, maxHeight: position.maxHeight }}
    >
      {model.image.previewUrl ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={model.image.previewUrl} alt="" data-market-constituent-preview-image className="mx-auto mb-2 h-44 w-full object-contain" />
      ) : <ImagePlaceholder className="mb-2 h-44 w-full" />}
      <p className="text-xs font-semibold text-[var(--text-primary)]">{model.title}</p>
      <dl className="mt-1.5 space-y-0.5 text-[10px]">
        {model.fields.map((field) => (
          <div key={field.label} className="flex justify-between gap-2">
            <dt className="text-[var(--text-secondary)]">{field.label}</dt>
            <dd className="text-right font-medium text-[var(--text-primary)]">{field.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

/**
 * The row thumbnail: fixed size (no layout shift), small image, lazy, object-contain.
 * When the row resolves a detail route the image is a link that opens the detail
 * page in a NEW TAB. Only the image is the link — never the whole row — and its
 * click does not reach the row's own handlers.
 *
 * Desktop: hover opens the preview. Keyboard: focusing the link opens it, blur or
 * Escape closes it, and nothing here takes or traps focus. Touch: no hover; the
 * link opens the detail page directly and every critical field stays in the row.
 */
export default function ConstituentThumbnail({ row, asset, className = "h-10 w-7" }) {
  const image = resolveConstituentImage(row);
  const href = resolveConstituentDetailHref(row);
  const name = constituentRowName(row);
  const [failed, setFailed] = useState(false);
  const [position, setPosition] = useState(null);
  const anchorRef = useRef(null);
  const previewId = useId();

  const open = useCallback(() => {
    const node = anchorRef.current;
    if (!node || typeof window === "undefined") return;
    setPosition(positionConstituentPreview(node.getBoundingClientRect(), PREVIEW_SIZE, { width: window.innerWidth, height: window.innerHeight }));
  }, []);
  const close = useCallback(() => setPosition(null), []);

  const visual = image.hasImage && !failed ? (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={image.thumbUrl} alt="" loading="lazy" decoding="async" onError={() => setFailed(true)}
      data-market-constituent-thumb className={`${className} flex-none rounded object-contain`} />
  ) : <ImagePlaceholder className={`${className} flex-none`} />;

  const previewNode = position && typeof document !== "undefined"
    ? createPortal(<ConstituentPreview row={row} asset={asset} position={position} id={previewId} />, document.body)
    : null;

  if (!href) {
    return (
      <span ref={anchorRef} className="inline-flex flex-none" data-market-constituent-thumb-frame
        onPointerEnter={(event) => { if (event.pointerType === "mouse") open(); }} onPointerLeave={close}>
        {visual}{previewNode}
      </span>
    );
  }
  return (
    <a
      ref={anchorRef}
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      data-market-constituent-link
      aria-label={`Open ${name} in a new tab`}
      aria-describedby={position ? previewId : undefined}
      onClick={(event) => event.stopPropagation()}
      onPointerEnter={(event) => { if (event.pointerType === "mouse") open(); }}
      onPointerLeave={close}
      onFocus={(event) => {
        let keyboard = true;
        try { keyboard = event.currentTarget.matches(":focus-visible"); } catch { /* keep default */ }
        if (keyboard) open();
      }}
      onBlur={close}
      onKeyDown={(event) => { if (event.key === "Escape") close(); }}
      className="inline-flex flex-none rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-300/80"
    >
      {visual}{previewNode}
    </a>
  );
}
