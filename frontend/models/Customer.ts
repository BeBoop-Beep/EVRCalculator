// models/Customer.js

import mongoose from 'mongoose';

const CustomerSchema = new mongoose.Schema(
  {
    name: {
      type: String,
      required: true,
      trim: true,
    },
    email: {
      type: String,
      required: true,
      unique: true, // Ensures no duplicate emails
      lowercase: true, // Store email in lowercase
      trim: true,
      match: [/^\S+@\S+\.\S+$/, 'Please enter a valid email address'], // Email validation regex
    },
    password: {
      type: String,
      required: true,
      minlength: 6, // Password should have at least 6 characters
    },
    phone: {
      type: String,
      trim: true,
    },
    address: {
      type: String,
      trim: true,
    },
    isVerified: {
      type: Boolean,
      default: false,
    },
  },
  {
    timestamps: true, // Automatically adds createdAt and updatedAt
  }
);

const Customer = mongoose.models.Customer || mongoose.model('Customer', CustomerSchema);

export default Customer;
