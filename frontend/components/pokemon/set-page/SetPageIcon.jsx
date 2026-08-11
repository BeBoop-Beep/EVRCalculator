"use client";

const paths = {
  calendar: <><path d="M6 2v3M14 2v3M3.5 7.5h13M5 4h10a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z" /></>,
  cards: <><rect x="5" y="3" width="11" height="14" rx="2" /><path d="M5 6H4a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h8" /></>,
  value: <><circle cx="10" cy="10" r="7" /><path d="M12.5 7.5c-.5-.7-1.3-1-2.4-1-1.3 0-2.2.6-2.2 1.6 0 2.4 4.3 1.1 4.3 3.5 0 1-.9 1.8-2.4 1.8-1.1 0-2-.4-2.6-1.2M10 5v10" /></>,
  trophy: <><path d="M6 3h8v3c0 3-1.6 5-4 5S6 9 6 6V3ZM8 11v3M12 11v3M6.5 17h7M8 14h4" /><path d="M6 5H3v1c0 2 1.2 3.5 3.4 3.8M14 5h3v1c0 2-1.2 3.5-3.4 3.8" /></>,
  trend: <><path d="m3 14 4-4 3 3 6-7" /><path d="M12 6h4v4" /></>,
  target: <><circle cx="10" cy="10" r="7" /><circle cx="10" cy="10" r="3" /><path d="m12 8 5-5M14 3h3v3" /></>,
  package: <><path d="m3 6 7-3 7 3-7 3-7-3Z" /><path d="M3 6v8l7 3 7-3V6M10 9v8" /></>,
  shield: <><path d="M10 2.5 16 5v4.5c0 4-2.5 6.6-6 8-3.5-1.4-6-4-6-8V5l6-2.5Z" /><path d="m7.5 11 1.6-1.8 1.5 1.2 2.2-3" /></>,
  star: <path d="m10 2.5 2.2 4.4 4.8.7-3.5 3.4.8 4.8-4.3-2.3-4.3 2.3.8-4.8L3 7.6l4.8-.7L10 2.5Z" />,
  bulb: <><path d="M13.7 12.2A6 6 0 1 0 6.3 12.2C7.3 13 7.5 14 7.5 15h5c0-1 .2-2 1.2-2.8Z" /><path d="M8 18h4M10 1V0M3.5 3.5l-1-1M16.5 3.5l1-1" /></>,
  tag: <><path d="M3 4h6l8 8-5 5-8-8V4Z" /><circle cx="7" cy="8" r="1" /></>,
  diamond: <path d="m10 2 7 6-7 10L3 8l7-6Z" />,
  analysis: <><path d="M3 17h14M5 14V9M10 14V4M15 14v-7" /></>,
};

export default function SetPageIcon({ name, className = "h-4 w-4" }) {
  return <svg aria-hidden="true" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className={className}>{paths[name] || paths.analysis}</svg>;
}
