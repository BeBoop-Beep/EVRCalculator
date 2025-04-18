import pandas as pd
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
import os

# Load the spreadsheet
file_path = "excelDocs/scarletAndViolet151/pokemon_data.xlsx"
df = pd.read_excel(file_path, engine='openpyxl')

# Ensure minimum required columns exist
required_columns = ["Card Name", "Pull Rate (1/X)", "Price ($)", "Hit Rate Adjustment (1+HR)"]
for col in required_columns:
    if col not in df.columns:
        raise KeyError(f"Missing required column: '{col}' in the spreadsheet.")

# Check if "Rarity" column exists (if not, use default 1/X)
use_rarity_adjustment = "Rarity" in df.columns

# Market price per pack (update accordingly)
pack_price = df["Current Market Pack Price"].iloc[0]

# Pack configuration constants
TOTAL_CARDS_PER_PACK = 10  # Update based on your set
GUARANTEED_POKEBALL_SLOTS = 1  # 1 Poké Ball per pack
MASTERBALL_CHANCE = 0.05  # 25% chance to replace Poké Ball slot

# Define what counts as a "hit"
HIT_RARITIES = [
    "master ball pattern",
    "special illustration rare",
    "illustration rare",
    "ace spec",
    "hyper rare",
    "ultra rare"
]

# Function to identify hits
def is_hit(row):
    card_name = str(row["Card Name"]).lower()
    rarity = str(row["Rarity"]).lower() if use_rarity_adjustment else ""
    
    # Check for master ball pattern in name
    if "master ball pattern" in card_name:
        return True
    
    # Check for hit rarities
    return any(hit_rarity in rarity for hit_rarity in HIT_RARITIES)

# Calculate hit rate adjustment
total_cards = len(df)
total_hits = sum(df.apply(is_hit, axis=1))
hit_rate_adjustment = 1 + (total_hits / total_cards)

# Store the adjustment in the designated column
df["Hit Rate Adjustment (1+HR)"].iloc[0] = hit_rate_adjustment


# Define rarity groups and their multipliers
RARITY_GROUPS = {
    "common": 5.5,    # Multiply sum by 5.5
    "uncommon": 1.5,  # Multiply sum by 1.5
    "rare": 1.5       # Multiply sum by 1.5
}

def classify_card(row):
    """Classify cards into groups and return (pull_rate, group)"""
    card_name = str(row["Card Name"]).lower()
    rarity = str(row["Rarity"]).lower() if use_rarity_adjustment else ""
    
    # 1. Highest priority: special patterns
    if "poke ball pattern" in card_name:
        return (302, "other")
    if "master ball pattern" in card_name:
        return (1362, "other")
    
    # 2. Check for special rarities (must come before regular rarities)
    if "special illustration rare" in rarity:
        return (225, "other")
    if "illustration rare" in rarity:
        return (188, "other")
    if "hyper rare" in rarity:
        return (154, "other")
    if "double rare" in rarity:
        return (90, "other")
    if "ultra rare" in rarity:
        return (248, "other")
    # if "ace spec" in rarity:
    #     return (128, "other")
    
    
    # 3. Now check basic rarities with exact matching
    if rarity == "common":
        return (row["Pull Rate (1/X)"], "common")
    if rarity == "uncommon":
        return (row["Pull Rate (1/X)"], "uncommon")
    if rarity == "holo rare":
        return (row["Pull Rate (1/X)"], "rare")
    if rarity == "rare":
        return (row["Pull Rate (1/X)"], "rare")
    
    # 4. Fallback for any unrecognized rarities
    return (row["Pull Rate (1/X)"], "other")

# Classify all cards and calculate EV components
df[["Pull Rate", "Rarity Group"]] = df.apply(
    lambda row: pd.Series(classify_card(row)), axis=1)

