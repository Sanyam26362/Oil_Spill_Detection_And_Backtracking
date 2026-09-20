# Production vs Local API Parity Report

- **Generated At**: 2026-09-20T09:52:50.944481+00:00
- **Production URL**: `https://naavss.duckdns.org`
- **Target Spill ID**: `spill_4e354b`

| # | Method | Endpoint | Local Status | Prod Status | Parity Status | Summary / Differences |
|---|---|---|---|---|---|---|
| 1 | `GET` | `/health` | `200` | `200` | ** MATCH ** | Exact match |
| 2 | `GET` | `/health/ready` | `200` | `200` | ** MATCH ** | Exact match |
| 3 | `GET` | `/api/v1/spills/spill_4e354b` | `200` | `200` | ** MATCH ** | Exact match |
| 4 | `GET` | `/api/v1/spills` | `200` | `200` | ** MATCH ** | Exact match |
| 5 | `POST` | `/api/v1/spills/ingest-ml` | `201` | `201` | ** MATCH ** | Exact match |
| 6 | `POST` | `/api/v1/drift/forward` | `200` | `200` | ** MATCH ** | Exact match |
| 7 | `POST` | `/api/v1/drift/hindcast` | `200` | `200` | ** MATCH ** | Exact match |
| 8 | `GET` | `/api/v1/drift/spill_4e354b/predict` | `200` | `404` | ** DIFF ** | HTTP Status mismatch: Local=200 vs Prod=404 |
| 9 | `GET` | `/api/v1/drift/spill_4e354b/diagnostic-plot` | `200` | `200` | ** MATCH ** | Exact match |
| 10 | `POST` | `/api/v1/attribution` | `200` | `200` | ** DIFF ** | .top_prediction: missing in prod; .estimated_release_time: missing in prod |
| 11 | `GET` | `/api/v1/demo/spills` | `200` | `200` | ** MATCH ** | Exact match |
| 12 | `GET` | `/api/v1/demo/spills/spill_4e354b` | `200` | `200` | ** MATCH ** | Exact match |
| 13 | `GET` | `/api/v1/demo/spills/spill_4e354b/vessels` | `200` | `200` | ** DIFF ** | .vessels[0].identifiers_synthetic: missing in prod; .vessels[1].identifiers_synthetic: missing in prod (+2 more) |
| 14 | `GET` | `/api/v1/demo/spills/spill_4e354b/attribution/trajectory` | `200` | `200` | ** DIFF ** | .vessels[0].trajectory[0].course: numeric diff local=295.2 vs prod=284.07 (delta=11.129999999999995); .vessels[0].trajectory[0].speed: numeric diff local=14.94 vs prod=15.76 (delta=0.8200000000000003) (+15 more) |
| 15 | `POST` | `/api/v1/demo/spills/spill_4e354b/backtrack` | `200` | `200` | ** DIFF ** | .backtrack.estimated_release_time: type mismatch str vs NoneType |
| 16 | `GET` | `/api/v1/demo/spills/spill_4e354b/predict` | `200` | `200` | ** MATCH ** | Exact match |
| 17 | `GET` | `/api/v1/visualization/spills/spill_4e354b` | `200` | `200` | ** MATCH ** | Exact match |

---

## Detailed Comparison Breakdown

### 1. GET `/health`
**Description**: Basic service health check  
**Parity**: IDENTICAL  
**HTTP Status**: Local = `200` | Prod = `200`  

**Local Output Sample**:
```json
{
  "status": "ok",
  "service": "SIH Oil Spill & Vessel Attribution API"
}
```

**Production Output Sample**:
```json
{
  "status": "ok",
  "service": "SIH Oil Spill & Vessel Attribution API"
}
```

### 2. GET `/health/ready`
**Description**: Database and service readiness check  
**Parity**: IDENTICAL  
**HTTP Status**: Local = `200` | Prod = `200`  

**Local Output Sample**:
```json
{
  "status": "ready"
}
```

**Production Output Sample**:
```json
{
  "status": "ready"
}
```

