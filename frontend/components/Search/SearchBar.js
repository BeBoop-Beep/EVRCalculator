import { useState } from "react";

export default function SearchBar({ onSearch }) {
  const [query, setQuery] = useState("");

  const handleSearch = () => {
    onSearch(query);
  };

  return (
    <div className="flex justify-center my-8">
      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search for a Pokémon TCG product..."
        className="w-1/2 px-4 py-2 border rounded-l-lg focus:outline-none"
      />
      <button
        onClick={handleSearch}
        className="bg-black text-white px-6 py-2 rounded-r-lg hover:bg-gray-800 transition-colors"
      >
        Search
      </button>
    </div>
  );
}