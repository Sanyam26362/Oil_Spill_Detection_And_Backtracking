# Oil Spill & Vessel Attribution Backend

This is the backend engine for the NTRO oil spill detection challenge. It handles drift hindcasting/forecasting (using ocean currents/winds) and AIS vessel spatio-temporal correlation.

## Tech Stack
* **Framework:** FastAPI (Python 3.11)
* **Geospatial Math:** GeoPandas, Xarray, Shapely
* **Database:** PostgreSQL 15 + PostGIS

## How to Run Locally

1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/).
2. Ask the backend lead for the `.env` file and place it in the root directory.
3. Open your terminal in this directory and run:
   ```bash
   docker compose up --build