"use client";

import { useEffect, useId, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

const CATEGORY_ORDER = ["Sets", "Eras", "Cards", "Sealed", "Quick Markets"];

export default function SitewideSearchBar({ onSearch, className, inputClassName, buttonClassName, placeholder = "Search" }) {
  const router = useRouter();
  const pathname = usePathname();
  const rootRef = useRef(null);
  const requestRef = useRef(0);
  const listId = useId();
  const [query, setQuery] = useState("");
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState("idle");
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);

  useEffect(() => { setOpen(false); setActiveIndex(-1); }, [pathname]);
  useEffect(() => {
    const close = (event) => { if (!rootRef.current?.contains(event.target)) setOpen(false); };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, []);
  useEffect(() => {
    const needle = query.trim();
    if (needle.length < 2) { setItems([]); setStatus("idle"); setOpen(false); return; }
    const controller = new AbortController();
    const requestId = ++requestRef.current;
    setStatus("loading"); setOpen(true); setActiveIndex(-1);
    const timer = setTimeout(async () => {
      try {
        const response = await fetch(`/api/search?q=${encodeURIComponent(needle)}&limit=20`, { signal: controller.signal });
        const payload = await response.json();
        if (requestId !== requestRef.current) return;
        if (!response.ok) throw new Error(payload?.message || "Search unavailable");
        setItems(Array.isArray(payload?.items) ? payload.items : []); setStatus("success");
      } catch (error) {
        if (error?.name !== "AbortError" && requestId === requestRef.current) { setItems([]); setStatus("error"); }
      }
    }, 275);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [query]);

  const choose = (item) => { setOpen(false); setActiveIndex(-1); router.push(item.href); };
  const submit = () => { const needle = query.trim(); if (needle) { setOpen(false); onSearch(needle); } };
  const grouped = CATEGORY_ORDER.map((category) => [category, items.filter((item) => item.category === category)]).filter(([, rows]) => rows.length);

  return <div ref={rootRef} className={className} data-sitewide-search>
    <input type="search" role="combobox" aria-label="Search Pokémon markets, cards, and sealed products"
      aria-autocomplete="list" aria-expanded={open} aria-controls={open ? listId : undefined}
      aria-activedescendant={activeIndex >= 0 ? `${listId}-option-${activeIndex}` : undefined}
      value={query} onChange={(event) => setQuery(event.target.value)} onFocus={() => { if (query.trim().length >= 2) setOpen(true); }}
      onKeyDown={(event) => {
        if (event.key === "Escape") { event.preventDefault(); setOpen(false); setActiveIndex(-1); }
        else if (event.key === "ArrowDown" && items.length) { event.preventDefault(); setOpen(true); setActiveIndex((index) => (index + 1) % items.length); }
        else if (event.key === "ArrowUp" && items.length) { event.preventDefault(); setOpen(true); setActiveIndex((index) => index <= 0 ? items.length - 1 : index - 1); }
        else if (event.key === "Enter") { event.preventDefault(); activeIndex >= 0 && items[activeIndex] ? choose(items[activeIndex]) : submit(); }
      }}
      placeholder={placeholder} className={inputClassName} />
    <button type="button" onClick={submit} className={buttonClassName} aria-label="Search">
      <svg className="h-[22px] w-[22px]" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
    </button>
    {open ? <div id={listId} role="listbox" aria-label="Search suggestions" className="set-dropdown-glass absolute left-0 right-0 top-full z-[1200] mt-2 max-h-[min(32rem,70vh)] overflow-y-auto rounded-xl p-2 shadow-2xl">
      {status === "loading" ? <p role="status" className="px-3 py-4 text-xs text-[var(--text-secondary)]">Searching…</p> : null}
      {status === "error" ? <p role="alert" className="px-3 py-4 text-xs text-red-300">Search is temporarily unavailable.</p> : null}
      {status === "success" && !items.length ? <p role="status" className="px-3 py-4 text-xs text-[var(--text-secondary)]">No results found.</p> : null}
      {status === "success" ? grouped.map(([category, rows]) => <section key={category} aria-labelledby={`${listId}-${category.replaceAll(" ", "-")}`}>
        <h2 id={`${listId}-${category.replaceAll(" ", "-")}`} className="px-3 pb-1 pt-2 text-[10px] font-bold uppercase tracking-[0.14em] text-[rgb(45,212,191)]">{category}</h2>
        {rows.map((item) => { const index = items.indexOf(item); return <button key={`${item.resultType}:${item.id}`} id={`${listId}-option-${index}`} role="option" aria-selected={index === activeIndex}
          type="button" onMouseEnter={() => setActiveIndex(index)} onClick={() => choose(item)}
          className={`block min-h-11 w-full rounded-lg px-3 py-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(45,212,191,0.75)] ${index === activeIndex ? "bg-[rgba(45,212,191,0.12)]" : "hover:bg-[var(--surface-hover)]"}`}>
          <span className="block truncate text-sm font-medium text-[var(--text-primary)]">{item.label}</span>
          {item.secondaryLabel ? <span className="block truncate text-[11px] text-[var(--text-secondary)]">{item.secondaryLabel}</span> : null}
        </button>; })}
      </section>) : null}
    </div> : null}
  </div>;
}
