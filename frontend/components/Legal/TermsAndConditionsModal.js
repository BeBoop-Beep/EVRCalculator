"use client";

import { useState, useRef, useEffect } from "react";

const TermsModal = ({ isOpen, onClose, onAgree }) => {
  const [isScrolledToBottom, setIsScrolledToBottom] = useState(false);
  const [lastUpdated, setLastUpdated] = useState("");
  const modalContentRef = useRef(null);

  // Set the "Last Updated" date on component mount
  useEffect(() => {
    setLastUpdated(new Date().toLocaleDateString());
  }, []);

  // Handle scroll event
  const handleScroll = () => {
    const { scrollTop, scrollHeight, clientHeight } = modalContentRef.current;
    if (scrollTop + clientHeight >= scrollHeight - 10) {
      // Allow a small margin of error
      setIsScrolledToBottom(true);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white p-6 rounded-lg shadow-lg max-w-2xl w-full max-h-[80vh] overflow-y-auto">
        <h1 className="text-2xl font-bold mb-4">Terms and Conditions</h1>
        <p>
          <strong>Last Updated:</strong> {lastUpdated}
        </p>
        <div
          ref={modalContentRef}
          onScroll={handleScroll}
          className="overflow-y-auto max-h-[60vh] pr-4"
        >
          <h2 className="text-xl font-bold mt-4">1. Introduction</h2>
          <p>
            Welcome to <strong>Shiny Finds LLC</strong>, operating as{" "}
            <strong>Shiny Finds</strong> (&quot;we,&quot; &quot;our,&quot;
            &quot;us&quot;). These Terms and Conditions govern your use of our
            website and services. By accessing or using our website, you agree
            to comply with these terms. If you do not agree, please do not use
            our website.
          </p>

          <h2 className="text-xl font-bold mt-4">2. Eligibility</h2>
          <p>
            By using this website, you confirm that you are at least 18 years
            old or the legal age of majority in your jurisdiction. If you are
            under 18, you may only use this website with the consent of a parent
            or guardian.
          </p>

          <h2 className="text-xl font-bold mt-4">3. User Accounts</h2>
          <p>
            To access certain features, you may need to create an account. You
            are responsible for maintaining the confidentiality of your account
            credentials and for all activities that occur under your account.
            Notify us immediately of any unauthorized use of your account.
          </p>

          <h2 className="text-xl font-bold mt-4">4. Privacy Policy</h2>
          <p>
            Your use of our website is also governed by our{" "}
            <a href="/privacy-policy" className="text-primary hover:underline">
              Privacy Policy
            </a>
            , which explains how we collect, use, and protect your personal
            information.
          </p>

          <h2 className="text-xl font-bold mt-4">5. Intellectual Property</h2>
          <p>
            All content on this website, including logos, images, and text, is
            the property of Shiny Finds LLC and is protected by copyright and
            other intellectual property laws. You may not use, reproduce, or
            distribute any content without our prior written consent.
          </p>

          <h2 className="text-xl font-bold mt-4">6. Prohibited Activities</h2>
          <p>
            You agree not to engage in any unlawful or prohibited activities,
            including but not limited to:
          </p>
          <ul className="list-disc pl-6">
            <li>Fraud, hacking, or spamming.</li>
            <li>Infringing on the intellectual property rights of others.</li>
            <li>
              Using automated tools to scrape or extract data from the website.
            </li>
            <li>Posting harmful, defamatory, or illegal content.</li>
          </ul>

          <h2 className="text-xl font-bold mt-4">7. Purchases and Payments</h2>
          <p>
            All purchases are subject to availability and confirmation of the
            order. We accept the following payment methods: Apple Pay, Google
            Pay, credit/debit cards (processed via Stripe), and PayPal. Shipping
            costs and taxes will be added to the total price. For details on
            refunds, returns, and cancellations, please refer to our{" "}
            <a href="/refund-policy" className="text-primary hover:underline">
              Refund Policy
            </a>
            .
          </p>

          <h2 className="text-xl font-bold mt-4">
            8. Authenticity and Collectibles
          </h2>
          <p>
            We guarantee the authenticity of all collectibles sold on our
            website. However, due to the nature of collectibles, we do not
            accept returns or cancellations for items that are accurately
            described and shown in the listing. If you believe an item is not
            authentic, contact us within <strong>14 days</strong> of receipt for
            an investigation. Please provide the following:
          </p>
          <ul className="list-disc pl-6">
            <li>Photos of the item in question.</li>
            <li>A detailed explanation of your concerns.</li>
            <li>Any supporting documentation (e.g., expert opinions).</li>
          </ul>
          <p>
            We will review your claim and, if necessary, consult with
            third-party experts to verify the item&apos;s authenticity. If the
            item is found to be inauthentic, we will provide a full refund or
            replacement at no additional cost.
          </p>

          <h2 className="text-xl font-bold mt-4">9. Limitation of Liability</h2>
          <p>
            Shiny Finds LLC is not liable for any damages arising from your use
            of this website, including but not limited to:
          </p>
          <ul className="list-disc pl-6">
            <li>Indirect, incidental, or consequential damages.</li>
            <li>Errors or inaccuracies in product descriptions or pricing.</li>
            <li>Website downtime or technical issues.</li>
          </ul>
          <p>
            Our total liability to you for any claim shall not exceed the amount
            you paid for the product or service in question.
          </p>

          <h2 className="text-xl font-bold mt-4">10. Indemnification</h2>
          <p>
            You agree to indemnify and hold Shiny Finds LLC harmless from any
            claims, damages, or losses arising from your use of the website,
            violation of these terms, or infringement of any third-party rights.
          </p>

          <h2 className="text-xl font-bold mt-4">11. Dispute Resolution</h2>
          <p>
            Any disputes arising from these terms will be resolved through
            binding arbitration in <strong>Maricopa County, Arizona</strong>,
            governed by the laws of the <strong>State of Arizona</strong>. You
            waive your right to participate in a class-action lawsuit or
            class-wide arbitration.
          </p>
          <p>
            Each party will bear its own costs and expenses related to the
            arbitration, including attorney fees, unless the arbitrator
            determines that a party has acted in bad faith, in which case the
            arbitrator may award fees to the prevailing party.
          </p>
          <p>
            Notwithstanding the above, either party may bring a claim in small
            claims court in <strong>Maricopa County, Arizona</strong>, if the
            claim qualifies for such court.
          </p>

          <h2 className="text-xl font-bold mt-4">12. Termination</h2>
          <p>
            We reserve the right to terminate or suspend your account at any
            time for violations of these terms. Upon termination, you must cease
            all use of the website.
          </p>

          <h2 className="text-xl font-bold mt-4">13. Changes to Terms</h2>
          <p>
            We may update these Terms and Conditions from time to time. Any
            changes will be posted on this page, and your continued use of the
            website constitutes acceptance of the updated terms.
          </p>

          <h2 className="text-xl font-bold mt-4">14. Governing Law</h2>
          <p>
            These terms are governed by the laws of the{" "}
            <strong>State of Arizona</strong>, without regard to its conflict of
            laws principles. Any legal actions must be brought in the courts of{" "}
            <strong>Maricopa County, Arizona</strong>.
          </p>

          <h2 className="text-xl font-bold mt-4">15. Severability</h2>
          <p>
            If any provision of these terms is found to be invalid or
            unenforceable, the remaining provisions will remain in full force
            and effect.
          </p>
          {/* TODO: Update contact information before launch */}
          <h2 className="text-xl font-bold mt-4">16. Contact Information</h2>
          <p>
            If you have any questions about these Terms and Conditions, please
            contact us at:
            <br />
            Email:{" "}
            <span className="text-gray-500">TODO: Add your email address</span>
            <br />
            Phone:{" "}
            <span className="text-gray-500">TODO: Add your phone number</span>
            <br />
            Address:{" "}
            <span className="text-gray-500">
              TODO: Add your business address
            </span>
          </p>
        </div>
        <div className="mt-4 flex justify-end">
          <button
            onClick={onClose}
            className="mr-2 px-4 py-2 bg-gray-300 rounded-md hover:bg-gray-400"
          >
            Close
          </button>
          <button
            onClick={onAgree}
            disabled={!isScrolledToBottom}
            className={`px-4 py-2 ${
              isScrolledToBottom
                ? "bg-primary text-white hover:bg-primary-dark"
                : "bg-gray-300 text-gray-500 cursor-not-allowed"
            } rounded-md`}
          >
            Agree
          </button>
        </div>
      </div>
    </div>
  );
};

export default TermsModal;
