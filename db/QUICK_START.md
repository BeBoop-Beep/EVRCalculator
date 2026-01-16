# Quick Start Guide - Database Simulation Persistence

## Setup (One-Time)

### 1. Create Database Tables

Open Supabase SQL Editor and run:
```sql
-- Copy entire contents of db/schemas/simulation_tables_schema.sql
```

This creates 6 tables:
- `pack_simulations`
- `simulation_ev_breakdown`
- `simulation_statistics`
- `simulation_percentiles`
- `simulation_rarity_stats`
- `simulation_top_hits`

### 2. Verify Environment

Ensure `.env` has:
```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_key_here
```

## Usage Examples

### Running the Calculator

```bash
# Navigate to calculator directory
cd "Expected Value and Cost Ratio Calculator Pokemon"

# Run the calculator
python main.py
```

**Interactive prompts:**
```
What set are we working on: 
> stellar crown

Save results to (1) Database, (2) Excel, or (3) Both? [default: 1]: 
> 1
```

### Programmatic Access

```python
from db.controllers.simulation_controller import SimulationController

controller = SimulationController()

# Save simulation
simulation_id = controller.save_pack_simulation(
    set_name="Stellar Crown",
    results=results,
    summary_data=summary_data,
    sim_results=sim_results,
    top_10_hits=top_10_hits
)

# Get simulation by ID
data = controller.get_simulation(simulation_id)

# Get latest for a set
latest = controller.get_latest_simulation_for_set("Stellar Crown")
```

### Direct Repository Access

```python
from db.repositories.pack_simulations_repository import (
    get_simulations_by_set_id,
    get_latest_simulation_by_set_id
)
from db.repositories.sets_repository import get_set_id_by_name

# Get set ID
set_id = get_set_id_by_name("Stellar Crown")

# Get all simulations for set
simulations = get_simulations_by_set_id(set_id)

# Get just the latest
latest = get_latest_simulation_by_set_id(set_id)
```

## Data Structure

### Simulation Record

```python
simulation = {
    'id': 'uuid',
    'set_id': 'uuid',
    'total_manual_ev': 2.45,
    'simulated_ev': 2.43,
    'pack_price': 4.00,
    'net_value': -1.57,
    'opening_pack_roi': -1.57,
    'opening_pack_roi_percent': -39.25,
    'hit_probability_percentage': 23.4,
    'no_hit_probability_percentage': 76.6,
    'simulation_count': 100000,
    'created_at': '2024-01-15T...'
}
```

### Complete Simulation Data

```python
complete_data = {
    'simulation': {...},        # Main record
    'ev_breakdown': {...},      # EV by rarity
    'statistics': {...},        # Mean, std dev, etc.
    'percentiles': {...},       # Distribution percentiles
    'rarity_stats': [{...}],    # List of rarity stats
    'top_hits': [{...}]         # List of top 10 cards
}
```

## Common Tasks

### Save Simulation from Code

```python
from db.controllers.simulation_controller import SimulationController

# After running calculate_pack_stats()
results, summary_data, total_ev, sim_results, top_10_hits = calculate_pack_stats(file_path, config)

# Save to DB
controller = SimulationController()
sim_id = controller.save_pack_simulation(
    set_name=config.SET_NAME,
    results=results,
    summary_data=summary_data,
    sim_results=sim_results,
    top_10_hits=top_10_hits
)
```

### Query Historical Data

```python
from db.repositories.pack_simulations_repository import get_simulations_by_set_id
from db.repositories.sets_repository import get_set_id_by_name

set_id = get_set_id_by_name("Stellar Crown")
all_simulations = get_simulations_by_set_id(set_id)

# Sort by date
for sim in all_simulations.data:
    print(f"{sim['created_at']}: EV = ${sim['simulated_ev']}")
```

### Export to Excel (Legacy)

```python
from src.printEvCalculations import append_summary_to_existing_excel

# Still works!
append_summary_to_existing_excel(
    file_path, 
    summary_data, 
    results, 
    sim_results, 
    top_10_hits
)
```

## Troubleshooting

### Error: "Set not found in database"

**Problem:** Set doesn't exist in `sets` table.

**Solution:**
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

### Error: "Table does not exist"

**Problem:** Database tables not created.

**Solution:** Run the SQL schema in Supabase SQL editor.

### Error: "No Supabase connection"

**Problem:** Missing or invalid environment variables.

**Solution:** Check `.env` file has valid `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`.

## API Reference

### SimulationController

```python
class SimulationController:
    def save_pack_simulation(set_name, results, summary_data, sim_results, top_10_hits)
        # Returns: simulation_id (str) or None
    
    def get_simulation(simulation_id)
        # Returns: dict with all simulation data
    
    def get_latest_simulation_for_set(set_name)
        # Returns: dict with latest simulation data
```

### SimulationService

```python
class SimulationService:
    def save_simulation_results(set_id, results, summary_data, sim_results, top_10_hits)
        # Returns: simulation_id (str)
    
    def get_simulation_with_all_data(simulation_id)
        # Returns: dict with complete simulation
```

## File Locations

```
db/
├── schemas/
│   └── simulation_tables_schema.sql     # SQL schema
├── repositories/
│   ├── pack_simulations_repository.py
│   ├── simulation_ev_breakdown_repository.py
│   ├── simulation_statistics_repository.py
│   ├── simulation_percentiles_repository.py
│   ├── simulation_rarity_stats_repository.py
│   └── simulation_top_hits_repository.py
├── services/
│   └── simulation_service.py            # Business logic
├── controllers/
│   └── simulation_controller.py         # High-level API
└── README_SIMULATION_DB.md              # Full documentation
```

## Tips

1. **Always use controller** - Prefer `SimulationController` over direct repository access
2. **Set must exist** - Ensure set is in database before saving simulation
3. **Excel still works** - Use option `2` or `3` if you want Excel files
4. **Check errors** - Service provides detailed error messages
5. **Transactions** - All 6 tables saved atomically

## Next Steps

1. ✅ Create tables in Supabase
2. ✅ Test with one set
3. ✅ Verify data in database
4. ✅ Build on top (dashboards, APIs, reports)

For complete documentation, see `db/README_SIMULATION_DB.md`.
