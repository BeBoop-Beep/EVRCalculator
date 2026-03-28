export default function SearchResults({ results }) {
  if (!results || results.length === 0) {
    return (
      <div className="text-center text-gray-500">
        No results found. Try another search!
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
      {results.map((result, index) => (
        <div key={index} className="bg-white p-4 rounded-lg shadow-lg">
          <img
            src={result.image}
            alt={result.title}
            className="w-full h-48 object-cover rounded-lg"
          />
          <h3 className="text-lg font-semibold mt-2">{result.title}</h3>
          <p className="text-gray-600">${result.price}</p>
          <p className="text-sm text-gray-500">{result.platform}</p>
        </div>
      ))}
    </div>
  );
}