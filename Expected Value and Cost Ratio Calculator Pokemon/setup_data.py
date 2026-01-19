"""
Data setup helper for EVR Calculator
This script creates the necessary data files and directories for the calculator
"""

import os
import sys
import pandas as pd
from pathlib import Path

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from constants.tcg.pokemon.scarletAndVioletEra.setMap import SET_CONFIG_MAP, SET_ALIAS_MAP

def create_directories(excel_path):
    """Create necessary directories if they don't exist"""
    directory = os.path.dirname(excel_path)
    Path(directory).mkdir(parents=True, exist_ok=True)
    print(f"✓ Created directories: {directory}")

def create_sample_data(config, excel_path):
    """Create sample Pokémon card data file"""
    
    # Create sample data based on the config's pull rate mapping
    data = {
        'Card Name': [],
        'Rarity': [],
        'Price ($)': [],
        'Pull Rate (1/X)': [],
        'Pack Price': [],
    }
    
    # Generate sample cards for each rarity
    sample_prices = {
        'common': 0.25,
        'uncommon': 0.50,
        'rare': 2.00,
        'double rare': 8.00,
        'ultra rare': 15.00,
        'illustration rare': 20.00,
        'special illustration rare': 50.00,
        'hyper rare': 30.00,
    }
    
    pack_price = 3.99  # Default MSRP for booster pack
    
    for rarity, pull_rate in config.PULL_RATE_MAPPING.items():
        # Create 3-5 sample cards per rarity
        num_cards = min(5, max(3, pull_rate // 100))
        
        for i in range(num_cards):
            price = sample_prices.get(rarity, 2.00)
            # Vary prices slightly for variety
            varied_price = price * (0.8 + (i * 0.1))
            
            data['Card Name'].append(f"Sample {rarity.title()} Card {i+1}")
            data['Rarity'].append(rarity)
            data['Price ($)'].append(round(varied_price, 2))
            data['Pull Rate (1/X)'].append(pull_rate)
            data['Pack Price'].append(pack_price)
    
    # Create DataFrame and save
    df = pd.DataFrame(data)
    df.to_excel(excel_path, index=False)
    print(f"✓ Created sample data file: {excel_path}")
    print(f"  - {len(df)} sample cards created")
    print(f"  - Rarities: {', '.join(df['Rarity'].unique())}")

def main():
    print("=" * 60)
    print("EVR Calculator - Data Setup Helper")
    print("=" * 60)
    
    # Get set input
    setName = input("\nWhat set do you want to set up? (e.g., 151): ").lower().strip()
    
    # Resolve set name
    if setName in SET_ALIAS_MAP:
        config_key = SET_ALIAS_MAP[setName]
    elif setName in SET_CONFIG_MAP:
        config_key = setName
    else:
        print(f"✗ Set '{setName}' not recognized")
        return
    
    config = SET_CONFIG_MAP[config_key]()
    
    # Construct file path
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    excel_path = os.path.join(project_root, 'excelDocs', config.SET_NAME, 'pokemon_data.xlsx')
    
    print(f"\n📁 Target location: {excel_path}")
    
    # Check if file already exists
    if os.path.exists(excel_path):
        print(f"ℹ File already exists at: {excel_path}")
        overwrite = input("Do you want to overwrite it with fresh sample data? (y/n): ").lower()
        if overwrite != 'y':
            print("Cancelled")
            return
    
    # Create directories
    create_directories(excel_path)
    
    # Create sample data
    print(f"\n📊 Creating sample data for {config.SET_NAME}...")
    create_sample_data(config, excel_path)
    
    print("\n" + "=" * 60)
    print("✓ Setup complete!")
    print("=" * 60)
    print(f"\nYou can now run the main calculator:")
    print(f"  python main.py")
    print(f"\nThe sample data contains basic card information.")
    print(f"For real data, run the Scraper:")
    print(f"  python ../Scraper/main.py")
    print()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n✗ Error: {e}")
        sys.exit(1)