### 3. GET `/api/v1/spills/spill_4e354b`
**Description**: Get specific spill detection details  
**Parity**: IDENTICAL  
**HTTP Status**: Local = `200` | Prod = `200`  

**Local Output Sample**:
```json
{
  "spill_id": "spill_4e354b",
  "detected_at": "2019-02-02T16:04:49Z",
  "centroid": {
    "lon": 24.019,
    "lat": 35.0191
  },
  "polygon": [
    [
      24.0173,
      35.0204
    ],
    [
      24.0207,
      35.0204
    ],
    [
      24.0207,
      35.0177
    ],
    [
      24.0173,
      
```

**Production Output Sample**:
```json
{
  "spill_id": "spill_4e354b",
  "detected_at": "2019-02-02T16:04:49Z",
  "centroid": {
    "lon": 24.019,
    "lat": 35.0191
  },
  "polygon": [
    [
      24.0173,
      35.0204
    ],
    [
      24.0207,
      35.0204
    ],
    [
      24.0207,
      35.0177
    ],
    [
      24.0173,
      
```

### 4. GET `/api/v1/spills`
**Description**: List all oil spill detections  
**Parity**: IDENTICAL  
**HTTP Status**: Local = `200` | Prod = `200`  

**Local Output Sample**:
```json
[
  {
    "spill_id": "spill_1566a9",
    "detected_at": "2019-01-01T03:42:35Z",
    "centroid": {
      "lon": 24.0288,
      "lat": 35.0354
    },
    "polygon": [
      [
        24.0233,
        35.0387
      ],
      [
        24.0344,
        35.0387
      ],
      [
        24.0344,
        3
```

**Production Output Sample**:
```json
[
  {
    "spill_id": "spill_1566a9",
    "detected_at": "2019-01-01T03:42:35Z",
    "centroid": {
      "lon": 24.0288,
      "lat": 35.0354
    },
    "polygon": [
      [
        24.0233,
        35.0387
      ],
      [
        24.0344,
        35.0387
      ],
      [
        24.0344,
        3
```

### 5. POST `/api/v1/spills/ingest-ml`
**Description**: Ingest ML detections batch  
**Parity**: IDENTICAL  
**HTTP Status**: Local = `201` | Prod = `201`  

**Local Output Sample**:
```json
{
  "message": "ML detections processed successfully.",
  "inserted_count": 0,
  "skipped_count": 1,
  "inserted_spill_ids": [],
  "skipped_spill_ids": [
    "spill_4e354b"
  ]
}
```

**Production Output Sample**:
```json
{
  "message": "ML detections processed successfully.",
  "inserted_count": 0,
  "skipped_count": 1,
  "inserted_spill_ids": [],
  "skipped_spill_ids": [
    "spill_4e354b"
  ]
}
```

### 6. POST `/api/v1/drift/forward`
**Description**: Forward particle drift simulation  
**Parity**: IDENTICAL  
**HTTP Status**: Local = `200` | Prod = `200`  

**Local Output Sample**:
```json
{
  "end_latitude": 35.02682860816973,
  "end_longitude": 23.989190430036892,
  "end_timestamp": "2019-02-02T18:04:49+00:00"
}
```

**Production Output Sample**:
```json
{
  "end_latitude": 35.02682860816973,
  "end_longitude": 23.989190430036892,
  "end_timestamp": "2019-02-02T18:04:49+00:00"
}
```

### 7. POST `/api/v1/drift/hindcast`
**Description**: Backward ensemble hindcast simulation  
**Parity**: IDENTICAL  
**HTTP Status**: Local = `200` | Prod = `200`  

**Local Output Sample**:
```json
{
  "centroid_latitude": 35.00523565282959,
  "centroid_longitude": 24.048961336370212,
  "radius_km": 0.5375602914232727
}
```

**Production Output Sample**:
```json
{
  "centroid_latitude": 35.00523565282959,
  "centroid_longitude": 24.048961336370212,
  "radius_km": 0.5375602914232727
}
```

