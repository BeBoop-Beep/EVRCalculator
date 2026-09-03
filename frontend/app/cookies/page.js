import LegalDocumentPage from "@/components/legal/LegalDocumentPage";

export const metadata = {
  title: "Cookie Policy | inDex",
  description: "How inDex uses cookies and similar technologies.",
};

const UPDATED = "September 2, 2026";

export default function CookiesPage() {
  return (
    <LegalDocumentPage
      title="Cookie Policy"
      updated={UPDATED}
      intro="This Cookie Policy explains how inDex uses cookies and similar storage technologies when you use inthedex.io."
    >
      <section>
        <h2>1. What cookies are</h2>
        <p className="mt-3">
          Cookies are small pieces of data stored by a website or browser to remember information about a session or device. Similar technologies can include local storage, session storage, and provider-managed identifiers used for authentication, security, and payment experiences.
        </p>
      </section>

      <section>
        <h2>2. Cookies inDex uses</h2>
        <h3 className="mt-5">Strictly necessary and security technologies</h3>
        <p className="mt-2">
          inDex uses cookies or equivalent session mechanisms that are necessary to authenticate users, preserve a secure signed-in session, complete authentication redirects, prevent abuse, and keep account actions connected to the correct user. Blocking these technologies can prevent account or paid-membership features from working.
        </p>
        <h3 className="mt-5">Preference technologies</h3>
        <p className="mt-2">
          We may use browser or account storage to remember user-selected settings and presentation preferences so you do not need to choose them again on every visit.
        </p>
      </section>

      <section>
        <h2>3. Stripe and Link</h2>
        <p className="mt-3">
          When you enter Stripe Checkout, Link, or Stripe-hosted subscription management, Stripe/Link may use cookies and similar technologies for payment processing, fraud prevention, authentication, transaction support, and remembering customer preferences. Those technologies are controlled by Stripe/Link and are subject to their own privacy and cookie practices.
        </p>
      </section>

      <section>
        <h2>4. Advertising and non-essential tracking</h2>
        <p className="mt-3">
          inDex does not currently operate third-party advertising cookies or use personal information for cross-context behavioral advertising. If we introduce non-essential analytics, advertising, or similar tracking that requires notice or consent, we will update this Policy and provide the controls required by applicable law before using those technologies in that jurisdiction.
        </p>
      </section>

      <section>
        <h2>5. Your controls</h2>
        <p className="mt-3">
          Most browsers let you delete or block cookies and site storage through browser settings. If you block strictly necessary cookies, parts of inDex—especially sign-in, authentication callbacks, account settings, and membership purchasing—may stop working correctly. Provider-managed cookie controls may also be available directly through Stripe, Link, or your browser.
        </p>
      </section>

      <section>
        <h2>6. Changes to this Policy</h2>
        <p className="mt-3">
          We may update this Cookie Policy as our technology or legal obligations change. The current version will be posted here with a revised effective date.
        </p>
      </section>
    </LegalDocumentPage>
  );
}
