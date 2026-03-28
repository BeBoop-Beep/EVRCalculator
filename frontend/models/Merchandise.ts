import mongoose, { Schema } from "mongoose";

// Define the product schema
const MerchandiseSchema = new Schema(
  {
    title: { type: String, required: true },
    description: { type: String, default: "" },
    price: { type: Number, required: true },
    quantity: { type: Number, required: true},
    size: {type: String, default: ""},
    images: [{ type: String, default: "" }],
    categories: [{ type: mongoose.Schema.Types.ObjectId, ref: "Category" }] // Reference Category model
  },
  {
    timestamps: true,
  }
);

// Create and export the Product model
const Merchandise = mongoose.models.Merchandise || mongoose.model("Merchandise", MerchandiseSchema);

export default Merchandise;
