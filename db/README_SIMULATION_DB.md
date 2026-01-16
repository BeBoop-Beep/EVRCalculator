# Pack Simulation Database Refactoring

## Overview

The pack simulation and EV calculation system has been refactored to persist results to a database instead of only writing to Excel files. This provides better data management, querying capabilities, and historical tracking.

## Database Schema

### Tables Created

1. **pack_simulations** - Main simulation record
   - Core EV metrics (manual EV, simulated EV, pack price, ROI)
   - Hit probabilities
   - Links to set via `set_id`

2. **simulation_ev_breakdown** - Detailed EV breakdown by rarity
   - EV totals for each rarity type (common, uncommon, rare, etc.)
   - Multipliers used in calculations
   - Special pack contributions (god packs, demi-god packs)

3. **simulation_statistics** - Statistical summary
   - Mean, standard deviation, min, max
   - Variance metrics

4. **simulation_percentiles** - Distribution percentiles
   - 5th, 25th, 50th (median), 75th, 90th, 95th, 99th percentiles

5. **simulation_rarity_stats** - Per-rarity pull statistics
   - Pull counts and value totals by rarity
   - Average value per pull for each rarity

6. **simulation_top_hits** - Top 10 most valuable cards
   - Card name, price, effective pull rate
   - Ranked 1-10

### Schema File

The complete SQL schema is available at:
```
db/schemas/simulation_tables_schema.sql
```

To create these tables in your Supabase database, run this SQL file in the Supabase SQL editor.

## Architecture

The implementation follows a layered architecture:

```
┌─────────────────────────────────────┐
│   main.py (User Interface)          │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│   SimulationController               │
│   (db/controllers/)                  │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│   SimulationService                  │
│   (db/services/)                     │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│   Repositories (6 files)             │
│   (db/repositories/)                 │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│   Supabase Client                    │
└─────────────────────────────────────┘
```

### Files Created/Modified

**New Repository Files:**
- `db/repositories/pack_simulations_repository.py`
- `db/repositories/simulation_ev_breakdown_repository.py`
- `db/repositories/simulation_statistics_repository.py`
- `db/repositories/simulation_percentiles_repository.py`
- `db/repositories/simulation_rarity_stats_repository.py`
- `db/repositories/simulation_top_hits_repository.py`

**New Service Files:**
- `db/services/simulation_service.py` - Business logic for saving simulation data

**New Controller Files:**
- `db/controllers/simulation_controller.py` - High-level orchestration

**Modified Files:**
- `Expected Value and Cost Ratio Calculator Pokemon/main.py` - Added database persistence option

## Usage

### Running Simulations

When you run the main calculator, you'll now be prompted to choose where to save results:

```bash
python "Expected Value and Cost Ratio Calculator Pokemon/main.py"
```

You'll see:
```
What set are we working on: 
> stellar crown

Save results to (1) Database, (2) Excel, or (3) Both? [default: 1]: 
```

**Options:**
- `1` - Save to database only (recommended)
- `2` - Save to Excel only (legacy behavior)
- `3` - Save to both database and Excel

### Programmatic Usage

```python
from db.controllers.simulation_controller import SimulationController

controller = SimulationController()

# Save simulation results
simulation_id = controller.save_pack_simulation(
    set_name="Stellar Crown",
    results=results_dict,
    summary_data=summary_dict,
    sim_results=sim_results_dict,
    top_10_hits=top_10_dataframe
)

# Retrieve simulation with all related data
simulation_data = controller.get_simulation(simulation_id)

# Get latest simulation for a set
latest = controller.get_latest_simulation_for_set("Stellar Crown")
```

## Prerequisites

### Database Setup

1. **Create Tables**: Run the SQL schema in Supabase:
   ```sql
   -- Copy and paste contents of db/schemas/simulation_tables_schema.sql
   ```

2. **Environment Variables**: Ensure your `.env` file has:
   ```
   SUPABASE_URL=your_supabase_url
   SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
   ```

3. **Set Must Exist**: Before saving simulation results, ensure the set exists in the `sets` table. The scraper/ingest process should create this automatically.

### Python Dependencies

No new dependencies required - uses existing Supabase client.

## Data Flow

```
1. User runs main.py
   ↓
2. PackCalculationOrchestrator calculates EV
   ↓
3. Returns: results, summary_data, sim_results, top_10_hits
   ↓
4. SimulationController.save_pack_simulation()
   ↓
5. SimulationService.save_simulation_results()
   ↓
6. Repositories insert data into 6 tables
   ↓
7. Returns simulation_id
```

## Querying Simulation Data

### Get All Simulations for a Set

```python
from db.repositories.pack_simulations_repository import get_simulations_by_set_id
from db.repositories.sets_repository import get_set_id_by_name

set_id = get_set_id_by_name("Stellar Crown")
simulations = get_simulations_by_set_id(set_id)
```

### Get Complete Simulation Details

```python
from db.controllers.simulation_controller import SimulationController

controller = SimulationController()
data = controller.get_simulation(simulation_id)

# Access different parts
print(data['simulation'])      # Main record
print(data['ev_breakdown'])    # EV breakdown
print(data['statistics'])      # Stats
print(data['percentiles'])     # Percentiles
print(data['rarity_stats'])    # Rarity-specific stats
print(data['top_hits'])        # Top 10 cards
```

## Migration from Excel

The Excel export functionality (`append_summary_to_existing_excel`) is still available:
- Select option `2` to continue using Excel only
- Select option `3` to save to both database and Excel during transition

## Benefits

✅ **Historical Tracking** - Keep all simulation runs with timestamps  
✅ **Queryable Data** - SQL queries for analysis and reporting  
✅ **Referential Integrity** - Linked to sets table via foreign keys  
✅ **Atomic Saves** - All related data saved together  
✅ **Scalable** - No file size limitations like Excel  
✅ **API Ready** - Data readily available for web apps or APIs  

## Troubleshooting

### "Set not found in database"

**Cause**: The set doesn't exist in the `sets` table.

**Solution**: Run the scraper/ingest process first to create the set record, or manually insert the set:

```python
from db.services.sets_service import SetsService

service = SetsService()
set_id = service.get_or_create_set({
    'set': 'Stellar Crown',
    'abbreviation': 'STC',
    'era': 'Scarlet & Violet',
    'tcg': 'Pokemon',
    'release_date': '2024-09-13'
})
```

### Database Connection Issues

Check that:
1. `.env` file has correct Supabase credentials
2. Supabase project is active
3. Tables have been created using the schema file
4. Network connection is available

## Future Enhancements

Potential improvements:
- Add API endpoints to query simulation data
- Build dashboard to visualize historical simulations
- Add simulation comparison features
- Implement simulation versioning/snapshots
- Create data export utilities (CSV, JSON)

## Contact

For questions or issues, refer to the main project documentation or create an issue in the repository.
