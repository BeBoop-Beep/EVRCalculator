"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";

export default function Dashboard() {
  const [customer, setCustomer] = useState(null);
  const [editingField, setEditingField] = useState(null);
  const [formData, setFormData] = useState({
    name: "",
    email: "",
    phone: "",
    address: "",
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
  const fetchCustomerDetails = async () => {
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
        phone: data.user.phone || "",
        address: data.user.address || "",
      });
    } catch (error) {
      console.error("Error fetching customer details:", error);
    }
  };

  useEffect(() => {
    fetchCustomerDetails();
  }, []);

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
    <div className="max-w-4xl mx-auto p-6">
      <div className="p-6 shadow-lg rounded-2xl bg-white border border-gray-200">
        <h1 className="text-3xl font-bold mb-4 text-primary text-center">
          Dashboard
        </h1>
        {customer && (
          <div className="flex flex-col items-center space-y-6">
            {Object.keys(formData).map((field) => (
              <div key={field} className="w-full mb-3">
                <label className="font-semibold capitalize text-gray-700">
                  {field}
                </label>
                {editingField === field ? (
                  <div className="flex gap-3">
                    <input
                      type={field === "email" ? "email" : "text"}
                      name={field}
                      value={formData[field]}
                      onChange={handleChange}
                      className="border p-2 w-full rounded-lg focus:ring-2 focus:ring-primary"
                    />
                    <button
                      onClick={() => handleSubmit(field)}
                      className="bg-primary text-white hover:bg-neutral-dark px-4 py-2 rounded-lg"
                    >
                      ✔
                    </button>
                    <button
                      onClick={() => setEditingField(null)}
                      className="bg-gray-300 hover:bg-gray-200 hover:text-neutral-dark text-primary px-4 py-2 rounded-lg"
                    >
                      ✖
                    </button>
                  </div>
                ) : (
                  <div
                    className="flex justify-between items-center p-2 border rounded-lg cursor-pointer hover:bg-gray-100"
                    onClick={() => setEditingField(field)}
                  >
                    <span>{customer[field] || "Not set"}</span>
                    <button className="text-primary hover:text-yellow-400">
                      Edit
                    </button>
                  </div>
                )}
              </div>
            ))}

            <button
              onClick={() => setIsPasswordModalOpen(true)}
              className="bg-primary hover:bg-neutral-dark text-white px-4 py-2 rounded-lg mt-4"
            >
              Change Password
            </button>

            {/* Logout Button */}
            <button
              onClick={handleLogout}
              className="bg-gray-400 hover:bg-gray-200 text-white px-4 py-2 rounded-lg mt-4"
            >
              Logout
            </button>

            {isPasswordModalOpen && (
              <div className="fixed inset-0 bg-gray-600 bg-opacity-50 flex justify-center items-center z-50">
                <div className="bg-white p-6 rounded-lg shadow-lg w-96">
                  <h2 className="text-xl font-semibold mb-4 text-primary">
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
                    className="border p-2 w-full rounded-lg mb-2"
                    placeholder="Current Password"
                  />
                  <input
                    type="password"
                    name="newPassword"
                    value={passwordData.newPassword}
                    onChange={handlePasswordChange}
                    className="border p-2 w-full rounded-lg mb-2"
                    placeholder="New Password"
                  />
                  <input
                    type="password"
                    name="confirmNewPassword"
                    value={passwordData.confirmNewPassword}
                    onChange={handlePasswordChange}
                    className="border p-2 w-full rounded-lg mb-4"
                    placeholder="Confirm New Password"
                  />
                  <div className="flex justify-between">
                    <button
                      onClick={handlePasswordSubmit}
                      className="bg-primary text-white px-3 py-2 rounded-lg"
                    >
                      Update Password
                    </button>
                    <button
                      onClick={() => setIsPasswordModalOpen(false)}
                      className="bg-gray-300 hover:bg-gray-200 hover:text-neutral-dark text-primary px-3 py-2 rounded-lg"
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
  );
}
