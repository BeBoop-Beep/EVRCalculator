# Validation and Regression Test Report (Subagent 5)

Date: 2026-04-18
Scope: Focused validation for EV math/output/persistence regressions.

## Added/Updated Tests

- reverse EV formula correctness and scaling
  - `backend/tests/unit/calculations/test_reverse_ev_math.py`
- total EV aggregation sanity + comparison payload/output blocks
  - `backend/tests/unit/jobs/test_evr_runner_output_metrics.py`
- single percentile section behavior in simulation summary output
  - `backend/tests/unit/simulations/test_monte_carlo_sim_v2.py`
- percentile label validity for persistence path parsing/inserts
  - `backend/tests/unit/db/repositories/test_calculation_runs_repository.py`

## Focused Commands

```bash
cd /d/EVRCalculator && C:/Users/Owner/AppData/Local/Programs/Python/Python311/python.exe -m pytest backend/tests/unit/calculations/test_reverse_ev_math.py backend/tests/unit/jobs/test_evr_runner_output_metrics.py backend/tests/unit/simulations/test_monte_carlo_sim_v2.py backend/tests/unit/db/repositories/test_calculation_runs_repository.py -q ; echo EXIT_CODE:$?
```

Result: `1 failed, 20 passed` (includes unrelated pre-existing failure in `test_actual_prismatic_fixed_config_supports_name_only_master_ball_entry_in_v2`).

```bash
cd /d/EVRCalculator && C:/Users/Owner/AppData/Local/Programs/Python/Python311/python.exe -m pytest backend/tests/unit/calculations/test_reverse_ev_math.py backend/tests/unit/jobs/test_evr_runner_output_metrics.py backend/tests/unit/simulations/test_monte_carlo_sim_v2.py::test_pull_summary_v2_prints_high_precision_avg_and_clear_total_label backend/tests/unit/simulations/test_monte_carlo_sim_v2.py::test_print_simulation_summary_v2_handles_single_percentile_section backend/tests/unit/simulations/test_monte_carlo_sim_v2.py::test_pull_summary_v1_and_v2_displayed_avg_matches_total_sampled_value backend/tests/unit/db/repositories/test_calculation_runs_repository.py -q ; echo EXIT_CODE:$?
```

Result: `23 passed, 0 failed`.