# Calculate EV components for each group
ev_components = {
    "common": df[df["Rarity Group"] == "common"]["Price ($)"].div(
              df[df["Rarity Group"] == "common"]["Pull Rate"]).sum(),
    "uncommon": df[df["Rarity Group"] == "uncommon"]["Price ($)"].div(
                df[df["Rarity Group"] == "uncommon"]["Pull Rate"]).sum(),
    "rare": df[df["Rarity Group"] == "rare"]["Price ($)"].div(
            df[df["Rarity Group"] == "rare"]["Pull Rate"]).sum(),
    "other": df[df["Rarity Group"] == "other"]["Price ($)"].div(
             df[df["Rarity Group"] == "other"]["Pull Rate"]).sum()
}

# Apply multipliers and calculate totals
common_ev = ev_components["common"] * RARITY_GROUPS["common"]
uncommon_ev = ev_components["uncommon"] * RARITY_GROUPS["uncommon"]
rare_ev = ev_components["rare"] * RARITY_GROUPS["rare"]
other_ev = ev_components["other"] * 1  # multiplier of 1

# Calculate base EV before hit rate adjustment
EV_base = common_ev + uncommon_ev + rare_ev + other_ev
EV = EV_base * hit_rate_adjustment
net_value = EV - pack_price
roi_per_pack = EV / pack_price

# Add all calculations to the DataFrame for inspection
df["EV Component"] = df["Price ($)"] / df["Pull Rate"]
df.loc[0, "Total Cards"] = total_cards
df.loc[0, "Total Hits"] = total_hits
df.loc[0, "Hit Rate Adjustment"] = hit_rate_adjustment
df.loc[0, "Common EV Sum"] = ev_components["common"]
df.loc[0, "Uncommon EV Sum"] = ev_components["uncommon"]
df.loc[0, "Rare EV Sum"] = ev_components["rare"]
df.loc[0, "Other EV Sum"] = ev_components["other"]
df.loc[0, "Common EV (x5.5)"] = common_ev
df.loc[0, "Uncommon EV (x1.5)"] = uncommon_ev
df.loc[0, "Rare EV (x1.5)"] = rare_ev
df.loc[0, "Other EV"] = other_ev
df.loc[0, "Total EV Base"] = EV_base
df.loc[0, "Total EV"] = EV
df.loc[0, "net value per pack"] = net_value
df.loc[0, "roi per pack"] = roi_per_pack

# Save to new file
base_filename = os.path.splitext(file_path)[0]
output_file = base_filename + "_final.xlsx"

# Preserve formatting
with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
    df.to_excel(writer, index=False, sheet_name="Data")
    workbook = writer.book
    worksheet = workbook.active
    
    # Copy column widths from original
    original_workbook = load_workbook(file_path)
    original_worksheet = original_workbook.active
    for i, col in enumerate(original_worksheet.columns):
        max_length = max(len(str(cell.value)) for cell in col) if any(cell.value for cell in col) else 0
        adjusted_width = (max_length + 2)
        worksheet.column_dimensions[get_column_letter(i + 1)].width = adjusted_width

# Print detailed EV breakdown
print("\nHit Rate Calculation:")
print(f"Total Cards: {total_cards}")
print(f"Total Hits: {total_hits}")
print(f"Hit Rate Adjustment: 1 + ({total_hits}/{total_cards}) = {hit_rate_adjustment:.4f}")

print("\nDetailed EV Calculation Breakdown:")
print(f"Sum of (Price/PullRate) for Commons: {ev_components['common']:.6f} x5.5 = {common_ev:.6f}")
print(f"Sum of (Price/PullRate) for Uncommons: {ev_components['uncommon']:.6f} x1.5 = {uncommon_ev:.6f}")
print(f"Sum of (Price/PullRate) for Rares: {ev_components['rare']:.6f} x1.5 = {rare_ev:.6f}")
print(f"Sum of (Price/PullRate) for Others: {ev_components['other']:.6f} x1 = {other_ev:.6f}")
print(f"\nBase EV (before hit rate): {EV_base:.6f}")
print(f"Final EV per pack: ${EV:.2f}")
print(f"net_value: {net_value:.4f}")
print(f"roi_per_pack: {roi_per_pack:.4f}")

print(f"\nUpdated spreadsheet saved as {output_file}!")

if not use_rarity_adjustment:
    print("Note: 'Rarity' column not found. Used default 1/X pull rates.")