import Image from "next/image";

export default function SearchResults({ results }) {
  if (!results || results.length === 0) {
    return (
      <div className="text-center text-[var(--text-secondary)]">
        No results found. Try another search!
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
      {results.map((result, index) => (
        <div key={index} className="bg-[var(--surface-panel)] p-4 rounded-lg border border-[var(--border-subtle)]">
          <Image
            unoptimized
            src={result.image}
            alt={result.title}
            width={800}
            height={480}
            className="w-full h-48 object-cover rounded-lg"
          />
          <h3 className="text-lg font-semibold mt-2">{result.title}</h3>
          <p className="text-[var(--text-secondary)]">\${result.price}</p>
          <p className="text-sm text-[var(--text-secondary)]">{result.platform}</p>
        </div>
      ))}
    </div>
  );
}