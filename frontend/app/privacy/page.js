import LegalDocumentPage from "@/components/legal/LegalDocumentPage";

export const metadata = {
  title: "Privacy Policy | inDex",
  description: "How inDex collects, uses, shares, and protects personal information.",
};

const UPDATED = "September 2, 2026";

export default function PrivacyPage() {
  return (
    <LegalDocumentPage
      title="Privacy Policy"
      updated={UPDATED}
      intro="This Privacy Policy explains how inDex handles personal information when you visit inthedex.io, create an account, use our analytics tools, join a waitlist, or purchase a membership."
    >
      <section>
        <h2>1. Information we collect</h2>
        <h3 className="mt-5">Information you provide</h3>
        <ul className="mt-3">
          <li>Account information such as email address, username, display name, and profile settings.</li>
          <li>Authentication information supplied through supported sign-in methods, including information returned by an identity provider when you choose that provider.</li>
          <li>Membership and billing-related account information such as plan, billing status, Stripe customer/subscription identifiers, and transaction state. inDex does not store your full payment-card number or card security code.</li>
          <li>Waitlist, feedback, support, or other communications you send to us.</li>
          <li>Collection, portfolio, preference, or other user-entered information if you use features that request it.</li>
        </ul>
        <h3 className="mt-5">Information collected automatically</h3>
        <ul className="mt-3">
          <li>Device, browser, IP address, request timestamps, referring page, and basic server/security logs.</li>
          <li>Session and authentication information needed to keep you signed in and protect account access.</li>
          <li>Product usage information needed to operate, troubleshoot, secure, and improve inDex.</li>
        </ul>
      </section>

      <section>
        <h2>2. How we use information</h2>
        <ul className="mt-3">
          <li>Provide, authenticate, personalize, and secure the service.</li>
          <li>Provision Basic, Index Plus, and Index Premium access and reconcile subscription state.</li>
          <li>Process account requests and coordinate payment/subscription administration with Stripe/Link.</li>
          <li>Operate market, simulation, ranking, research, and other product features.</li>
          <li>Send transactional or service communications such as authentication messages, billing notices, security notices, and important product updates.</li>
          <li>Prevent fraud, abuse, scraping, unauthorized access, and other harmful activity.</li>
          <li>Debug errors, monitor reliability, measure product performance, and improve the service.</li>
          <li>Comply with legal obligations and enforce our Terms of Service.</li>
        </ul>
      </section>

      <section>
        <h2>3. Payments and Stripe Managed Payments</h2>
        <p className="mt-3">
          Paid memberships use Stripe Managed Payments. Link/Stripe acts as merchant of record for those transactions and handles payment collection, transaction-level support, applicable indirect taxes, receipts, invoices, and subscription notifications. Payment information you enter at Checkout is provided directly to Stripe/Link rather than stored by inDex.
        </p>
        <p className="mt-3">
          inDex receives the identifiers and status information necessary to associate a Stripe customer and subscription with your inDex account, determine your membership entitlement, and provide billing-management features. Stripe/Link processes information under its own privacy terms and may retain transaction records as required for payment, tax, fraud, dispute, and legal obligations.
        </p>
      </section>

      <section>
        <h2>4. Service providers and disclosures</h2>
        <p className="mt-3">
          We disclose personal information only as reasonably necessary to operate the service, complete transactions, protect inDex and its users, or comply with law. Categories of recipients may include:
        </p>
        <ul className="mt-3">
          <li>cloud hosting and deployment providers;</li>
          <li>database, authentication, and infrastructure providers such as Supabase;</li>
          <li>payment and merchant-of-record providers such as Stripe and Link;</li>
          <li>email and transactional communication providers;</li>
          <li>security, logging, reliability, and fraud-prevention providers; and</li>
          <li>government authorities, courts, or other parties when disclosure is legally required or reasonably necessary to protect rights, safety, or the integrity of the service.</li>
        </ul>
        <p className="mt-3">
          inDex does not currently sell personal information for money and does not currently share personal information for cross-context behavioral advertising. If those practices change, we will update this Policy and provide any legally required choices before the change applies.
        </p>
      </section>

      <section>
        <h2>5. Cookies and similar technologies</h2>
        <p className="mt-3">
          inDex uses essential cookies and similar storage technologies for authentication, security, session continuity, and user preferences. Stripe/Link and other service providers may set their own cookies when you use their services. See our <a href="/cookies">Cookie Policy</a> for more detail.
        </p>
      </section>

      <section>
        <h2>6. Data retention</h2>
        <p className="mt-3">
          We keep personal information for as long as reasonably necessary to provide the service, maintain account and billing records, meet legal or tax obligations, resolve disputes, prevent fraud, enforce agreements, and maintain security. Retention periods vary by data type. We may retain de-identified or aggregated information that no longer identifies you.
        </p>
      </section>

      <section>
        <h2>7. Security</h2>
        <p className="mt-3">
          We use reasonable administrative, technical, and organizational safeguards designed to protect personal information, including access controls and encrypted network connections where appropriate. No online system can guarantee absolute security, and you are responsible for protecting your account credentials and devices.
        </p>
      </section>

      <section>
        <h2>8. Your choices and privacy rights</h2>
        <p className="mt-3">
          Depending on where you live and which privacy laws apply, you may have rights to request access to, correction of, deletion of, or a copy of certain personal information, or to object to or restrict certain processing. You may also have rights concerning the sale or sharing of personal information. inDex does not discriminate against users for exercising legally protected privacy rights.
        </p>
        <p className="mt-3">
          You can update certain account information through the product where available. For other privacy requests, contact us using the address listed at the bottom of this Policy. We may need to verify your identity before completing a request and may retain information where an exception or legal obligation applies.
        </p>
        <p className="mt-3">
          California residents may have rights under California privacy law where that law applies to inDex, including rights to know, correct, delete, and obtain information about certain disclosures. We will honor applicable rights and browser-based opt-out signals where legally required.
        </p>
      </section>

      <section>
        <h2>9. Children&apos;s privacy</h2>
        <p className="mt-3">
          inDex is not directed to children under 13, and we do not knowingly collect personal information from a child under 13 without legally required parental consent. If we learn that an account belongs to a child under 13 and COPPA requires parental consent that we do not have, we will take appropriate steps to delete or restrict the information and account. Parents or guardians who believe a child has provided personal information can contact us.
        </p>
      </section>

      <section>
        <h2>10. International users</h2>
        <p className="mt-3">
          inDex and its service providers may process information in the United States and other countries. Those countries may have privacy laws different from the laws where you live. Where required, we rely on appropriate legal mechanisms for international processing or transfer.
        </p>
      </section>

      <section>
        <h2>11. Third-party sites and services</h2>
        <p className="mt-3">
          inDex may link to third-party websites, marketplaces, identity providers, payment experiences, or other services. Their privacy practices are governed by their own policies, not this Privacy Policy.
        </p>
      </section>

      <section>
        <h2>12. Changes to this Policy</h2>
        <p className="mt-3">
          We may update this Privacy Policy as our service or legal obligations change. We will post the updated Policy with a revised effective date and provide additional notice when required by law.
        </p>
      </section>
    </LegalDocumentPage>
  );
}