### 8. GET `/api/v1/drift/spill_4e354b/predict`
**Description**: Predict forward spill drift  
**Parity**: DIFFERENCE DETECTED  
**HTTP Status**: Local = `200` | Prod = `404`  

**Differences Identified**:
- `HTTP Status mismatch: Local=200 vs Prod=404`

**Local Output Sample**:
```json
{
  "spill_id": "spill_4e354b",
  "forecast_hours": 6.0,
  "initial_position": {
    "latitude": 35.0191,
    "longitude": 24.019,
    "timestamp": "2019-02-02T16:04:49Z"
  },
  "predicted_position": {
    "latitude": 35.029889,
    "longitude": 23.932699,
    "timestamp": "2019-02-02T22:04:49"
  },
```

**Production Output Sample**:
```json
{
  "detail": "Spill with ID 'spill_4e354b' could not be found."
}
```

### 9. GET `/api/v1/drift/spill_4e354b/diagnostic-plot`
**Description**: Diagnostic plot URL  
**Parity**: IDENTICAL  
**HTTP Status**: Local = `200` | Prod = `200`  

**Local Output Sample**:
```json
{
  "spill_id": "spill_4e354b",
  "diagnostic_plot_url": "https://res.cloudinary.com/dll6vk0kp/image/upload/v1788710644/oil_spill_diagnostics/diagnostic_spill_4e354b.png"
}
```

**Production Output Sample**:
```json
{
  "spill_id": "spill_4e354b",
  "diagnostic_plot_url": "https://res.cloudinary.com/dll6vk0kp/image/upload/v1788710644/oil_spill_diagnostics/diagnostic_spill_4e354b.png"
}
```

### 10. POST `/api/v1/attribution`
**Description**: Direct vessel attribution engine query  
**Parity**: DIFFERENCE DETECTED  
**HTTP Status**: Local = `200` | Prod = `200`  

**Differences Identified**:
- `.top_prediction: missing in prod`
- `.estimated_release_time: missing in prod`

**Local Output Sample**:
```json
{
  "source_estimate": {
    "latitude": 35.00598381014967,
    "longitude": 24.048527463002735,
    "radius_km": 0.5115796559111344
  },
  "estimated_release_time": "2019-02-02T14:04:49+00:00",
  "candidate_count": 0,
  "candidates": [],
  "top_prediction": null
}
```

**Production Output Sample**:
```json
{
  "source_estimate": {
    "latitude": 35.00598381014967,
    "longitude": 24.048527463002735,
    "radius_km": 0.5115796559111345
  },
  "candidate_count": 0,
  "candidates": []
}
```

### 11. GET `/api/v1/demo/spills`
**Description**: List demo catalog spills  
**Parity**: IDENTICAL  
**HTTP Status**: Local = `200` | Prod = `200`  

**Local Output Sample**:
```json
{
  "total": 377,
  "page": 1,
  "page_size": 10,
  "items": [
    {
      "spill_id": "spill_31e02e",
      "detected_at": "2019-01-04T15:56:38Z",
      "centroid": {
        "lon": 24.0497,
        "lat": 35.0501
      },
      "area_km2": 0.59,
      "confidence_score": 0.78,
      "candidate_cou
```

**Production Output Sample**:
```json
{
  "total": 377,
  "page": 1,
  "page_size": 10,
  "items": [
    {
      "spill_id": "spill_31e02e",
      "detected_at": "2019-01-04T15:56:38Z",
      "centroid": {
        "lon": 24.0497,
        "lat": 35.0501
      },
      "area_km2": 0.59,
      "confidence_score": 0.78,
      "candidate_cou
```

### 12. GET `/api/v1/demo/spills/spill_4e354b`
**Description**: Get demo spill detail  
**Parity**: IDENTICAL  
**HTTP Status**: Local = `200` | Prod = `200`  

