export default function Featured({products}) {
  return (
    <section className="relative w-full h-[52vh] min-h-[380px] overflow-hidden bg-[#020817]">
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(1200px 520px at 50% -12%, rgba(16, 69, 129, 0.34) 0%, rgba(2, 8, 23, 0) 62%), linear-gradient(180deg, #020817 0%, #06122a 55%, #08152f 100%)",
        }}
      />

      {/* Background Image */}
      <div
        className="absolute inset-0 bg-cover bg-center animate-zoom-in opacity-45"
        style={{ backgroundImage: "url('/images/shinyFindsLogo.png')" }}
      ></div>

      {/* Overlay */}
      <div className="absolute inset-0 flex items-center justify-center" style={{
  background: 'linear-gradient(180deg, rgba(2, 8, 23, 0.42) 0%, rgba(2, 8, 23, 0.55) 48%, rgba(2, 8, 23, 0.74) 100%)'
}}>
       <div className="text-center text-white">
  <h1 
    className="text-5xl font-bold"
    style={{ textShadow: '2px 2px 4px rgba(0, 4, 41, 0.8)' }} 
  >
    Welcome to Shiny Finds!
  </h1>
  <p 
    className="text-xl mt-2 font-bold"
    style={{ textShadow: '2px 2px 4px rgb(0, 4, 41)' }} 
  >
    Discover rare collectibles and amazing deals.
  </p>
  <div>
    <a
      href="/products" 
      className="mt-6 inline-block px-8 py-3 bg-yellow-100 text-primary font-semibold rounded-3xl shadow-lg hover:bg-accent transition duration-300"
    >
      Shop
    </a>
  </div>
</div>
      </div>
    </section>
  );
}
