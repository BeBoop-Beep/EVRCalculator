import Link from "next/link";

export default function SubscriptionDisclosure({ amountLabel, interval, compact = false }) {
  const cadence = interval === "year" ? "year" : "month";
  return (
    <p className={`${compact ? "mt-3" : "mt-4"} text-xs leading-5 text-[var(--text-secondary)]`}>
      By continuing, you agree to the <Link href="/terms" className="font-semibold underline underline-offset-2">Terms of Service</Link>{" "}
      and acknowledge the <Link href="/privacy" className="font-semibold underline underline-offset-2">Privacy Policy</Link>. Your membership automatically renews at {amountLabel} per {cadence}, plus applicable tax, until canceled. Cancel from Membership &amp; Billing or through Link before the next renewal to avoid future charges. Cancellation normally takes effect at the end of the current paid period and does not automatically generate a prorated refund.
    </p>
  );
}
