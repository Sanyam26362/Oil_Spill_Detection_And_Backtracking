# Environmental Lookup Performance Optimization

## Goal
Substantially reduce the runtime of the attribution engine (currently ~57-59 seconds) by batching the environmental lookup operations. Profiling reveals that the current sequential lookup (`Dataset.interp` called individually for each particle at each timestep) incurs high xarray bookkeeping overhead.

## User Review Required
> [!IMPORTANT]
> The target strategy is to use **Option A: vectorized DataArray.interp()**.
> This approach natively handles the NetCDF dimensions, coordinates, and NaN logic, keeping the code mathematically equivalent while drastically reducing the bookkeeping overhead. My tests confirm this takes 0.014s per batch of 100 vs 1.24s scalar, with differences bounded to `1e-15` floating point precision. Is this acceptable?

## Open Questions
- None.

## Proposed Changes

---

### WeatherService

#### [MODIFY] [`app/services/weather_service.py`](file:///d:/projects/oil-spill-backend/app/services/weather_service.py)
- **Changes**:
  - Add a new method `get_velocities(latitudes, longitudes, timestamps)` that returns lists/arrays of `current_u, current_v, wind_u, wind_v`.
  - The implementation will use xarray's vectorized `.interp()` by passing `xr.DataArray(latitudes, dims="points")` and `xr.DataArray(longitudes, dims="points")`.
  - Maintain the old `get_velocity` method as a scalar reference to be used by the numerical equivalence test.

---

### DriftEngine

#### [MODIFY] [`app/services/drift_engine.py`](file:///d:/projects/oil-spill-backend/app/services/drift_engine.py)
- **Changes**:
  - Add an ensemble-aware tracking method `_track_ensemble(start_latitudes, start_longitudes, ...)` that processes all particles in parallel at each timestep.
  - Maintain a list of active particle indices to correctly drop particles that hit NaN/land without aborting the others.
  - Return `list[DriftTrajectory]`.
  - Add `backward_drift_ensemble` and `forward_drift_ensemble` proxy methods.
  - Leave `_track` unchanged for numerical reference/backward compatibility.

---

### HindcastService

#### [MODIFY] [`app/services/hindcast_service.py`](file:///d:/projects/oil-spill-backend/app/services/hindcast_service.py)
- **Changes**:
  - In `backward_ensemble`, instead of a `for` loop over each particle invoking `backward_drift`, pre-calculate all initial particle offsets.
  - Call the new `drift_engine.backward_drift_ensemble`.
  - Iterate over the returned valid trajectories to populate `particles`.

---

### Tests and Benchmarking

#### [NEW] [`scratch/test_numerical_equivalence.py`](file:///d:/projects/oil-spill-backend/scratch/test_numerical_equivalence.py)
- **Changes**:
  - A script that calls both the old scalar and new batched implementations across various grid points (normal ocean, boundary points, NaN/land).
  - Reports max/mean absolute differences to formally assert `1e-7` or better precision equivalence.

#### [NEW] [`scratch/test_trajectory_equivalence.py`](file:///d:/projects/oil-spill-backend/scratch/test_trajectory_equivalence.py)
- **Changes**:
  - A script that runs the full `HindcastService.backward_ensemble` with the old loop and the new batch mode.
  - Asserts identical end-particle positions, centroid, radius, and valid count.

## Verification Plan

### Automated Tests
- Run `pytest -q tests/` (expecting 47 passes).
- Run `python -m scripts.test_postgis_candidates` (expect Scenario-002 isolation).
- Run `python -m scripts.test_end_to_end_postgis` twice, record new runtime to compute the speedup.
- Run `python -m scripts.benchmark.runner` to guarantee the 40-scenario metrics stay at 100%.

### Manual Verification
- Execute `test_numerical_equivalence.py` and `test_trajectory_equivalence.py` and capture output for the `implementation_verification_report.md`.
