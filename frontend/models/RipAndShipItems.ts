import mongoose, { Schema } from "mongoose";

// Define the ripAndShip schema
const RipAndShipSchema = new Schema(
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

// Create and export the RipAndShip model
const RipAndShip = mongoose.models.RipAndShip || mongoose.model("RipAndShip", RipAndShipSchema);

export default RipAndShip;
