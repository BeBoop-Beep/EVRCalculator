import LandingHero from "@/components/landing/LandingHero";
import Footer from "@/components/Footer";
import { getLandingHeroData } from "@/lib/landing/landingHeroServer";

export default async function HomePage() {
  const { spotlight, ranked } = await getLandingHeroData();

  return (
    <div>
      <LandingHero spotlight={spotlight} ranked={ranked} />
      <Footer />
    </div>
  );
}
