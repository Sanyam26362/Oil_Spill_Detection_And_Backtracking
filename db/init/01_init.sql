-- db/init/01_init.sql
-- Enable PostGIS extension for geospatial data
CREATE EXTENSION IF NOT EXISTS postgis;
-- Enable topology (optional but good for advanced routing/attribution)
CREATE EXTENSION IF NOT EXISTS postgis_topology;