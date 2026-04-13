-- Create sealed_product_price_observations table
-- This table stores historical price tracking for sealed products

CREATE TABLE IF NOT EXISTS public.sealed_product_price_observations (
    id BIGSERIAL PRIMARY KEY,
    sealed_product_id BIGINT NOT NULL REFERENCES public.sealed_products(id) ON DELETE CASCADE,
    market_price DECIMAL(10, 2) NOT NULL,
    low_price DECIMAL(10, 2),
    source VARCHAR(255),
    currency VARCHAR(3) DEFAULT 'USD',
    captured_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create index for faster queries on sealed_product_id
CREATE INDEX IF NOT EXISTS idx_sealed_product_price_observations_sealed_product_id 
    ON public.sealed_product_price_observations(sealed_product_id);

-- Create index for faster queries on captured_at for historical lookups
CREATE INDEX IF NOT EXISTS idx_sealed_product_price_observations_captured_at 
    ON public.sealed_product_price_observations(captured_at DESC);

-- Enable RLS (Row Level Security) - this allows PostgREST to access the table
ALTER TABLE public.sealed_product_price_observations ENABLE ROW LEVEL SECURITY;

-- Create a policy allowing all authenticated users to read sealed_product_price_observations
CREATE POLICY sealed_product_price_observations_read_policy
    ON public.sealed_product_price_observations
    FOR SELECT
    USING (true);

-- Create a policy allowing all authenticated users to insert sealed_product_price_observations
CREATE POLICY sealed_product_price_observations_insert_policy
    ON public.sealed_product_price_observations
    FOR INSERT
    WITH CHECK (true);
