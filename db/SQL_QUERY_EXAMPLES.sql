-- SQL Query Examples for Pack Simulation Data
-- Run these queries in Supabase SQL Editor or your PostgreSQL client

-- ============================================================================
-- BASIC QUERIES
-- ============================================================================

-- Get all simulations for a specific set
SELECT ps.*, s.name as set_name
FROM pack_simulations ps
JOIN sets s ON ps.set_id = s.id
WHERE s.name = 'Stellar Crown'
ORDER BY ps.created_at DESC;

-- Get latest simulation for each set
SELECT DISTINCT ON (s.name) 
    s.name as set_name,
    ps.simulated_ev,
    ps.pack_price,
    ps.opening_pack_roi_percent,
    ps.hit_probability_percentage,
    ps.created_at
FROM pack_simulations ps
JOIN sets s ON ps.set_id = s.id
ORDER BY s.name, ps.created_at DESC;

-- Get complete simulation data with all related tables
SELECT 
    ps.*,
    s.name as set_name,
    json_build_object(
        'statistics', (SELECT row_to_json(ss) FROM simulation_statistics ss WHERE ss.simulation_id = ps.id),
        'percentiles', (SELECT row_to_json(sp) FROM simulation_percentiles sp WHERE sp.simulation_id = ps.id),
        'ev_breakdown', (SELECT row_to_json(seb) FROM simulation_ev_breakdown seb WHERE seb.simulation_id = ps.id)
    ) as details
FROM pack_simulations ps
JOIN sets s ON ps.set_id = s.id
WHERE ps.id = 'your-simulation-id-here';

-- ============================================================================
-- ANALYTICS & COMPARISONS
-- ============================================================================

-- Compare EV across all sets (latest simulation for each)
SELECT DISTINCT ON (s.name)
    s.name as set_name,
    s.release_date,
    ps.simulated_ev,
    ps.pack_price,
    ps.opening_pack_roi_percent,
    ps.hit_probability_percentage
FROM pack_simulations ps
JOIN sets s ON ps.set_id = s.id
ORDER BY s.name, ps.created_at DESC;

-- Find most profitable sets (highest ROI)
SELECT DISTINCT ON (s.name)
    s.name as set_name,
    ps.opening_pack_roi_percent,
    ps.simulated_ev,
    ps.pack_price,
    ps.net_value
FROM pack_simulations ps
JOIN sets s ON ps.set_id = s.id
ORDER BY s.name, ps.created_at DESC
ORDER BY ps.opening_pack_roi_percent DESC;

-- Find sets with highest hit probability
SELECT DISTINCT ON (s.name)
    s.name as set_name,
    ps.hit_probability_percentage,
    ps.simulated_ev,
    ps.pack_price
FROM pack_simulations ps
JOIN sets s ON ps.set_id = s.id
ORDER BY s.name, ps.created_at DESC
ORDER BY ps.hit_probability_percentage DESC;

-- ============================================================================
-- TOP HITS ANALYSIS
-- ============================================================================

-- Get top 10 hits for a specific simulation
SELECT 
    sth.rank,
    sth.card_name,
    sth.price,
    sth.effective_pull_rate,
    s.name as set_name
FROM simulation_top_hits sth
JOIN pack_simulations ps ON sth.simulation_id = ps.id
JOIN sets s ON ps.set_id = s.id
WHERE ps.id = 'your-simulation-id-here'
ORDER BY sth.rank;

-- Find most valuable chase cards across all sets
SELECT 
    s.name as set_name,
    sth.card_name,
    sth.price,
    sth.effective_pull_rate,
    sth.rank
FROM simulation_top_hits sth
JOIN pack_simulations ps ON sth.simulation_id = ps.id
JOIN sets s ON ps.set_id = s.id
WHERE sth.rank = 1  -- Top card from each set
ORDER BY sth.price DESC;

-- ============================================================================
-- RARITY STATISTICS
-- ============================================================================

-- Get rarity breakdown for a specific simulation
SELECT 
    srs.rarity_name,
    srs.pull_count,
    srs.average_value,
    srs.total_value,
    s.name as set_name
FROM simulation_rarity_stats srs
JOIN pack_simulations ps ON srs.simulation_id = ps.id
JOIN sets s ON ps.set_id = s.id
WHERE ps.id = 'your-simulation-id-here'
ORDER BY srs.average_value DESC;

-- Compare rarity values across sets
SELECT 
    s.name as set_name,
    srs.rarity_name,
    srs.average_value,
    srs.pull_count
FROM simulation_rarity_stats srs
JOIN pack_simulations ps ON srs.simulation_id = ps.id
JOIN sets s ON ps.set_id = s.id
WHERE srs.rarity_name = 'hyper rare'
ORDER BY srs.average_value DESC;

-- ============================================================================
-- EV BREAKDOWN ANALYSIS
-- ============================================================================

-- Get detailed EV breakdown for a simulation
SELECT 
    s.name as set_name,
    seb.ev_common_total,
    seb.ev_uncommon_total,
    seb.ev_rare_total,
    seb.ev_ultra_rare_total,
    seb.ev_hyper_rare_total,
    seb.ev_illustration_rare_total,
    seb.ev_special_illustration_rare_total,
    seb.regular_pack_ev_contribution,
    seb.god_pack_ev_contribution,
    seb.demi_god_pack_ev_contribution
FROM simulation_ev_breakdown seb
JOIN pack_simulations ps ON seb.simulation_id = ps.id
JOIN sets s ON ps.set_id = s.id
WHERE ps.id = 'your-simulation-id-here';

-- Compare rare card EV contributions across sets
SELECT 
    s.name as set_name,
    seb.ev_ultra_rare_total,
    seb.ev_hyper_rare_total,
    seb.ev_special_illustration_rare_total,
    ps.simulated_ev as total_ev
