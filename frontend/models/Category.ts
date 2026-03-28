import mongoose, { Schema } from "mongoose";

// Define the category schema
const CategorySchema = new Schema(
  {
    name: { type: String, required: true },
    parent: { type: mongoose.Types.ObjectId, ref: 'Category' },
  },
  {
    timestamps: true,
  }
);

// Create and export the Category model
const Category = mongoose.models.Category || mongoose.model("Category", CategorySchema);

export default Category;
