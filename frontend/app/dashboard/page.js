"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";

export default function Dashboard() {
  const [customer, setCustomer] = useState(null);
  const [editingField, setEditingField] = useState(null);
  const [formData, setFormData] = useState({
    name: "",
    email: "",
  });
  const [passwordData, setPasswordData] = useState({
    currentPassword: "",
    newPassword: "",
    confirmNewPassword: "",
  });
  const [passwordError, setPasswordError] = useState("");
  const [isPasswordModalOpen, setIsPasswordModalOpen] = useState(false);

  const router = useRouter();

  // Fetch customer details
  const fetchCustomerDetails = useCallback(async () => {
    try {
      const res = await fetch("/api/auth/me");
      if (!res.ok) {
        router.push("/login");
        return;
      }
      const data = await res.json();
      setCustomer({ ...data.user });
      setFormData({
        name: data.user.name || "",
        email: data.user.email || "",
      });
    } catch (error) {
      console.error("Error fetching customer details:", error);
    }
  }, [router]);

  useEffect(() => {
    fetchCustomerDetails();
  }, [fetchCustomerDetails]);

  // Logout function
  const handleLogout = async () => {
    try {
      const response = await fetch("/api/logout", {
        method: "POST",
      });

      if (response.ok) {
        console.log("Logout successful");
        router.push("/login"); // Redirect to login page
      } else {
        console.log("Logout failed");
      }
    } catch (error) {
      console.error("Error during logout:", error);
    }
  };

  // Update customer details
  const handleSubmit = async (field) => {
    const res = await fetch("/api/customer/update", {
      method: "PUT",
      body: JSON.stringify({ [field]: formData[field] }),
      headers: { "Content-Type": "application/json" },
    });

    if (res.ok) {
      alert(`${field} updated successfully`);
      await fetchCustomerDetails(); // Re-fetch updated user details
      setEditingField(null);
    } else {
      alert("Error updating details");
    }
  };

  const handleChange = (e) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value || "",
    });
  };

  const handlePasswordChange = (e) => {
    setPasswordData({
      ...passwordData,
      [e.target.name]: e.target.value || "",
    });
  };

  const handlePasswordSubmit = async () => {
    if (passwordData.newPassword !== passwordData.confirmNewPassword) {
      setPasswordError("New password and confirmation do not match.");
      return;
    }

    if (passwordData.newPassword.length < 6) {
      setPasswordError("Password must be at least 6 characters.");
      return;
    }

    try {
      const res = await fetch("/api/customer/updatePassword", {
        method: "PUT",
        body: JSON.stringify({
          currentPassword: passwordData.currentPassword,
          newPassword: passwordData.newPassword,
        }),
        headers: { "Content-Type": "application/json" },
      });

      if (res.ok) {
        alert("Password updated successfully");
        setPasswordData({
          currentPassword: "",
          newPassword: "",
          confirmNewPassword: "",
        });
        setIsPasswordModalOpen(false);
      } else {
        const responseText = await res.text();
        let errorData;
        try {
          errorData = JSON.parse(responseText);
        } catch (e) {
          errorData = { message: "An unknown error occurred" };
        }
        setPasswordError(errorData.message || "Error updating password");
      }
    } catch (error) {
      console.error("Error updating password:", error);
      setPasswordError("Error updating password");
    }
  };

  return (
    <div className="mx-auto max-w-4xl px-4 py-6 sm:px-6">
      <div className="dashboard-container">
      <div className="page-hero-panel rounded-2xl px-6 py-8">
        <h1 className="mb-4 text-center text-3xl font-bold text-[var(--text-primary)]">
          Dashboard
        </h1>
        {customer && (
          <div className="flex flex-col items-center space-y-6">
            {Object.keys(formData).map((field) => (
              <div key={field} className="w-full mb-3">
                <label className="font-semibold capitalize text-[var(--text-secondary)]">
                  {field}
                </label>
                {editingField === field ? (
                  <div className="flex gap-3">
                    <input
                      type={field === "email" ? "email" : "text"}
                      name={field}
                      value={formData[field]}
                      onChange={handleChange}
                      className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] p-2 text-[var(--text-primary)] focus:ring-2 focus:ring-[var(--accent)]"
                    />
                    <button
                      onClick={() => handleSubmit(field)}
                      className="rounded-lg bg-[var(--brand)] px-4 py-2 text-white hover:bg-[var(--brand-dark)]"
                    >
                      ✔
                    </button>
                    <button
                      onClick={() => setEditingField(null)}
                      className="rounded-lg bg-[var(--surface-page)] px-4 py-2 text-[var(--text-primary)] hover:bg-[var(--surface-hover)]"
                    >
                      ✖
                    </button>
                  </div>
                ) : (
                  <div
                    className="flex cursor-pointer items-center justify-between rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] p-2 hover:bg-[var(--surface-hover)]"
                    onClick={() => setEditingField(field)}
                  >
                    <span className="text-[var(--text-primary)]">{customer[field] || "Not set"}</span>
                    <button className="text-[var(--brand)] hover:text-[var(--accent)]">
                      Edit
                    </button>
                  </div>
                )}
              </div>
            ))}

            <button
              onClick={() => setIsPasswordModalOpen(true)}
              className="mt-4 rounded-lg bg-[var(--brand)] px-4 py-2 text-white hover:bg-[var(--brand-dark)]"
            >
              Change Password
            </button>

            {/* Logout Button */}
            <button
              onClick={handleLogout}
              className="mt-4 rounded-lg bg-[var(--neutral)] px-4 py-2 text-white hover:bg-[var(--surface-hover)]"
            >
              Logout
            </button>

            {isPasswordModalOpen && (
              <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
                <div className="w-96 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-6">
                  <h2 className="mb-4 text-xl font-semibold text-[var(--text-primary)]">
                    Change Password
                  </h2>
                  {passwordError && (
                    <p className="text-red-500 text-sm">{passwordError}</p>
                  )}
                  <input
                    type="password"
                    name="currentPassword"
                    value={passwordData.currentPassword}
                    onChange={handlePasswordChange}
                    className="mb-2 w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] p-2 text-[var(--text-primary)]"
                    placeholder="Current Password"
                  />
                  <input
                    type="password"
                    name="newPassword"
                    value={passwordData.newPassword}
                    onChange={handlePasswordChange}
                    className="mb-2 w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] p-2 text-[var(--text-primary)]"
                    placeholder="New Password"
                  />
                  <input
                    type="password"
                    name="confirmNewPassword"
                    value={passwordData.confirmNewPassword}
                    onChange={handlePasswordChange}
                    className="mb-4 w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] p-2 text-[var(--text-primary)]"
                    placeholder="Confirm New Password"
                  />
                  <div className="flex justify-between">
                    <button
                      onClick={handlePasswordSubmit}
                      className="rounded-lg bg-[var(--brand)] px-3 py-2 text-white hover:bg-[var(--brand-dark)]"
                    >
                      Update Password
                    </button>
                    <button
                      onClick={() => setIsPasswordModalOpen(false)}
                      className="rounded-lg bg-[var(--surface-page)] px-3 py-2 text-[var(--text-primary)] hover:bg-[var(--surface-hover)]"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
        </div>
        </div>
      </div>
  );
}
