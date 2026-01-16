-- Schema for Pack Simulation Results
-- These tables store the results of Monte Carlo pack simulations and EV calculations

-- Main simulation record - one per set/pack calculation run
CREATE TABLE IF NOT EXISTS pack_simulations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    set_id UUID NOT NULL REFERENCES sets(id) ON DELETE CASCADE,
    
    -- Manual calculation results
    total_manual_ev DECIMAL(10, 4) NOT NULL,
    
    -- Simulated results
    simulated_ev DECIMAL(10, 4) NOT NULL,
    
    -- Pack pricing and ROI
    pack_price DECIMAL(10, 2) NOT NULL,
    net_value DECIMAL(10, 4) NOT NULL,
    opening_pack_roi DECIMAL(10, 4) NOT NULL,
    opening_pack_roi_percent DECIMAL(10, 4) NOT NULL,
    
    -- Hit probabilities
    hit_probability_percentage DECIMAL(10, 4),
    no_hit_probability_percentage DECIMAL(10, 4),
    
    -- Metadata
    simulation_count INTEGER DEFAULT 100000,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- EV breakdown by rarity and calculation type
CREATE TABLE IF NOT EXISTS simulation_ev_breakdown (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    simulation_id UUID NOT NULL REFERENCES pack_simulations(id) ON DELETE CASCADE,
    
    -- Rarity-based EV totals
    ev_common_total DECIMAL(10, 6),
    ev_uncommon_total DECIMAL(10, 6),
    ev_rare_total DECIMAL(10, 6),
    ev_reverse_total DECIMAL(10, 6),
    ev_ace_spec_total DECIMAL(10, 6),
    ev_pokeball_total DECIMAL(10, 6),
    ev_master_ball_total DECIMAL(10, 6),
    ev_illustration_rare_total DECIMAL(10, 6),
    ev_special_illustration_rare_total DECIMAL(10, 6),
    ev_double_rare_total DECIMAL(10, 6),
    ev_hyper_rare_total DECIMAL(10, 6),
    ev_ultra_rare_total DECIMAL(10, 6),
    
    -- Multipliers used
    reverse_multiplier DECIMAL(10, 6),
    rare_multiplier DECIMAL(10, 6),
    
    -- Special pack contributions
    regular_pack_ev_contribution DECIMAL(10, 6),
    god_pack_ev_contribution DECIMAL(10, 6),
    demi_god_pack_ev_contribution DECIMAL(10, 6),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Statistical summary of simulation results
CREATE TABLE IF NOT EXISTS simulation_statistics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    simulation_id UUID NOT NULL REFERENCES pack_simulations(id) ON DELETE CASCADE,
    
    -- Core statistics
    mean_value DECIMAL(10, 4) NOT NULL,
    std_dev DECIMAL(10, 4) NOT NULL,
    min_value DECIMAL(10, 4) NOT NULL,
    max_value DECIMAL(10, 4) NOT NULL,
    
    -- Variance metrics (optional if calculated)
    variance DECIMAL(10, 6),
    weighted_variance DECIMAL(10, 6),
    weighted_stddev DECIMAL(10, 6),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(simulation_id)
);

-- Percentile data from simulation
CREATE TABLE IF NOT EXISTS simulation_percentiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    simulation_id UUID NOT NULL REFERENCES pack_simulations(id) ON DELETE CASCADE,
    
    percentile_5th DECIMAL(10, 4),
    percentile_25th DECIMAL(10, 4),
    percentile_50th DECIMAL(10, 4),  -- median
    percentile_75th DECIMAL(10, 4),
    percentile_90th DECIMAL(10, 4),
    percentile_95th DECIMAL(10, 4),
    percentile_99th DECIMAL(10, 4),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(simulation_id)
);

-- Rarity-specific pull statistics from simulation
CREATE TABLE IF NOT EXISTS simulation_rarity_stats (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    simulation_id UUID NOT NULL REFERENCES pack_simulations(id) ON DELETE CASCADE,
    
    rarity_name TEXT NOT NULL,  -- e.g., 'common', 'rare', 'hyper rare', etc.
    pull_count INTEGER NOT NULL,  -- total times this rarity was pulled across all simulations
    total_value DECIMAL(10, 4) NOT NULL,  -- total $ value from this rarity across all simulations
    average_value DECIMAL(10, 4) NOT NULL,  -- average value per pull for this rarity
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(simulation_id, rarity_name)
);

-- Top hit cards tracked for each simulation
CREATE TABLE IF NOT EXISTS simulation_top_hits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    simulation_id UUID NOT NULL REFERENCES pack_simulations(id) ON DELETE CASCADE,
    
    card_name TEXT NOT NULL,
    price DECIMAL(10, 2) NOT NULL,
    effective_pull_rate DECIMAL(12, 8),  -- probability of pulling this card
    rank INTEGER NOT NULL,  -- ranking (1-10 for top 10)
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(simulation_id, rank)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_pack_simulations_set_id ON pack_simulations(set_id);
CREATE INDEX IF NOT EXISTS idx_pack_simulations_created_at ON pack_simulations(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_simulation_ev_breakdown_simulation_id ON simulation_ev_breakdown(simulation_id);
CREATE INDEX IF NOT EXISTS idx_simulation_statistics_simulation_id ON simulation_statistics(simulation_id);
CREATE INDEX IF NOT EXISTS idx_simulation_percentiles_simulation_id ON simulation_percentiles(simulation_id);
CREATE INDEX IF NOT EXISTS idx_simulation_rarity_stats_simulation_id ON simulation_rarity_stats(simulation_id);
CREATE INDEX IF NOT EXISTS idx_simulation_top_hits_simulation_id ON simulation_top_hits(simulation_id);
