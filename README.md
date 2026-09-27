# 🛢️ Oil Spill Detection & Vessel Attribution Backend

> **SIH (Smart India Hackathon) — NTRO Oil Spill Detection Challenge**
> A production-ready FastAPI backend for SAR-based oil spill detection, physics-driven drift hindcasting/forecasting, and AIS spatio-temporal vessel attribution.

---

## 📋 Table of Contents

- [Overview](#-overview)
- [System Architecture](#-system-architecture)
- [Core Pipeline](#-core-pipeline)
- [Tech Stack](#-tech-stack)
- [Project Structure](#-project-structure)
- [API Reference](#-api-reference)
- [Getting Started](#-getting-started)
  - [Prerequisites](#prerequisites)
  - [Environment Variables](#environment-variables)
  - [Run with Docker (Recommended)](#run-with-docker-recommended)
  - [Run Locally (Without Docker)](#run-locally-without-docker)
- [Data Requirements](#-data-requirements)
- [Key Services](#-key-services)
- [Scoring Model](#-scoring-model)
- [Testing](#-testing)
- [Scripts & Tooling](#-scripts--tooling)
- [Configuration](#-configuration)
- [Docker Details](#-docker-details)
- [Database Schema](#-database-schema)
- [Contributing](#-contributing)

---

## 🌊 Overview

This backend powers a maritime oil spill response system. When a satellite SAR (Synthetic Aperture Radar) image detects an oil slick at sea, this system answers two critical questions:

1. **Where did the spill originate?** — by backward-hindcasting the slick's drift using real-world ERA5 wind and CMEMS ocean current NetCDF data.
2. **Which vessel caused it?** — by cross-correlating the estimated spill source location and time against AIS (Automatic Identification System) vessel position records stored in PostGIS.

The system supports both real-world Piraeus AIS data (2019) and fully synthetic AIS scenario generation for controlled evaluation.

---

## 🏗️ System Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                        FastAPI Application                           │
│                                                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌────────────┐  ┌────────────┐  │
│  │  /drift     │  │ /attribution│  │ /spills    │  │/demo/spills│  │
│  │  endpoints  │  │  endpoints  │  │  endpoints │  │  endpoints │  │
│  └──────┬──────┘  └──────┬──────┘  └─────┬──────┘  └─────┬──────┘  │
│         │                │               │               │          │
│  ┌──────▼──────────────────────────────────────────────────────┐    │
│  │                     Service Layer                           │    │
│  │  DriftEngine  │  HindcastService  │  AttributionEngine      │    │
│  │  ScoringEngine│  WeatherService   │  SpillCatalogService    │    │
│  └──────┬────────────────────┬──────────────────────┬──────────┘    │
│         │                    │                      │               │
│  ┌──────▼──────┐    ┌────────▼────────┐    ┌────────▼──────────┐   │
│  │ ERA5 + CMEMS│    │  PostGIS / AIS  │    │  json_output/     │   │
│  │ NetCDF Data │    │  PostgreSQL 15  │    │  Detection Catalog│   │
│  └─────────────┘    └─────────────────┘    └───────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

---

## ⚙️ Core Pipeline

The end-to-end attribution pipeline runs as follows:

```
SAR Observation (lat, lon, timestamp)
        │
        ▼
[1] Backward Ensemble Hindcast
        │  DriftEngine: ocean_current + windage × wind_velocity
        │  100-particle Monte Carlo ensemble → source centroid + radius
        ▼
[2] PostGIS Candidate Search
        │  ST_DWithin query: vessels within radius_km of source centroid
        │  Time window: ±2h around estimated release time
        ▼
[3] AIS Trajectory Retrieval
        │  Fetch full track for each candidate vessel
        ▼
[4] Behavioral Scoring (ScoringEngine)
        │  Proximity · Temporal · Slowdown · Loiter · Approach · Departure
        ▼
[5] Ranked Vessel Candidates
        └─► top_prediction (most likely polluter)
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **API Framework** | [FastAPI](https://fastapi.tiangolo.com/) 0.110.0 + [Uvicorn](https://www.uvicorn.org/) 0.28.0 |
| **Language** | Python 3.11 |
| **Data Validation** | [Pydantic](https://docs.pydantic.dev/) v2.6.4 + pydantic-settings |
| **Database** | [PostgreSQL 15](https://www.postgresql.org/) + [PostGIS 3.4](https://postgis.net/) |
| **ORM** | [SQLAlchemy](https://www.sqlalchemy.org/) 2.0 (async) + asyncpg |
| **Geospatial** | [GeoPandas](https://geopandas.org/) 0.14, [Shapely](https://shapely.readthedocs.io/) 2.0, [GeoAlchemy2](https://geoalchemy-2.readthedocs.io/) |
| **Metocean Data** | [Xarray](https://xarray.pydata.org/) + [NetCDF4](https://unidata.github.io/netcdf4-python/) + [SciPy](https://scipy.org/) |
| **Numerics** | [NumPy](https://numpy.org/) 1.26, Pandas |
| **Containerization** | [Docker](https://www.docker.com/) + Docker Compose (multi-stage build) |
| **Image Storage** | [Cloudinary](https://cloudinary.com/) (diagnostic SAR plots) |
| **Testing** | [pytest](https://pytest.org/) 8.1 + pytest-asyncio |

---

## 📁 Project Structure

```text
oil-spill-backend/
├── .env                          # Environment config (not committed)
├── .dockerignore
├── .gitignore
├── Dockerfile                    # Multi-stage build (builder → lean runner)
├── docker-compose.yml            # PostGIS + FastAPI services
├── requirements.txt              # Production dependencies
├── requirements-dev.txt          # Dev/test dependencies
├── pytest.ini
│
├── app/                          # Main FastAPI application
│   ├── main.py                   # App factory, lifespan, CORS, router mounts
│   ├── core/
│   │   ├── config.py             # Pydantic settings (DATABASE_URL, API keys)
│   │   └── database.py           # Async SQLAlchemy engine + session factory
│   │
│   ├── models/                   # SQLAlchemy ORM models
│   │   ├── ais.py                # AISPosition, Vessel
│   │   ├── spill.py              # OilSpillDetection
│   │   ├── drift.py              # DriftTrajectory, ParticleState (dataclasses)
│   │   └── schemas.py            # Pydantic response schemas
│   │
│   ├── repositories/             # Async database access layer
│   │   ├── ais_repository.py     # PostGIS candidate + trajectory queries
│   │   ├── attribution_repository.py
│   │   └── spill_repository.py
│   │
│   ├── routers/                  # API route handlers
│   │   ├── drift.py              # Forward drift, hindcast, predict, diagnostic plot
│   │   ├── attribution.py        # Vessel attribution endpoint
│   │   ├── spills.py             # ML pipeline ingestion
│   │   ├── demo_spills.py        # Demo catalog, vessel evidence
│   │   └── visualization.py      # Visualization API
│   │
│   ├── services/                 # Core business logic
│   │   ├── drift_engine.py       # Particle tracking (forward + backward, ensemble)
│   │   ├── hindcast_service.py   # Backward ensemble → source estimate
│   │   ├── weather_service.py    # ERA5 wind + CMEMS current NetCDF loader
│   │   ├── attribution_engine.py # Full attribution orchestrator
│   │   ├── scoring_engine.py     # Behavioral scoring (6 sub-scores)
│   │   ├── spill_catalog_service.py  # In-memory spill catalog
│   │   ├── visualization_service.py  # Plot generation
│   │   └── mock_vessel_service.py    # Mock AIS for demo/testing
│   │
│   └── utils/
│       └── geo_helpers.py
│
├── data/                         # Runtime data (gitignored, Docker volume)
│   ├── ais/
│   │   ├── raw/piraeus/          # Piraeus AIS dynamic (Jan–Dec 2019 CSVs)
│   │   └── processed/            # synthetic_ais_test.csv, ground_truth.json
│   ├── weather/
│   │   └── raw/yearly/           # ERA5 wind NetCDF (era5_wind_YYYY-*.nc)
│   └── ocean/
│       └── raw/yearly/           # CMEMS currents NetCDF (med_currents_YYYY-*.nc)
│
├── db/
│   └── init/
│       └── 01_init.sql           # PostGIS schema bootstrap
│
├── json_output/                  # Generated detection artifacts (gitignored)
│   └── validation/
│       ├── detection_attribution_results.csv
│       └── diagnostic_plot_urls.json
│
├── scripts/                      # Standalone ingestion & analysis tools
│   ├── ingest_piraeus_ais.py     # Bulk-load Piraeus AIS CSVs → PostGIS
│   ├── ingest_ml_outputs.py      # Ingest ML detection JSON → catalog
│   ├── ingest_synthetic_ais.py   # Load synthetic AIS scenarios
│   ├── run_scenario_001..005.py  # End-to-end scenario runners
│   ├── diagnose_detections.py    # Diagnostic report over all spills
│   ├── analyze_vessel_behavior.py
│   ├── validate_2019_synthetic_ais.py
│   ├── synthetic/
│   │   ├── generate_synthetic_ais.py
│   │   └── scenario.py
│   ├── attribution/
│   │   └── score_candidates.py
│   └── weather/
│       └── download_era5.py      # Pull ERA5 data via CDSAPI
│
├── tests/                        # pytest test suite
│   ├── conftest.py
│   ├── test_drift_engine.py
│   ├── test_hindcast_service.py
│   ├── test_scoring_engine.py
│   ├── test_attribution_integrity.py
│   ├── test_synthetic_ais.py
│   ├── test_scenario_002_attribution.py
│   ├── test_scenario_003_*.py    # Comprehensive scenario 003 coverage
│   ├── test_weather_service.py
│   ├── test_visualization_api.py
│   └── ...
│
└── docs/
    ├── implementation_plan.md
    └── implementation_verification_report.md
```

---

## 🔌 API Reference

Base URL: `http://localhost:8000`
OpenAPI Docs: `http://localhost:8000/docs`
ReDoc: `http://localhost:8000/redoc`

### System

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Liveness check — returns `{"status": "ok"}` |
| `GET` | `/health/ready` | Readiness check — verifies DB connectivity |

### Drift Modeling (`/api/v1/drift`)

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/drift/forward` | Forward drift from a given position and time |
| `POST` | `/api/v1/drift/hindcast` | Backward ensemble hindcast → source centroid |
| `GET` | `/api/v1/drift/predict/{spill_id}` | Forecast future spill location by ID |
| `GET` | `/api/v1/drift/{spill_id}/diagnostic-plot` | Cloudinary SAR diagnostic plot URL |

#### `POST /api/v1/drift/forward` — Request Body
```json
{
  "start_latitude": 36.5,
  "start_longitude": 28.3,
  "start_time": "2019-07-15T12:00:00Z",
  "duration_hours": 6.0
}
```

#### `POST /api/v1/drift/hindcast` — Request Body
```json
{
  "obs_latitude": 36.5,
  "obs_longitude": 28.3,
  "obs_time": "2019-07-15T18:00:00Z",
  "duration_hours": 6.0,
  "ensemble_size": 100
}
```

#### `GET /api/v1/drift/predict/{spill_id}` — Query Parameters

| Param | Default | Description |
|---|---|---|
| `hours` | `6.0` | Forecast horizon (max 72h) |
| `timestep_minutes` | `15` | Trajectory waypoint interval |

### Vessel Attribution (`/api/v1/attribution`)

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/attribution` | Full end-to-end vessel attribution |

#### Request Body
```json
{
  "observation_latitude": 36.5,
  "observation_longitude": 28.3,
  "observation_time": "2019-07-15T18:00:00Z",
  "drift_duration_hours": 6.0,
  "synthetic_only": true,
  "scenario_id": "scenario_003"
}
```

#### Response
```json
{
  "source_estimate": {
    "latitude": 36.42,
    "longitude": 28.18,
    "radius_km": 4.7
  },
  "estimated_release_time": "2019-07-15T12:00:00+00:00",
  "candidate_count": 5,
  "top_prediction": "VESSEL_XYZ",
  "candidates": [
    {
      "vessel_id": "VESSEL_XYZ",
      "score": 0.7821,
      "proximity_score": 0.94,
      "temporal_score": 0.88,
      "slowdown_score": 0.72,
      "loiter_score": 0.65,
      "approach_score": 0.80,
      "departure_score": 0.75,
      "closest_distance_km": 0.31,
      "minimum_event_speed_knots": 1.2
    }
  ]
}
```

### ML Pipeline Ingestion (`/api/v1/spills`)

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/spills` | Ingest oil spill detection from ML pipeline |
| `GET` | `/api/v1/spills` | List all ingested spill detections |
| `GET` | `/api/v1/spills/{spill_id}` | Get a single spill record |

### Demo API (`/api/v1/demo/spills`)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/demo/spills` | List all demo spill catalog entries |
| `GET` | `/api/v1/demo/spills/{spill_id}` | Get demo spill detail |
| `GET` | `/api/v1/demo/spills/{spill_id}/vessel-evidence` | AIS vessel evidence for a spill |

### Visualization (`/api/v1/visualization`)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/visualization/{spill_id}` | Get visualization data for a spill |

---

## 🚀 Getting Started

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) ≥ 4.x
- OR: Python 3.11, PostgreSQL 15 + PostGIS 3.4 (for local dev without Docker)

### Environment Variables

Create a `.env` file in the project root (ask the backend lead for credentials, or use the template below):

```env
# PostgreSQL
POSTGRES_USER=sih_admin
POSTGRES_PASSWORD=your_secure_password
POSTGRES_DB=oil_spill_db
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# Full DSN override (takes precedence when set)
DATABASE_URL=postgresql+asyncpg://sih_admin:your_secure_password@localhost:5432/oil_spill_db

# App
APP_HOST=0.0.0.0
APP_PORT=8000
ENVIRONMENT=development
API_V1_PREFIX=/api/v1

# Geospatial
TARGET_REGION=EASTERN_MEDITERRANEAN
DEFAULT_CRS=EPSG:4326

# Copernicus Climate Data Store (ERA5 wind downloads)
CDSAPI_URL=https://cds.climate.copernicus.eu/api
CDSAPI_KEY=your_cds_api_key

# Cloudinary (diagnostic plot hosting)
CLOUDINARY_CLOUD_NAME=your_cloud_name
CLOUDINARY_API_KEY=your_api_key
CLOUDINARY_API_SECRET=your_api_secret
```

> ⚠️ **Never commit `.env` to version control.** It is listed in `.gitignore`.

### Run with Docker (Recommended)

```bash
# 1. Clone the repository
git clone https://github.com/your-org/oil-spill-backend.git
cd oil-spill-backend

# 2. Place your .env file in the root directory

# 3. Start PostGIS + FastAPI
docker compose up --build

# API is now live at http://localhost:8000
# Docs at http://localhost:8000/docs
```

To run in detached mode:
```bash
docker compose up -d --build
```

To view logs:
```bash
docker compose logs -f api
```

To stop:
```bash
docker compose down
```

### Run Locally (Without Docker)

> Requires PostgreSQL 15 + PostGIS installed locally.

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

# 2. Install production dependencies
pip install -r requirements.txt

# 3. Bootstrap the database schema
psql -U sih_admin -d oil_spill_db -f db/init/01_init.sql

# 4. Start the development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## 📦 Data Requirements

Several runtime data paths are **excluded from version control** (`.gitignore`) due to size. They must be present (or Docker-volume-mounted) for full functionality.

### 1. `json_output/` — Detection Catalog

| Field | Value |
|---|---|
| **Purpose** | Loaded by `SpillCatalogService` for demo endpoints and diagnostic plot URL lookups |
| **Key files** | `json_output/validation/detection_attribution_results.csv`, `json_output/validation/diagnostic_plot_urls.json` |
| **How to generate** | Run `scripts/ingest_ml_outputs.py` or a synthetic scenario generator |
| **Docker mount** | `./json_output:/app/json_output:ro` |

### 2. `data/weather/raw/yearly/` — ERA5 Wind (NetCDF)

| Field | Value |
|---|---|
| **Purpose** | `WeatherService` reads 10 m u/v wind velocity vectors for drift integration |
| **File pattern** | `era5_wind_YYYY-MM-*.nc` |
| **How to obtain** | Run `scripts/weather/download_era5.py` (requires `CDSAPI_KEY`) |
| **Docker mount** | `./data:/app/data:ro` |

### 3. `data/ocean/raw/yearly/` — CMEMS Ocean Currents (NetCDF)

| Field | Value |
|---|---|
| **Purpose** | `WeatherService` reads eastward/northward surface current vectors |
| **File pattern** | `med_currents_YYYY-MM-*.nc` |
| **How to obtain** | Download from [Copernicus Marine Service](https://marine.copernicus.eu/) |
| **Docker mount** | `./data:/app/data:ro` |

### 4. `data/ais/raw/piraeus/` — Piraeus AIS (2019)

| Field | Value |
|---|---|
| **Purpose** | Real-world AIS vessel tracks for the Eastern Mediterranean |
| **Coverage** | Jan–Dec 2019, 12 monthly CSV files |
| **How to load** | Run `scripts/ingest_piraeus_ais.py` to bulk-load into PostGIS |

> **Startup behavior:** `app/main.py` checks for all required directories at startup. Missing paths emit a `logger.error` without crashing, enabling degraded/demo-only operation.

---

## 🔧 Key Services

### `DriftEngine`

Physics-based oil particle tracking using the model:

```
drift_velocity = ocean_current + windage × wind_velocity
```

- **Windage coefficient:** 3% (default, configurable)
- Supports **forward** and **backward** (hindcast) tracking
- Vectorised **ensemble tracking** for N particles simultaneously (NumPy)
- Handles fractional timestep remainders for accurate endpoint alignment
- Coordinate motion via spherical Earth geometry (no flat-Earth approximation)

### `HindcastService`

Wraps `DriftEngine.backward_drift_ensemble()` to produce a **probabilistic source estimate**:

- Spawns 100 particles uniformly within a 500 m radius of the observed slick centroid
- Integrates each particle backward by `duration_hours`
- Returns: `centroid_latitude`, `centroid_longitude`, `radius_km` of the source cloud

### `WeatherService`

- Loads ERA5 wind and CMEMS ocean current **NetCDF** files via `xarray`
- Organises files by year for efficient multi-year lookups
- Provides `get_velocity(lat, lon, timestamp)` (scalar) and `get_velocities(...)` (vectorised NumPy arrays)
- Single shared instance per process lifetime (`app.state.weather_service`)

### `AttributionEngine`

Orchestrates the complete 6-step pipeline: hindcast → candidate search → trajectory retrieval → scoring → ranked output.

### `ScoringEngine`

Interpretable baseline scorer — 6 behavioural sub-scores combined with fixed weights (see [Scoring Model](#-scoring-model)).

### `SpillCatalogService`

Singleton in-memory catalog loaded from `json_output/` at startup. Provides fast spill lookup by ID for the demo and drift-predict endpoints.

---

## 📊 Scoring Model

The `ScoringEngine` produces an interpretable total score as a weighted sum of 6 behavioral sub-scores. No ground truth is accessed during scoring.

| Sub-score | Weight | How it's measured |
|---|---|---|
| **Proximity** | 25% | Minimum haversine distance of vessel to source centroid (within ±30 min window). Score = `clip(1 − dist_km / 5.0, 0, 1)` |
| **Temporal** | 15% | Closest time delta to estimated release. Score = `clip(1 − min_time_min / 120, 0, 1)` |
| **Slowdown** | 20% | Speed reduction vs. pre-event baseline. Score = `clip((baseline − event_speed) / baseline, 0, 1)` |
| **Loiter** | 15% | Duration within 3 km of source centroid (±60 min). Score = `clip(loiter_minutes / 30, 0, 1)` |
| **Approach** | 12.5% | Fraction of pre-event steps where vessel is moving closer to source |
| **Departure** | 12.5% | Fraction of post-event steps where vessel is moving away from source |

**Total Score Formula:**

```
total = 0.25 × proximity + 0.15 × temporal + 0.20 × slowdown
      + 0.15 × loiter + 0.125 × approach + 0.125 × departure
```

---

## 🧪 Testing

Install dev dependencies:
```bash
pip install -r requirements-dev.txt
```

Run all tests:
```bash
pytest
```

Run with verbose output:
```bash
pytest -v
```

Run a specific test file:
```bash
pytest tests/test_drift_engine.py -v
pytest tests/test_scoring_engine.py -v
pytest tests/test_scenario_003_attribution.py -v
```

Run tests matching a keyword:
```bash
pytest -k "hindcast" -v
```

### Test Coverage Areas

| Test File | Coverage |
|---|---|
| `test_drift_engine.py` | Forward/backward tracking, pole guard, remainder step |
| `test_drift_ensemble_equivalence.py` | Ensemble vs scalar parity |
| `test_hindcast_service.py` | Backward ensemble source estimation |
| `test_scoring_engine.py` | All 6 scoring sub-components |
| `test_attribution_integrity.py` | End-to-end pipeline integrity |
| `test_synthetic_ais.py` | Synthetic AIS fixture validity |
| `test_scenario_002_attribution.py` | Scenario 002 attribution correctness |
| `test_scenario_003_attribution.py` | Scenario 003 attribution E2E |
| `test_scenario_003_db.py` | Scenario 003 database integration |
| `test_scenario_003_scoring.py` | Scenario 003 scoring validation |
| `test_weather_service.py` | NetCDF loading and velocity interpolation |
| `test_yearly_weather_service.py` | Multi-year file stitching |
| `test_visualization_api.py` | Visualization endpoint smoke tests |
| `test_demo_spills.py` | Demo catalog endpoints |

---

## 🔩 Scripts & Tooling

### Data Ingestion

| Script | Purpose |
|---|---|
| `scripts/ingest_piraeus_ais.py` | Bulk-load all Piraeus AIS monthly CSVs into PostGIS |
| `scripts/ingest_ml_outputs.py` | Ingest ML detection JSON files into catalog |
| `scripts/ingest_synthetic_ais.py` | Load synthetic AIS scenarios into PostGIS |
| `scripts/weather/download_era5.py` | Download ERA5 NetCDF wind data via CDSAPI |
| `scripts/download_env_data_2019.py` | Download 2019 environmental data |

### Scenario Runners

| Script | Purpose |
|---|---|
| `scripts/run_scenario_001.py` | Scenario 001 — real AIS + real detection |
| `scripts/run_scenario_002.py` | Scenario 002 — synthetic AIS attribution |
| `scripts/run_scenario_003.py` | Scenario 003 — controlled synthetic test |
| `scripts/run_scenario_004.py` | Scenario 004 — extended coverage |
| `scripts/run_scenario_005.py` | Scenario 005 — alternative region |

### Diagnostics & Analysis

| Script | Purpose |
|---|---|
| `scripts/diagnose_detections.py` | Full diagnostic report over all spill detections |
| `scripts/diagnose_all_spills.py` | Per-spill diagnostic summary |
| `scripts/analyze_vessel_behavior.py` | AIS vessel behaviour analysis |
| `scripts/analyze_piraeus_ais.py` | Piraeus AIS dataset analysis |
| `scripts/validate_2019_synthetic_ais.py` | Validate 2019 synthetic AIS data |
| `scripts/verify_2019_ais.py` | Verify ingested AIS records |
| `scripts/sync_catalog_attribution.py` | Sync catalog with attribution results |
| `batch_generate_and_upload_plots.py` | Batch-generate SAR plots and upload to Cloudinary |
| `evaluate_catalog_accuracy.py` | Compute accuracy metrics against ground truth |

---

## ⚙️ Configuration

All settings are managed by `app/core/config.py` via `pydantic-settings`. All values can be overridden with environment variables or the `.env` file.

| Variable | Default | Description |
|---|---|---|
| `PROJECT_NAME` | `SIH Oil Spill & Vessel Attribution API` | API title |
| `VERSION` | `1.0.0` | API version |
| `API_V1_STR` | `/api/v1` | API prefix |
| `CORS_ORIGINS` | `http://localhost:3000,http://localhost:5173` | Allowed CORS origins (comma-separated) |
| `POSTGRES_USER` | — | Database username |
| `POSTGRES_PASSWORD` | — | Database password |
| `POSTGRES_HOST` | `localhost` | Database host |
| `POSTGRES_PORT` | `5432` | Database port |
| `POSTGRES_DB` | — | Database name |
| `DATABASE_URL` | `None` | Full DSN override (takes precedence) |
| `DB_POOL_SIZE` | `5` | SQLAlchemy connection pool size |
| `DB_MAX_OVERFLOW` | `10` | Max overflow connections |
| `CDSAPI_KEY` | — | Copernicus CDS API key for ERA5 downloads |
| `CLOUDINARY_CLOUD_NAME` | — | Cloudinary cloud name |
| `CLOUDINARY_API_KEY` | — | Cloudinary API key |
| `CLOUDINARY_API_SECRET` | — | Cloudinary API secret |

---

## 🐳 Docker Details

The `Dockerfile` uses a **multi-stage build**:

- **Builder stage** (`python:3.11-slim`): Installs compiled geospatial libraries (GDAL, GEOS, PROJ) and Python packages
- **Final stage** (`python:3.11-slim`): Lean runtime image, runs as a non-root user (`appuser`)

```bash
# Manual image build
docker build -t oil-spill-backend .

# Run container directly
docker run -p 8000:8000 --env-file .env oil-spill-backend
```

### Docker Compose Services

| Service | Image | Port | Memory Limit |
|---|---|---|---|
| `postgres` | `postgis/postgis:15-3.4` | (internal only) | 512 MB |
| `api` | Built from `Dockerfile` | `8000:8000` | 1 GB |

The `postgres` service exposes no external port — only the `api` service connects to it over the internal Docker network. A health check (`pg_isready`) gates the `api` service startup.

---

## 🗄️ Database Schema

The database is bootstrapped via `db/init/01_init.sql` which is auto-executed on first `docker compose up`.

### Key Tables

| Table | Description |
|---|---|
| `vessels` | Vessel metadata (MMSI, name, vessel type, flag state) |
| `ais_positions` | AIS position records with PostGIS `geometry(Point, 4326)` column and spatial index |
| `oil_spill_detections` | Ingested ML detection records (polygon, centroid, detected_at) |

### Key Indexes

```sql
-- Enables fast ST_DWithin candidate lookups
CREATE INDEX ON ais_positions USING GIST (geom);

-- Composite temporal index for time-window queries
CREATE INDEX ON ais_positions (vessel_id, timestamp);
```

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-new-feature`
3. Write tests for your changes
4. Ensure all tests pass: `pytest`
5. Commit with a clear message: `git commit -m "feat: add new scoring sub-component"`
6. Push and open a pull request

### Code Style Guidelines

- Follow **PEP 8** / **PEP 257** (docstrings on all public classes and methods)
- Use **type hints** throughout
- Keep service methods pure (no side effects where possible)
- All database access must go through the **repository layer**
- Blocking I/O (NetCDF reads, heavy NumPy ops) **must** be wrapped in `run_in_threadpool`
- Never access ground truth data inside `ScoringEngine` or `AttributionEngine`

---

*Built for the Smart India Hackathon (SIH) — NTRO Oil Spill Detection Challenge.*