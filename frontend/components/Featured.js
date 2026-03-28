export default function Featured({products}) {
  return (
    <section className="relative w-full h-[50vh] overflow-hidden">
      {/* Background Image */}
      <div
        className="absolute inset-0 bg-cover bg-center animate-zoom-in"
        style={{ backgroundImage: "url('/images/shinyFindsLogo.png')" }}
      ></div>

      {/* Overlay */}
      <div className="absolute inset-0 flex items-center justify-center" style={{
  background: 'linear-gradient(to right, rgba(4, 0, 27, 0.17) 0%, rgba(255, 255, 255, 0.19) 50%, rgba(4, 0, 27, 0.17) 100%)'
}}>
       <div className="text-center text-white">
  <h1 
    className="text-5xl font-bold"
    style={{ textShadow: '2px 2px 4px rgba(0, 4, 41, 0.74)' }} 
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
