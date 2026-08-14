export const ARTICLE_PATHS = Object.freeze({
  rip: "/Articles/how-rip-score-works",
  simulation: "/Articles/how-we-simulated-one-million-pokemon-pack-openings",
  validation: "/Articles/how-we-validated-our-pokemon-pack-simulation-using-expected-value",
  ev: "/Articles/why-expected-value-alone-isnt-enough",
  financial: "/Articles/how-financial-rip-works",
  collector: "/Articles/how-collector-appeal-works",
});

export const ARTICLES = Object.freeze([
  { key: "rip", category: "Methodology", title: "How the RIP Score Works", description: "Why Expected Value was not enough, and how inDex compares the full opening experience.", media: { src: "/images/pokemon/booster-packs/perfectOrder.webp", alt: "Perfect Order booster pack", motif: "scores" } },
  { key: "simulation", category: "Methodology", title: "How We Simulated One Million Pokémon Pack Openings", description: "How one modeled pack becomes a distribution of normal outcomes, strong pulls, and jackpots.", media: { src: "/images/pokemon/booster-packs/megaEvolution.webp", alt: "Mega Evolution booster pack", motif: "distribution" } },
  { key: "validation", category: "Methodology", title: "How We Validated Our Pokémon Pack Simulation Using Expected Value", description: "The mathematical cross-check that tells me whether the simulator is behaving as intended.", media: { src: "/images/pokemon/booster-packs/whiteFlare.webp", alt: "White Flare booster pack", motif: "ev" } },
  { key: "financial", category: "Methodology", title: "How Financial RIP Measures the Economics of Opening Pokémon Packs", description: "Why wins, normal losses, realistic upside, and jackpots belong in the same financial picture.", media: { src: "/images/pokemon/booster-packs/paldeanFates.webp", alt: "Paldean Fates booster pack", motif: "financial" } },
  { key: "collector", category: "Methodology", title: "How Collector Appeal Measures What Collectors Actually Want", description: "A price-independent look at desirable Pokémon and how often a pack can deliver them.", media: { src: "https://images.pokemontcg.io/sv3pt5/149_hires.png", alt: "Dragonite card from Scarlet and Violet 151", motif: "collector" } },
  { key: "ev", category: "Analysis & Guides", title: "Why Expected Value Alone Doesn't Tell You Which Pokémon Set Is Best to Open", description: "Two packs can share the same average while feeling completely different to open.", media: { src: "/images/pokemon/booster-packs/prismaticEvolutions.webp", alt: "Prismatic Evolutions booster pack", motif: "contrast" } },
].map(article => ({ ...article, href: ARTICLE_PATHS[article.key] })));

export const related = (...keys) => keys.map(key => { const article = ARTICLES.find(item => item.key === key); return { href: article.href, title: article.title }; });
