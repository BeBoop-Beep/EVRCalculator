"use client";
import Image from "next/image";
import Link from "next/link";
import { useMemo, useState } from "react";
import { resolveLooseBoosterPackArtwork } from "@/lib/pokemon/pokemonBoosterPackAssets.mjs";
import { buildTcgSetHrefFromTarget } from "@/lib/explore/ripStatisticsRouting";
import { SET_PACK_COLUMNS, sortSetPackMetrics, formatSetMetric } from "./setPackMetricsSelector.mjs";
import styles from "./explore.module.css";

export default function SetPackMetrics({ sets, eraFilter }) {
 const [sort,setSort]=useState({key:"modeledReturn",direction:"desc"});
 const filtered=(sets||[]).filter(t=>!eraFilter||String(t.eraName).toLowerCase()===String(eraFilter).toLowerCase());
 const rows=useMemo(()=>sortSetPackMetrics(filtered,sort.key,sort.direction),[filtered,sort]);
 const change=key=>setSort(s=>({key,direction:s.key===key&&s.direction==="desc"?"asc":"desc"}));
 const art=row=>resolveLooseBoosterPackArtwork({setCanonicalKey:row.canonicalKey});
 return <section data-set-pack-metrics><header className="mb-3"><h2 className="text-lg font-semibold">Pack Economics by Set</h2><p className="text-xs text-[var(--text-secondary)]">All eligible modeled sealed products, normalized per pack. Sorting never changes the official Set RIP rank.</p></header>
 <div className={`${styles.surface} hidden overflow-x-auto desk:block`}><table className={styles.table}><thead className={styles.head}><tr><th>Set / pack</th>{SET_PACK_COLUMNS.map(([key,label])=><th key={key}><button onClick={()=>change(key)}>{label} {sort.key===key?(sort.direction==="asc"?"↑":"↓"):null}</button></th>)}</tr></thead><tbody>{rows.map(row=><tr key={row.setId}><th className="text-left"><Link href={buildTcgSetHrefFromTarget(row.raw)} className="flex items-center gap-3">{art(row)?<Image src={art(row).src} width={30} height={42} alt="" className="h-11 w-8 object-contain"/>:null}{row.logo?<Image src={row.logo} width={72} height={30} alt="" className="h-7 w-16 object-contain"/>:null}<span>{row.setName}<small className="block text-[var(--text-secondary)]">Set RIP #{row.canonicalRank || "—"}</small></span></Link></th>{SET_PACK_COLUMNS.map(([key])=><td key={key} className="text-right tabular-nums">{formatSetMetric(key,row[key]) || "—"}</td>)}</tr>)}</tbody></table></div>
 <ul className="space-y-2.5 desk:hidden">{rows.map(row=><li key={row.setId} className={`${styles.surface} rounded-xl p-3.5`}><Link href={buildTcgSetHrefFromTarget(row.raw)} className="flex items-center gap-3">{art(row)?<Image src={art(row).src} width={34} height={48} alt="" className="h-12 w-9 object-contain"/>:null}<div><b>{row.setName}</b><span className="block text-xs text-[var(--text-secondary)]">Set RIP #{row.canonicalRank || "—"}</span></div></Link><dl className="mt-3 grid grid-cols-2 gap-2">{["modeledReturn","typicalOpening","entertainmentCost","typicalRetention"].map(key=><div key={key}><dt className="text-[.65rem] uppercase text-[var(--text-secondary)]">{SET_PACK_COLUMNS.find(c=>c[0]===key)[1]}</dt><dd>{formatSetMetric(key,row[key])||"—"}</dd></div>)}</dl><p className="mt-2 border-t border-[var(--ex-line)] pt-2 text-xs text-[var(--text-secondary)]">Pack {formatSetMetric("packPrice",row.packPrice)||"—"} · Break-even {formatSetMetric("modelBreakEven",row.modelBreakEven)||"—"} · Recover {formatSetMetric("chanceToRecoverCost",row.chanceToRecoverCost)||"—"}</p></li>)}</ul></section>;
}
