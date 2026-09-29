"use client";

import TableSearchInput from "@/components/ui/TableSearchInput";

export default function RankingsSearchInput({ value, onChange, entity = "Sets", className = "" }) {
  return <TableSearchInput value={value} onChange={onChange} placeholder={`Search ${entity}…`} ariaLabel={`Search ${entity}`} containerClassName={className} inputProps={{ "data-rankings-search": entity.toLowerCase() }} />;
}
