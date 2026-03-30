'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import TermsAndConditions from '@/components/Legal/TermsAndConditionsModal'; // Import the modal

export default function Signup() {
  const router = useRouter();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [termsAccepted, setTermsAccepted] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [infoMessage, setInfoMessage] = useState('');
  const [isTermsModalOpen, setIsTermsModalOpen] = useState(false);

  const handleSignup = async (e) => {
    e.preventDefault();
    setErrorMessage('');
    setInfoMessage('');

    // Validate form
    if (password !== confirmPassword) {
      alert('Passwords do not match!');
      return;
    }

    if (!termsAccepted) {
      alert('You must accept the terms and conditions.');
      return;
    }

    if (!email || !password || !name) {
      alert('Please fill in all fields.');
      return;
    }

    try {
      // Send the user data to the server for signup
      const response = await fetch('/api/signup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ name, email, password }),
      });

      const data = await response.json();

      // Check if the response is successful
      if (response.ok) {
        if (data?.requiresEmailConfirmation) {
          setInfoMessage(data?.message || 'Signup successful. Please confirm your email before logging in.');
          router.push('/login');
          return;
        }

        // Redirect to profile only when authenticated session is available.
        router.push('/profile');
      } else {
        setErrorMessage(data.error || 'Signup failed');
      }
    } catch (error) {
      setErrorMessage('Something went wrong. Please try again.');
    }
  };

  return (
    <div className="container mx-auto p-6 py-16">
      <div className="max-w-md mx-auto bg-[var(--surface-panel)] p-8 rounded-lg border border-[var(--border-subtle)]">
        <h2 className="text-4xl font-bold text-center text-[var(--text-primary)] mb-6">Create Account</h2>

        {errorMessage && <p className="text-red-500 text-center">{errorMessage}</p>}
        {infoMessage && <p className="text-green-700 text-center mb-2">{infoMessage}</p>}

        {/* Form fields */}
        <div className="mb-4">
          <label htmlFor="name" className="block text-[var(--text-secondary)]">Full Name</label>
          <input
            type="text"
            id="name"
            className="w-full px-4 py-2 mt-2 border border-[var(--border-subtle)] rounded-md bg-[var(--surface-page)] text-[var(--text-primary)] placeholder:text-[var(--text-secondary)] focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/25 transition-[border-color,box-shadow] duration-200 ease-in-out"
            placeholder="Enter your full name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>

        <div className="mb-4">
          <label htmlFor="email" className="block text-[var(--text-secondary)]">Email</label>
          <input
            type="email"
            id="email"
            className="w-full px-4 py-2 mt-2 border border-gray-300 rounded-md focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/25 transition-[border-color,box-shadow] duration-200 ease-in-out"
            placeholder="Enter your email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>

        <div className="mb-4">
          <label htmlFor="password" className="block text-[var(--text-secondary)]">Password</label>
          <input
            type="password"
            id="password"
            className="w-full px-4 py-2 mt-2 border border-gray-300 rounded-md focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/25 transition-[border-color,box-shadow] duration-200 ease-in-out"
            placeholder="Enter your password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        <div className="mb-6">
          <label htmlFor="confirm-password" className="block text-[var(--text-secondary)]">Confirm Password</label>
          <input
            type="password"
            id="confirm-password"
            className="w-full px-4 py-2 mt-2 border border-gray-300 rounded-md focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/25 transition-[border-color,box-shadow] duration-200 ease-in-out"
            placeholder="Confirm your password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
          />
        </div>

        <div className="flex items-center mb-6">
          <input
            type="checkbox"
            id="terms"
            checked={termsAccepted}
            onChange={() => setTermsAccepted(!termsAccepted)}
            disabled={!termsAccepted} // Disable the checkbox unless terms are accepted
            className="mr-2"
          />
          <label htmlFor="terms" className="text-[var(--text-secondary)]">
            I agree to the{' '}
            <button
              onClick={() => setIsTermsModalOpen(true)}
              className="text-accent hover:underline transition-colors duration-200 ease-in-out"
            >
              Terms & Conditions
            </button>
          </label>
        </div>

        <button
          onClick={handleSignup}
          className="w-full bg-brand text-white text-xl py-2 rounded-md hover:bg-brand-dark transition-colors duration-200 ease-in-out cursor-pointer font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
          disabled={!termsAccepted}
        >
          Create Account
        </button>

        <div className="mt-4 text-center text-[var(--text-secondary)]">
          <p>
            Already have an account?{' '}
            <a href="/login" className="text-accent hover:underline transition-colors duration-200 ease-in-out">
              Login
            </a>
          </p>
        </div>
      </div>

      {/* Terms Modal */}
      <TermsAndConditions
        isOpen={isTermsModalOpen}
        onClose={() => setIsTermsModalOpen(false)}
        onAgree={() => {
          setTermsAccepted(true); // Enable the checkbox when the user agrees
          setIsTermsModalOpen(false);
        }}
      />
    </div>
  );
}