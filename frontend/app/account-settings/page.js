"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  getCurrentUserProfile,
  getTcgOptions,
  updateCurrentUserProfile,
} from "@/lib/profile/profileClient";

/** @typedef {import("@/types/profile").UserProfileRow} UserProfileRow */
/** @typedef {import("@/types/profile").TcgOption} TcgOption */

function buildInitialFormState(profile) {
  return {
    display_name: profile?.display_name || "",
    bio: profile?.bio || "",
    location: profile?.location || "",
    favorite_tcg_id: profile?.favorite_tcg_id ?? "",
    is_profile_public: Boolean(profile?.is_profile_public),
    show_portfolio_value: Boolean(profile?.show_portfolio_value),
    show_activity: Boolean(profile?.show_activity),
  };
}

function validateForm(formState) {
  if (formState.display_name.length > 80) {
    return "Display name must be 80 characters or less.";
  }

  if (formState.bio.length > 280) {
    return "Bio must be 280 characters or less.";
  }

  if (formState.location.length > 120) {
    return "Location must be 120 characters or less.";
  }

  return "";
}

export default function AccountSettingsPage() {
  const router = useRouter();

  /** @type {[UserProfileRow | null, Function]} */
  const [profile, setProfile] = useState(null);
  /** @type {[TcgOption[], Function]} */
  const [tcgs, setTcgs] = useState([]);
  const [formState, setFormState] = useState(buildInitialFormState(null));
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  useEffect(() => {
    let mounted = true;

    const loadPageData = async () => {
      setIsLoading(true);
      setErrorMessage("");

      try {
        const [profileResponse, tcgsResponse] = await Promise.all([
          getCurrentUserProfile(),
          getTcgOptions(),
        ]);

        if (!mounted) return;

        setProfile(profileResponse.profile);
        setFormState(buildInitialFormState(profileResponse.profile));
        setTcgs(tcgsResponse.tcgs || []);
      } catch (error) {
        if (!mounted) return;

        if (error?.status === 401) {
          router.push("/login");
          return;
        }

        setErrorMessage(error?.message || "Unable to load account settings.");
      } finally {
        if (mounted) setIsLoading(false);
      }
    };

    loadPageData();

    return () => {
      mounted = false;
    };
  }, [router]);

  const disableSave = useMemo(() => isLoading || isSaving, [isLoading, isSaving]);

  const handleInputChange = (event) => {
    const { name, value } = event.target;
    setFormState((prev) => ({ ...prev, [name]: value }));
    setSuccessMessage("");
  };

  const handleToggleChange = (event) => {
    const { name, checked } = event.target;
    setFormState((prev) => ({ ...prev, [name]: checked }));
    setSuccessMessage("");
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setErrorMessage("");
    setSuccessMessage("");

    const validationError = validateForm(formState);
    if (validationError) {
      setErrorMessage(validationError);
      return;
    }

    setIsSaving(true);

    try {
      const payload = {
        display_name: formState.display_name.trim() || null,
        bio: formState.bio.trim() || null,
        location: formState.location.trim() || null,
        favorite_tcg_id: formState.favorite_tcg_id === "" ? null : formState.favorite_tcg_id,
        is_profile_public: Boolean(formState.is_profile_public),
        show_portfolio_value: Boolean(formState.show_portfolio_value),
        show_activity: Boolean(formState.show_activity),
      };

      const response = await updateCurrentUserProfile(payload);
      setProfile(response.profile);
      setFormState(buildInitialFormState(response.profile));
      setSuccessMessage("Account settings saved.");
    } catch (error) {
      setErrorMessage(error?.message || "Unable to save account settings.");
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return (
      <main className="mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
        <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-8">
          <h1 className="text-2xl font-semibold text-[var(--text-primary)]">Account Settings</h1>
          <p className="mt-2 text-sm text-[var(--text-secondary)]">Loading your account preferences...</p>
        </div>
      </main>
    );
  }

  if (!profile && errorMessage) {
    return (
      <main className="mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
        <div className="rounded-2xl border border-red-500/30 bg-[var(--surface-panel)] p-8">
          <h1 className="text-2xl font-semibold text-[var(--text-primary)]">Account Settings</h1>
          <p className="mt-2 text-sm text-red-300">{errorMessage}</p>
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto w-full max-w-7xl space-y-6 px-4 py-8 sm:px-6 lg:px-8">
      <section className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] px-6 py-5">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-[1fr_auto] md:items-end">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">inDex</p>
            <h1 className="mt-1 text-2xl font-semibold text-[var(--text-primary)]">Account Settings</h1>
            <p className="mt-2 text-sm text-[var(--text-secondary)]">Manage profile privacy and collector preferences.</p>
          </div>

          <div className="inline-flex w-fit items-center gap-2 self-start rounded-full border border-[var(--border-subtle)] bg-[var(--surface-page)] px-3 py-2 text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)] md:self-auto">
            Profile Preferences
          </div>
        </div>
      </section>

      <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-6 sm:p-8">
        <h2 className="text-xl font-semibold text-[var(--text-primary)]">Settings</h2>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">Manage your profile visibility and collector preferences.</p>

        <form id="account-settings-form" className="mt-6 space-y-5" onSubmit={handleSubmit}>
          <div>
            <label htmlFor="display_name" className="mb-1 block text-sm font-semibold text-[var(--text-primary)]">
              Display Name
            </label>
            <input
              id="display_name"
              name="display_name"
              type="text"
              value={formState.display_name}
              onChange={handleInputChange}
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-secondary)]"
              placeholder="How your name appears publicly"
            />
          </div>

          <div>
            <label htmlFor="bio" className="mb-1 block text-sm font-semibold text-[var(--text-primary)]">
              Bio
            </label>
            <textarea
              id="bio"
              name="bio"
              value={formState.bio}
              onChange={handleInputChange}
              rows={4}
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-secondary)]"
              placeholder="Tell collectors about your collecting focus"
            />
          </div>

          <div>
            <label htmlFor="location" className="mb-1 block text-sm font-semibold text-[var(--text-primary)]">
              Location
            </label>
            <input
              id="location"
              name="location"
              type="text"
              value={formState.location}
              onChange={handleInputChange}
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-secondary)]"
              placeholder="City, State or Region"
            />
          </div>

          <div>
            <label htmlFor="favorite_tcg_id" className="mb-1 block text-sm font-semibold text-[var(--text-primary)]">
              Favorite TCG
            </label>
            <select
              id="favorite_tcg_id"
              name="favorite_tcg_id"
              value={formState.favorite_tcg_id}
              onChange={handleInputChange}
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] px-3 py-2 text-sm text-[var(--text-primary)]"
            >
              <option value="">No favorite selected</option>
              {tcgs.map((tcg) => (
                <option key={tcg.id} value={tcg.id}>
                  {tcg.name}
                </option>
              ))}
            </select>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <label className="flex cursor-pointer items-center justify-between rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] p-3 text-sm text-[var(--text-secondary)]">
              Profile Public
              <input
                name="is_profile_public"
                type="checkbox"
                checked={formState.is_profile_public}
                onChange={handleToggleChange}
                className="h-4 w-4"
              />
            </label>

            <label className="flex cursor-pointer items-center justify-between rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] p-3 text-sm text-[var(--text-secondary)]">
              Show Portfolio Value
              <input
                name="show_portfolio_value"
                type="checkbox"
                checked={formState.show_portfolio_value}
                onChange={handleToggleChange}
                className="h-4 w-4"
              />
            </label>

            <label className="flex cursor-pointer items-center justify-between rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] p-3 text-sm text-[var(--text-secondary)] sm:col-span-2">
              Show Activity
              <input
                name="show_activity"
                type="checkbox"
                checked={formState.show_activity}
                onChange={handleToggleChange}
                className="h-4 w-4"
              />
            </label>
          </div>

          {errorMessage ? <p className="text-sm text-red-600">{errorMessage}</p> : null}
          {successMessage ? <p className="text-sm text-green-700">{successMessage}</p> : null}

          <div className="flex flex-wrap gap-3">
            <button
              type="submit"
              disabled={disableSave}
              className="rounded-lg bg-brand px-5 py-2 text-sm font-semibold text-white hover:bg-brand-dark disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isSaving ? "Saving..." : "Save Changes"}
            </button>

            <button
              type="button"
              onClick={() => router.push("/profile")}
              className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] px-5 py-2 text-sm font-semibold text-[var(--text-primary)] hover:bg-[var(--surface-hover)]"
            >
              Back to Profile
            </button>
          </div>
        </form>
      </div>
    </main>
  );
}
