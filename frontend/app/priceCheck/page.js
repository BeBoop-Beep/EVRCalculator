"use client";
import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import SearchBar from "@/components/Search/SearchBar";
import SearchResults from "@/components/Search/SearchResults";
import PriceChart from "@/components/Search/PriceChart";

export default function PriceChartingPage() {
  const [results, setResults] = useState([]);
  const [chartData, setChartData] = useState([]);
  const searchParams = useSearchParams();
  const queryFromUrl = searchParams.get("query") || "";

  const handleSearch = useCallback(async (query) => {
    if (!query) return;
    try {
      const response = await fetch(`/api/ebaySearch?query=${query}`);
      if (!response.ok) {
        const errorData = await response.json();
        console.log('Backend Error:', errorData); // Log the backend error details
        throw new Error(errorData.error || 'Failed to fetch data');
      }
      const data = await response.json();
      console.log(data); // Log the response data for debugging
      setResults(data.results || []);
      setChartData(data.chartData || []); // Fallback to an empty array if chartData is missing
    } catch (error) {
      console.log('Error fetching search results:', error);
      setResults([]); // Reset results to an empty array on error
      setChartData([]); // Reset chartData to an empty array on error
    }
  }, []);

  useEffect(() => {
    if (queryFromUrl.trim()) {
      handleSearch(queryFromUrl.trim());
    }
  }, [queryFromUrl, handleSearch]);

  return (
    <div className="container mx-auto px-4 py-8">
      <h1 className="text-3xl font-bold text-center mb-8">
        Pokémon TCG Price Tracker
      </h1>
      <SearchBar onSearch={handleSearch} initialQuery={queryFromUrl} />
      <SearchResults results={results} />
      {chartData.length > 0 && <PriceChart data={chartData} />}
    </div>
  );
}
