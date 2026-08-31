import { Suspense } from "react";
import PricingPageClient from "@/components/pricing/PricingPageClient";
export const metadata = { title: "Membership Pricing | inDex", description: "Compare Basic, Index Plus, and Index Premium membership." };
export default function PricingPage() { return <Suspense fallback={<main className="min-h-[60vh]"/>}><PricingPageClient/></Suspense>; }