**Local Output Sample**:
```json
{
  "spill_id": "spill_4e354b",
  "source_type": "water",
  "source_file": "ow-0031.json",
  "detected_at": "2019-02-02T16:04:49Z",
  "estimated_age_hours": 15.5,
  "estimated_release_time": "2019-02-02T00:34:49Z",
  "observation_latitude": 35.0191,
  "observation_longitude": 24.019,
  "centroid": {
```

**Production Output Sample**:
```json
{
  "spill_id": "spill_4e354b",
  "source_type": "water",
  "source_file": "ow-0031.json",
  "detected_at": "2019-02-02T16:04:49Z",
  "estimated_age_hours": 15.5,
  "estimated_release_time": "2019-02-02T00:34:49Z",
  "observation_latitude": 35.0191,
  "observation_longitude": 24.019,
  "centroid": {
```

### 13. GET `/api/v1/demo/spills/spill_4e354b/vessels`
**Description**: Attributed and candidate vessels  
**Parity**: DIFFERENCE DETECTED  
**HTTP Status**: Local = `200` | Prod = `200`  

**Differences Identified**:
- `.vessels[0].identifiers_synthetic: missing in prod`
- `.vessels[1].identifiers_synthetic: missing in prod`
- `.vessels[2].identifiers_synthetic: missing in prod`
- `.vessels[3].identifiers_synthetic: missing in prod`

**Local Output Sample**:
```json
{
  "spill_id": "spill_4e354b",
  "vessels": [
    {
      "vessel_id": "SYNTH-Y2019-000026",
      "is_mock": false,
      "is_mock_comparison": false,
      "identifiers_synthetic": true,
      "rank": 1,
      "score": 0.85,
      "proximity_score": 0.0,
      "temporal_score": 0.185,
      "slow
```

**Production Output Sample**:
```json
{
  "spill_id": "spill_4e354b",
  "vessels": [
    {
      "vessel_id": "SYNTH-Y2019-000026",
      "is_mock": false,
      "is_mock_comparison": false,
      "rank": 1,
      "score": 0.85,
      "proximity_score": 0.0,
      "temporal_score": 0.185,
      "slowdown_score": 0.0,
      "loiter_score
```

### 14. GET `/api/v1/demo/spills/spill_4e354b/attribution/trajectory`
**Description**: Attributed vessel trajectory  
**Parity**: DIFFERENCE DETECTED  
**HTTP Status**: Local = `200` | Prod = `200`  

**Differences Identified**:
- `.vessels[0].trajectory[0].course: numeric diff local=295.2 vs prod=284.07 (delta=11.129999999999995)`
- `.vessels[0].trajectory[0].speed: numeric diff local=14.94 vs prod=15.76 (delta=0.8200000000000003)`
- `.vessels[0].trajectory[0].polygon[0][0]: numeric diff local=25.86358 vs prod=25.880671 (delta=0.017091000000000633)`
- `.vessels[0].trajectory[0].polygon[0][1]: numeric diff local=34.470364 vs prod=34.490129 (delta=0.019765000000006694)`
- `.vessels[0].trajectory[0].polygon[1][0]: numeric diff local=25.896248 vs prod=25.914928 (delta=0.018679999999999808)`
- `.vessels[0].trajectory[0].polygon[1][1]: numeric diff local=34.459204 vs prod=34.478428 (delta=0.01922400000000124)`
- `.vessels[0].trajectory[0].polygon[2][0]: numeric diff local=25.90978 vs prod=25.929118 (delta=0.019337999999997635)`
- `.vessels[0].trajectory[0].polygon[2][1]: numeric diff local=34.432259 vs prod=34.450179 (delta=0.017919999999996605)`
- `.vessels[0].trajectory[0].polygon[3][0]: numeric diff local=25.896248 vs prod=25.914928 (delta=0.018679999999999808)`
- `.vessels[0].trajectory[0].polygon[3][1]: numeric diff local=34.405314 vs prod=34.42193 (delta=0.01661600000000618)`
- *... and 7 more differences*