FROM simulation_ev_breakdown seb
JOIN pack_simulations ps ON seb.simulation_id = ps.id
JOIN sets s ON ps.set_id = s.id
ORDER BY seb.ev_hyper_rare_total DESC;

-- ============================================================================
-- STATISTICAL ANALYSIS
-- ============================================================================

-- Get distribution statistics for a simulation
SELECT 
    s.name as set_name,
    ss.mean_value,
    ss.std_dev,
    ss.min_value,
    ss.max_value,
    sp.percentile_50th as median,
    sp.percentile_95th,
    sp.percentile_5th
FROM simulation_statistics ss
JOIN simulation_percentiles sp ON ss.simulation_id = sp.simulation_id
JOIN pack_simulations ps ON ss.simulation_id = ps.id
JOIN sets s ON ps.set_id = s.id
WHERE ps.id = 'your-simulation-id-here';

-- Compare variance across sets
SELECT 
    s.name as set_name,
    ss.mean_value,
    ss.std_dev,
    ss.std_dev / ss.mean_value as coefficient_of_variation,
    ps.pack_price
FROM simulation_statistics ss
JOIN pack_simulations ps ON ss.simulation_id = ps.id
JOIN sets s ON ps.set_id = s.id
ORDER BY coefficient_of_variation DESC;

-- ============================================================================
-- TIME-BASED ANALYSIS
-- ============================================================================

-- Track EV changes over time for a set
SELECT 
    ps.created_at,
    ps.simulated_ev,
    ps.pack_price,
    ps.opening_pack_roi_percent
FROM pack_simulations ps
JOIN sets s ON ps.set_id = s.id
WHERE s.name = 'Stellar Crown'
ORDER BY ps.created_at DESC;

-- Get simulations from last 30 days
SELECT 
    s.name as set_name,
    ps.simulated_ev,
    ps.pack_price,
    ps.created_at
FROM pack_simulations ps
JOIN sets s ON ps.set_id = s.id
WHERE ps.created_at >= NOW() - INTERVAL '30 days'
ORDER BY ps.created_at DESC;

-- ============================================================================
-- AGGREGATIONS & SUMMARIES
-- ============================================================================

-- Count simulations per set
SELECT 
    s.name as set_name,
    COUNT(ps.id) as simulation_count,
    MAX(ps.created_at) as latest_simulation
FROM sets s
LEFT JOIN pack_simulations ps ON s.id = ps.set_id
GROUP BY s.name
ORDER BY simulation_count DESC;

-- Average metrics across all simulations per set
SELECT 
    s.name as set_name,
    COUNT(ps.id) as num_simulations,
    AVG(ps.simulated_ev) as avg_ev,
    AVG(ps.opening_pack_roi_percent) as avg_roi,
    AVG(ps.hit_probability_percentage) as avg_hit_prob
FROM sets s
JOIN pack_simulations ps ON s.id = ps.set_id
GROUP BY s.name
ORDER BY avg_ev DESC;

-- ============================================================================
-- UTILITY QUERIES
-- ============================================================================

-- Delete all simulations for a set (use with caution!)
-- DELETE FROM pack_simulations 
-- WHERE set_id = (SELECT id FROM sets WHERE name = 'Set Name Here');

-- Delete old simulations (keep only latest per set)
-- DELETE FROM pack_simulations ps
-- WHERE ps.id NOT IN (
--     SELECT DISTINCT ON (set_id) id
--     FROM pack_simulations
--     ORDER BY set_id, created_at DESC
-- );

-- Get total storage used by simulation data
SELECT 
    pg_size_pretty(pg_total_relation_size('pack_simulations')) as pack_simulations_size,
    pg_size_pretty(pg_total_relation_size('simulation_statistics')) as statistics_size,
    pg_size_pretty(pg_total_relation_size('simulation_percentiles')) as percentiles_size,
    pg_size_pretty(pg_total_relation_size('simulation_rarity_stats')) as rarity_stats_size,
    pg_size_pretty(pg_total_relation_size('simulation_top_hits')) as top_hits_size,
    pg_size_pretty(pg_total_relation_size('simulation_ev_breakdown')) as ev_breakdown_size;

-- ============================================================================
-- ADVANCED: CREATE VIEWS FOR COMMON QUERIES
-- ============================================================================

-- View: Latest simulation for each set with key metrics
CREATE OR REPLACE VIEW latest_set_simulations AS
SELECT DISTINCT ON (s.name)
    s.id as set_id,
    s.name as set_name,
    s.release_date,
    ps.id as simulation_id,
    ps.simulated_ev,
    ps.pack_price,
    ps.net_value,
    ps.opening_pack_roi_percent,
    ps.hit_probability_percentage,
    ps.created_at as simulation_date
FROM pack_simulations ps
JOIN sets s ON ps.set_id = s.id
ORDER BY s.name, ps.created_at DESC;

-- View: Complete simulation summary with all stats
CREATE OR REPLACE VIEW simulation_summary AS
SELECT 
    ps.id as simulation_id,
    s.name as set_name,
    ps.simulated_ev,
    ps.pack_price,
    ps.opening_pack_roi_percent,
    ps.hit_probability_percentage,
    ss.mean_value,
    ss.std_dev,
    sp.percentile_50th as median,
    sp.percentile_95th,
    ps.created_at
FROM pack_simulations ps
JOIN sets s ON ps.set_id = s.id
LEFT JOIN simulation_statistics ss ON ps.id = ss.simulation_id
LEFT JOIN simulation_percentiles sp ON ps.id = sp.simulation_id;

-- Use views
SELECT * FROM latest_set_simulations WHERE set_name = 'Stellar Crown';
SELECT * FROM simulation_summary ORDER BY created_at DESC LIMIT 10;
