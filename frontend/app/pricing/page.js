import Link from "next/link";
import { Suspense } from "react";
import PricingPageClient from "@/components/pricing/PricingPageClient";

export const metadata = {
  title: "Membership Pricing | inDex",
  description: "Compare Basic, Index Plus, and Index Premium membership.",
};

export default function PricingPage() {
  return (
    <>
      <Suspense fallback={<main className="min-h-[60vh]" />}>
        <PricingPageClient />
      </Suspense>
      <section className="mx-auto -mt-4 mb-12 w-full max-w-5xl px-4 text-center text-xs leading-5 text-[var(--text-secondary)] sm:px-6">
        <p>
          Paid memberships automatically renew at the selected displayed monthly or annual price, plus applicable tax, until canceled. Cancel before the next renewal through Membership &amp; Billing or Link to avoid future charges. Ordinary cancellation normally takes effect at the end of the current paid period and does not automatically create a prorated refund.
        </p>
        <p className="mt-2">
          By purchasing a paid membership, you agree to the{" "}
          <Link href="/terms" className="font-semibold underline underline-offset-2">
            Terms of Service
          </Link>{" "}
          and acknowledge the{" "}
          <Link href="/privacy" className="font-semibold underline underline-offset-2">
            Privacy Policy
          </Link>.
        </p>
      </section>
    </>
  );
}
