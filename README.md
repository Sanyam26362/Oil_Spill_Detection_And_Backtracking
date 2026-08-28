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
   ```

## Folder Structure

```text
oil-spill-backend/
├── .dockerignore
├── .env
├── .gitignore
├── Dockerfile
├── README.md
├── app
│   ├── __init__.py
│   ├── core
│   │   ├── __init__.py
│   │   ├── config.py
│   │   └── database.py
│   ├── main.py
│   ├── models
│   │   ├── __init__.py
│   │   ├── ais.py
│   │   ├── attribution.py
│   │   ├── drift.py
│   │   ├── schemas.py
│   │   └── spill.py
│   ├── repositories
│   │   ├── __init__.py
│   │   ├── ais_repository.py
│   │   ├── attribution_repository.py
│   │   └── spill_repository.py
│   ├── routers
│   │   ├── __init__.py
│   │   ├── attribution.py
│   │   ├── drift.py
│   │   └── spills.py
│   ├── services
│   │   ├── __init__.py
│   │   ├── attribution_engine.py
│   │   ├── drift_engine.py
│   │   ├── scoring_engine.py
│   │   ├── spill_service.py
│   │   ├── trajectory_service.py
│   │   └── weather_service.py
│   └── utils
│       ├── __init__.py
│       └── geo_helpers.py
├── data
│   ├── ais
│   │   ├── processed
│   │   │   ├── synthetic_ais_test.csv
│   │   │   └── synthetic_ground_truth.json
│   │   └── raw
│   │       └── piraeus
│   │           ├── ais_static.zip
│   │           ├── dynamic
│   │           │   ├── README.md
│   │           │   ├── unipi_ais_dynamic_apr2019.csv
│   │           │   ├── unipi_ais_dynamic_aug2019.csv
│   │           │   ├── unipi_ais_dynamic_dec2019.csv
│   │           │   ├── unipi_ais_dynamic_feb2019.csv
│   │           │   ├── unipi_ais_dynamic_jan2019.csv
│   │           │   ├── unipi_ais_dynamic_jul2019.csv
│   │           │   ├── unipi_ais_dynamic_jun2019.csv
│   │           │   ├── unipi_ais_dynamic_mar2019.csv
│   │           │   ├── unipi_ais_dynamic_may2019.csv
│   │           │   ├── unipi_ais_dynamic_nov2019.csv
│   │           │   ├── unipi_ais_dynamic_oct2019.csv
│   │           │   └── unipi_ais_dynamic_sep2019.csv
│   │           ├── static
│   │           │   ├── README.md
│   │           │   └── ais_static
│   │           │       ├── ais_codes_descriptions.csv
│   │           │       └── unipi_ais_static.csv
│   │           └── unipi_ais_dynamic_2019.zip
│   ├── ml
│   │   └── detections
│   ├── ocean
│   │   ├── processed
│   │   └── raw
│   │       └── med_currents_2019-07-event.nc
│   └── weather
│       ├── cmems
│       ├── era5
│       ├── processed
│       └── raw
│           └── era5_wind_2019-07-event.nc
├── db
│   └── init
│       └── 01_init.sql
├── docker-compose.yml
├── requirements.txt
├── scripts
│   ├── __init__.py
│   ├── analyze_piraeus_ais.py
│   ├── analyze_vessel_behavior.py
│   ├── attribution
│   │   ├── __init__.py
│   │   └── score_candidates.py
│   ├── ingest_piraeus_ais.py
│   ├── synthetic
│   │   ├── __init__.py
│   │   ├── generate_synthetic_ais.py
│   │   └── scenario.py
│   └── weather
│       └── download_era5.py
└── test_app.py
```