-- db/init/02_ais_indexes.sql
-- Missing performance indexes on ais_positions for scenario filtering and spatial candidates

-- Partial GiST index on geometry for synthetic AIS positions
CREATE INDEX IF NOT EXISTS idx_ais_positions_geometry_synthetic
ON ais_positions USING GIST (geometry)
WHERE is_synthetic = true;

-- Composite index on (scenario_id, timestamp) for scenario queries
CREATE INDEX IF NOT EXISTS idx_ais_positions_scenario_timestamp
ON ais_positions (scenario_id, timestamp);