**Local Output Sample**:
```json
{
  "spill_id": "spill_4e354b",
  "backtrack_origin": {
    "latitude": 34.92182377238791,
    "longitude": 24.242819424241073,
    "timestamp": "2019-02-02T00:34:49Z",
    "radius_km": 0.6490494132370475
  },
  "verification": {
    "culprit_vessel_id": "SYNTH-Y2019-000026",
    "search_parameters"
```

**Production Output Sample**:
```json
{
  "spill_id": "spill_4e354b",
  "backtrack_origin": {
    "latitude": 34.92182377238791,
    "longitude": 24.242819424241073,
    "timestamp": "2019-02-02T00:34:49Z",
    "radius_km": 0.6490494132370475
  },
  "verification": {
    "culprit_vessel_id": "SYNTH-Y2019-000026",
    "search_parameters"
```

### 15. POST `/api/v1/demo/spills/spill_4e354b/backtrack`
**Description**: Demo catalog backtrack  
**Parity**: DIFFERENCE DETECTED  
**HTTP Status**: Local = `200` | Prod = `200`  

**Differences Identified**:
- `.backtrack.estimated_release_time: type mismatch str vs NoneType`

**Local Output Sample**:
```json
{
  "spill_id": "spill_4e354b",
  "backtrack": {
    "observation": {
      "latitude": 35.0191,
      "longitude": 24.019,
      "timestamp": "2019-02-02T16:04:49+00:00"
    },
    "estimated_release_time": "2019-02-02T00:34:49+00:00",
    "source_estimate": {
      "latitude": 34.92182377238791,
 
```

**Production Output Sample**:
```json
{
  "spill_id": "spill_4e354b",
  "backtrack": {
    "observation": {
      "latitude": 35.0191,
      "longitude": 24.019,
      "timestamp": "2019-02-02T16:04:49+00:00"
    },
    "estimated_release_time": null,
    "source_estimate": {
      "latitude": 34.92182377238791,
      "longitude": 24.24
```

### 16. GET `/api/v1/demo/spills/spill_4e354b/predict`
**Description**: Forward prediction for demo spill  
**Parity**: IDENTICAL  
**HTTP Status**: Local = `200` | Prod = `200`  

**Local Output Sample**:
```json
{
  "spill_id": "spill_4e354b",
  "forecast_hours": 6.0,
  "initial_position": {
    "latitude": 35.0191,
    "longitude": 24.019,
    "timestamp": "2019-02-02T16:04:49Z"
  },
  "predicted_position": {
    "latitude": 35.029889,
    "longitude": 23.932699,
    "timestamp": "2019-02-02T22:04:49"
  },
```

**Production Output Sample**:
```json
{
  "spill_id": "spill_4e354b",
  "forecast_hours": 6.0,
  "initial_position": {
    "latitude": 35.0191,
    "longitude": 24.019,
    "timestamp": "2019-02-02T16:04:49Z"
  },
  "predicted_position": {
    "latitude": 35.029889,
    "longitude": 23.932699,
    "timestamp": "2019-02-02T22:04:49"
  },
```

### 17. GET `/api/v1/visualization/spills/spill_4e354b`
**Description**: Full frontend visualization  
**Parity**: IDENTICAL  
**HTTP Status**: Local = `200` | Prod = `200`  

**Local Output Sample**:
```json
{
  "spill": {
    "spill_id": "spill_4e354b",
    "latitude": 35.0191,
    "longitude": 24.019,
    "detected_at": "2019-02-02T16:04:49Z"
  },
  "source_estimate": {
    "latitude": 34.921824,
    "longitude": 24.242819,
    "radius_km": 0.649
  },
  "environment": {
    "wind": {
      "u": -6.211
```

**Production Output Sample**:
```json
{
  "spill": {
    "spill_id": "spill_4e354b",
    "latitude": 35.0191,
    "longitude": 24.019,
    "detected_at": "2019-02-02T16:04:49Z"
  },
  "source_estimate": {
    "latitude": 34.921824,
    "longitude": 24.242819,
    "radius_km": 0.649
  },
  "environment": {
    "wind": {
      "u": -6.211
```
