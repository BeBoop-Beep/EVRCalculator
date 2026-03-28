import mongoose, { Schema } from "mongoose";

// Define the product schema
const ProductSchema = new Schema(
  {
    title: { type: String, required: true },
    description: { type: String, default: "" },
    price: { type: Number, required: true },
    quantity: { type: Number, required: true},
    images: [{ type: String, default: "" }],
    categories: [{ type: mongoose.Schema.Types.ObjectId, ref: "Category" }] // Reference Category model
  },
  {
    timestamps: true,
  }
);

// Create and export the Product model
const Product = mongoose.models.Product || mongoose.model("Product", ProductSchema);

export default Product;
