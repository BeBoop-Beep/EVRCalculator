import LegalDocumentPage from "@/components/legal/LegalDocumentPage";

export const metadata = {
  title: "Terms of Service | inDex",
  description: "Terms governing use of inDex and paid inDex memberships.",
};

const UPDATED = "September 2, 2026";

export default function TermsPage() {
  return (
    <LegalDocumentPage
      title="Terms of Service"
      updated={UPDATED}
      intro="These Terms govern your access to and use of inDex, including Basic, Index Plus, and Index Premium membership features. By using inDex, creating an account, or purchasing a membership, you agree to these Terms."
    >
      <section>
        <h2>1. About inDex</h2>
        <p className="mt-3">
          inDex is an independent collectible-card analytics and decision-support service. We provide market information, modeled opening outcomes, rankings, estimates, research, and related tools for informational and entertainment purposes.
        </p>
        <p className="mt-3">
          inDex is not affiliated with, endorsed by, sponsored by, or certified by Nintendo, Creatures, GAME FREAK, The Pokémon Company, TCGplayer, grading companies, marketplaces, card manufacturers, or other rights holders referenced through the service. Third-party names and marks belong to their respective owners.
        </p>
      </section>

      <section>
        <h2>2. Eligibility and accounts</h2>
        <ul className="mt-3">
          <li>You must be at least 13 years old to create or use an inDex account.</li>
          <li>If you are under the age of majority where you live, you may use the service only with permission and supervision of a parent or legal guardian.</li>
          <li>You must be legally able to enter into a binding purchase agreement to buy a paid membership.</li>
          <li>You are responsible for maintaining the security of your account and for activity performed through it.</li>
          <li>You must provide accurate account information and keep it reasonably current.</li>
        </ul>
      </section>

      <section>
        <h2>3. Informational service; no financial advice</h2>
        <p className="mt-3">
          Market prices, expected values, pull-rate models, simulations, rankings, probability estimates, Collector Appeal, Financial RIP, Overall RIP, Chase Efficiency, and other inDex outputs are estimates and analytical tools—not guarantees of future results, card values, opening outcomes, liquidity, or resale proceeds.
        </p>
        <p className="mt-3">
          Nothing on inDex is investment, financial, tax, legal, gambling, or professional advice. Collectibles are volatile and may lose value. You are responsible for your own purchase, sale, opening, collecting, and financial decisions.
        </p>
      </section>

      <section>
        <h2>4. Data quality and third-party sources</h2>
        <p className="mt-3">
          inDex may rely on third-party market data, public information, modeled pull rates, historical observations, and other external sources. Data can be incomplete, delayed, stale, inaccurate, unavailable, or changed by the source without notice. We may correct, restate, remove, or republish analytics as source data or methodology changes.
        </p>
      </section>

      <section>
        <h2>5. Membership plans and recurring billing</h2>
        <p className="mt-3">
          inDex offers a free Basic tier and paid Index Plus and Index Premium memberships. The price, billing interval, included features, and any applicable taxes are shown before purchase. There is no free trial unless a future offer expressly states otherwise.
        </p>
        <h3 className="mt-5">Automatic renewal</h3>
        <p className="mt-2">
          Paid monthly memberships automatically renew each month, and paid annual memberships automatically renew each year, until canceled. By purchasing a paid membership, you expressly authorize the recurring charges shown at checkout for the selected billing interval, plus applicable taxes, until cancellation takes effect.
        </p>
        <h3 className="mt-5">Merchant of record and payment administration</h3>
        <p className="mt-2">
          Paid memberships are sold through Stripe Managed Payments. Link/Stripe acts as merchant of record for those transactions and handles payment collection, applicable indirect taxes, transaction-level support, receipts, invoices, subscription notifications, and certain refund administration. The checkout page and receipt identify the merchant of record, and additional Stripe or Link transaction terms may apply.
        </p>
        <h3 className="mt-5">Taxes and currency conversion</h3>
        <p className="mt-2">
          Applicable tax may be added to the listed membership price at checkout. Managed Payments may also present localized payment methods or currency conversion based on the customer&apos;s location. The amount displayed for final confirmation in Checkout is the transaction amount you authorize.
        </p>
      </section>

      <section>
        <h2>6. Upgrades and downgrades</h2>
        <ul className="mt-3">
          <li><strong>Plus to Premium:</strong> an upgrade takes effect immediately after successful payment. Stripe calculates the prorated amount due for the remainder of the current billing period, and inDex shows that amount for confirmation before submitting the change.</li>
          <li><strong>Premium to Plus:</strong> a downgrade is scheduled for the end of the current paid billing period. Premium access remains active through that period, and Plus begins at the next billing boundary unless the scheduled change is canceled beforehand.</li>
          <li>Changing only the billing interval within the same tier may be unavailable unless explicitly offered by inDex.</li>
        </ul>
      </section>

      <section>
        <h2>7. Cancellation</h2>
        <p className="mt-3">
          You may cancel a paid membership through inDex Membership &amp; Billing or the Link/Stripe subscription-management experience made available for your transaction. Ordinary cancellation is scheduled for the end of the current paid billing period, so paid access generally continues until that period expires. Cancel before your next renewal date to avoid the next recurring charge.
        </p>
        <p className="mt-3">
          If applicable law requires a particular cancellation method, reminder, timing, or consumer right, that law controls. We will not require a customer to purchase another product or accept a retention offer in order to cancel.
        </p>
      </section>

      <section>
        <h2>8. Refunds</h2>
        <p className="mt-3">
          Ordinary cancellation does not automatically create a prorated cash refund or credit for unused time in the current billing period. Refund requests may be considered case by case, and refunds will be provided where required by law. Because Link/Stripe is merchant of record, Link/Stripe may also administer or approve transaction refunds under its applicable policies and Managed Payments terms.
        </p>
      </section>

      <section>
        <h2>9. Acceptable use and protection of inDex data</h2>
        <p className="mt-3">You may use inDex for lawful personal or internal business purposes. You may not:</p>
        <ul className="mt-3">
          <li>bypass authentication, plan entitlements, paywalls, rate limits, or other access controls;</li>
          <li>scrape, crawl, harvest, systematically copy, or bulk-extract protected inDex data or analytics without written permission;</li>
          <li>resell, republish, sublicense, or build a competing data product from non-public inDex outputs;</li>
          <li>reverse engineer or interfere with the service except to the extent such restriction is prohibited by applicable law;</li>
          <li>use automated traffic in a manner that degrades the service or circumvents intended product limits;</li>
          <li>attempt unauthorized access to accounts, systems, data, or infrastructure; or</li>
          <li>use inDex for unlawful, fraudulent, deceptive, or abusive activity.</li>
        </ul>
      </section>

      <section>
        <h2>10. Intellectual property</h2>
        <p className="mt-3">
          The inDex software, original analytics, methodologies, visualizations, compilation and presentation of data, branding, text, and other original service content are owned by or licensed to inDex and are protected by applicable intellectual-property laws. These Terms grant you a limited, revocable, non-exclusive, non-transferable right to use the service as intended; they do not transfer ownership of inDex intellectual property or third-party content.
        </p>
      </section>

      <section>
        <h2>11. Service changes, availability, and termination</h2>
        <p className="mt-3">
          We may improve, add, remove, pause, or change features, data sources, methodologies, supported products, or plan packaging. We may suspend or terminate access where reasonably necessary for security, fraud prevention, legal compliance, nonpayment, or material violation of these Terms. We will use reasonable efforts to avoid unnecessary interruption to paid access.
        </p>
      </section>

      <section>
        <h2>12. Disclaimers</h2>
        <p className="mt-3">
          To the maximum extent permitted by law, inDex is provided on an &quot;as is&quot; and &quot;as available&quot; basis. We do not warrant that the service will be uninterrupted, error-free, complete, current, or suitable for a particular collecting, investment, resale, or opening decision. Some jurisdictions do not permit certain warranty exclusions, so portions of this section may not apply to you.
        </p>
      </section>

      <section>
        <h2>13. Limitation of liability</h2>
        <p className="mt-3">
          To the maximum extent permitted by law, inDex will not be liable for indirect, incidental, special, consequential, exemplary, or punitive damages, or for lost profits, lost opportunity, loss in collectible value, loss of data, or trading or purchasing losses arising from use of the service. For claims that cannot lawfully be excluded, inDex&apos;s aggregate liability will not exceed the greater of the amount you paid directly for inDex membership during the 12 months before the event giving rise to the claim or US $100. Nothing in these Terms limits liability that applicable law does not allow us to limit.
        </p>
      </section>

      <section>
        <h2>14. Changes to these Terms</h2>
        <p className="mt-3">
          We may update these Terms to reflect service, legal, security, or business changes. The updated version will be posted here with a new effective date. If a change materially affects an active paid membership, we will provide notice where required by law before the change takes effect. Continued use after an effective update constitutes acceptance where permitted by law.
        </p>
      </section>

      <section>
        <h2>15. General</h2>
        <p className="mt-3">
          These Terms, together with the Privacy Policy and any transaction terms presented at checkout, form the agreement governing your use of inDex. If a provision is unenforceable, the remaining provisions continue in effect. Failure to enforce a provision is not a waiver. Mandatory consumer-protection rights in your jurisdiction are not waived by these Terms.
        </p>
      </section>
    </LegalDocumentPage>
  );
}
