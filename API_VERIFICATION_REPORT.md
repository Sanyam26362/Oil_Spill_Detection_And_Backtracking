# API Verification & Output Report

Generated at: 2026-09-20T08:03:34.563877+00:00
Target Spill ID: `spill_4e354b`

| # | Method | Endpoint | Status | Summary |
|---|---|---|---|---|
| 1 | `GET` | `/health` | `200` | Basic service health check |
| 2 | `GET` | `/health/ready` | `200` | Database and service readiness check |
| 3 | `GET` | `/api/v1/spills` | `200` | List all oil spill detections in DB |
| 4 | `GET` | `/api/v1/spills/spill_4e354b` | `200` | Get specific spill detection details from DB |
| 5 | `POST` | `/api/v1/spills/ingest-ml` | `201` | Ingest ML detections batch (existing detection idempotency check) |
| 6 | `POST` | `/api/v1/drift/forward` | `200` | Forward particle drift simulation |
| 7 | `POST` | `/api/v1/drift/hindcast` | `200` | Backward ensemble hindcast simulation |
| 8 | `GET` | `/api/v1/drift/spill_4e354b/predict` | `200` | Predict forward spill drift from detection coordinates |
| 9 | `GET` | `/api/v1/drift/spill_4e354b/diagnostic-plot` | `200` | Diagnostic plot Cloudinary image URL for spill |
| 10 | `POST` | `/api/v1/attribution` | `200` | Direct vessel attribution engine query |
| 11 | `GET` | `/api/v1/demo/spills` | `200` | List demo spills with pagination |
| 12 | `GET` | `/api/v1/demo/spills/spill_4e354b` | `200` | Get single demo spill details from catalog |
| 13 | `GET` | `/api/v1/demo/spills/spill_4e354b/vessels` | `200` | Attributed and candidate vessels with sub-scores |
| 14 | `GET` | `/api/v1/demo/spills/spill_4e354b/attribution/trajectory` | `200` | Attributed vessel AIS trajectory and CPA |
| 15 | `POST` | `/api/v1/demo/spills/spill_4e354b/backtrack` | `200` | Catalog backtrack endpoint |
| 16 | `GET` | `/api/v1/demo/spills/spill_4e354b/predict` | `200` | Forward prediction for demo spill |
| 17 | `GET` | `/api/v1/visualization/spills/spill_4e354b` | `200` | Full frontend visualization payload |

---

## Detailed Request & Response Outputs

### 1. GET `/health`
**Description**: Basic service health check  
**HTTP Status**: `200`  
**Response Body**:
```json
{
  "status": "ok",
  "service": "SIH Oil Spill & Vessel Attribution API"
}
```

### 2. GET `/health/ready`
**Description**: Database and service readiness check  
**HTTP Status**: `200`  
**Response Body**:
```json
{
  "status": "ready"
}
```

### 3. GET `/api/v1/spills`
**Description**: List all oil spill detections in DB  
**HTTP Status**: `200`  
**Query Parameters**:
```json
{
  "limit": 2
}
```
**Response Body**:
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
        35.032
      ],
      [
        24.0233,
        35.032
      ],
      [
        24.0233,
        35.0387
      ]
    ],
    "area_km2": 0.75,
    "estimated_age_hours": 16.8,
    "confidence_score": 0.9,
    "image_reference": "https://res.cloudinary.com/bro6lw9c/image/upload/oc-0001.jpg"
  },
  {
    "spill_id": "spill_dfa07c",
    "detected_at": "2019-01-01T03:42:35Z",
    "centroid": {
      "lon": 24.0426,
      "lat": 35.061
    },
    "polygon": [
      [
        24.0365,
        35.0657
      ],
      [
        24.0487,
        35.0657
      ],
      [
        24.0487,
        35.0563
      ],
      [
        24.0365,
        35.0563
      ],
      [
        24.0365,
        35.0657
      ]
    ],
    "area_km2": 1.15,
    "estimated_age_hours": 15.5,
    "confidence_score": 0.85,
    "image_reference": "https://res.cloudinary.com/bro6lw9c/image/upload/oc-0001.jpg"
  },
  {
    "spill_id": "spill_692068",
    "detected_at": "2019-01-01T03:42:35Z",
    "centroid": {
      "lon": 24.056,
      "lat": 35.0498
    },
    "polygon": [
      [
        24.0535,
        35.0541
      ],
      [
        24.0584,
        35.0541
      ],
      [
        24.0584,
        35.0455
      ],
      [
        24.0535,
        35.0455
      ],
      [
        24.0535,
        35.0541
      ]
    ],
    "area_km2": 0.43,
    "estimated_age_hours": 22.7,
    "confidence_score": 0.79,
    "image_reference": "https://res.cloudinary.com/bro6lw9c/image/upload/ow-0001.jpg"
  },
  {
    "spill_id": "spill_d7e8e7",
    "detected_at": "2019-01-01T03:42:35Z",
    "centroid": {
      "lon": 24.0559,
      "lat": 35.0217
    },
    "polygon": [
      [
        24.0539,
        35.0332
      ],
      [
        24.0578,
        35.0332
      ],
      [
        24.0578,
        35.0102
      ],
      [
        24.0539,
        35.0102
      ],
      [
        24.0539,
        35.0332
      ]
    ],
    "area_km2": 0.93,
    "estimated_age_hours": 47.4,
    "confidence_score": 0.54,
    "image_reference": "https://res.cloudinary.com/bro6lw9c/image/upload/oc-0002.jpg"
  },
  {
    "spill_id": "spill_5495f2",
    "detected_at": "2019-01-01T03:42:35Z",
    "centroid": {
      "lon": 24.0177,
      "lat": 35.0844
    },
    "polygon": [
      [
        24.0034,
        35.0999
      ],
      [
        24.032,
        35.0999
      ],
      [
        24.032,
        35.0689
      ],
      [
        24.0034,
        35.0689
      ],
      [
        24.0034,
        35.0999
      ]
    ],
    "area_km2": 8.99,
    "estimated_age_hours": 16.5,
    "confidence_score": 0.77,
    "image_reference": "https://res.cloudinary.com/bro6lw9c/image/upload/oc-0002.jpg"
  },
  {
    "spill_id": "spill_4b168c",
    "detected_at": "2019-01-01T03:42:35Z",
    "centroid": {
      "lon": 24.0434,
      "lat": 35.0433
    },
    "polygon": [
      [
        24.0395,
        35.0525
      ],
      [
        24.0472,
        35.0525
      ],
      [
        24.0472,
        35.034
      ],
      [
        24.0395,
        35.034
      ],
      [
        24.0395,
        35.0525
      ]
    ],
... [Truncated: 73412 more lines] ...
```

### 4. GET `/api/v1/spills/spill_4e354b`
**Description**: Get specific spill detection details from DB  
**HTTP Status**: `200`  
**Response Body**:
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
      35.0177
    ],
    [
      24.0173,
      35.0204
    ]
  ],
  "area_km2": 0.09,
  "estimated_age_hours": 15.5,
  "confidence_score": 0.67,
  "image_reference": "https://res.cloudinary.com/bro6lw9c/image/upload/ow-0031.jpg"
}
```

### 5. POST `/api/v1/spills/ingest-ml`
**Description**: Ingest ML detections batch (existing detection idempotency check)  
**HTTP Status**: `201`  
**Request Body**:
```json
{
  "detections": [
    {
      "spill_id": "spill_4e354b",
      "detected_at": "2019-02-02T16:04:49Z",
      "centroid": {
        "lat": 35.0191,
        "lon": 24.019
      },
      "polygon": [
        [
          24.01,
          35.01
        ],
        [
          24.02,
          35.01
        ],
        [
          24.02,
          35.02
        ],
        [
          24.01,
          35.02
        ]
      ],
      "area_km2": 0.09,
      "estimated_age_hours": 15.5,
      "confidence_score": 0.67,
      "image_reference": "sample_url"
    }
  ]
}
```
**Response Body**:
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
**HTTP Status**: `200`  
**Request Body**:
```json
{
  "start_latitude": 35.0191,
  "start_longitude": 24.019,
  "start_time": "2019-02-02T16:04:49Z",
  "duration_hours": 2.0
}
```
**Response Body**:
```json
{
  "end_latitude": 35.02682860816973,
  "end_longitude": 23.989190430036892,
  "end_timestamp": "2019-02-02T18:04:49+00:00"
}
```

### 7. POST `/api/v1/drift/hindcast`
**Description**: Backward ensemble hindcast simulation  
**HTTP Status**: `200`  
**Request Body**:
```json
{
  "obs_latitude": 35.0191,
  "obs_longitude": 24.019,
  "obs_time": "2019-02-02T16:04:49Z",
  "duration_hours": 2.0,
  "ensemble_size": 10
}
```
**Response Body**:
```json
{
  "centroid_latitude": 35.00523565282959,
  "centroid_longitude": 24.048961336370212,
  "radius_km": 0.5375602914232727
}
```

### 8. GET `/api/v1/drift/spill_4e354b/predict`
**Description**: Predict forward spill drift from detection coordinates  
**HTTP Status**: `200`  
**Response Body**:
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
  "total_displacement_km": 7.949,
  "net_heading_deg": 278.7,
  "average_speed_knots": 0.72,
  "trajectory": [
    {
      "timestamp": "2019-02-02T16:04:49",
      "latitude": 35.0191,
      "longitude": 24.019,
      "drift_speed_knots": 0.8,
      "drift_heading_deg": 293.3,
      "distance_from_start_km": 0.0
    },
    {
      "timestamp": "2019-02-02T16:19:49",
      "latitude": 35.020416,
      "longitude": 24.015264,
      "drift_speed_knots": 0.79,
      "drift_heading_deg": 291.5,
      "distance_from_start_km": 0.37
    },
    {
      "timestamp": "2019-02-02T16:34:49",
      "latitude": 35.021631,
      "longitude": 24.011507,
      "drift_speed_knots": 0.78,
      "drift_heading_deg": 289.8,
      "distance_from_start_km": 0.738
    },
    {
      "timestamp": "2019-02-02T16:49:49",
      "latitude": 35.022739,
      "longitude": 24.007753,
      "drift_speed_knots": 0.77,
      "drift_heading_deg": 288.1,
      "distance_from_start_km": 1.101
    },
    {
      "timestamp": "2019-02-02T17:04:49",
      "latitude": 35.023739,
      "longitude": 24.004009,
      "drift_speed_knots": 0.77,
      "drift_heading_deg": 286.3,
      "distance_from_start_km": 1.459
    },
    {
      "timestamp": "2019-02-02T17:19:49",
      "latitude": 35.024635,
      "longitude": 24.000276,
      "drift_speed_knots": 0.76,
      "drift_heading_deg": 284.6,
      "distance_from_start_km": 1.813
    },
    {
      "timestamp": "2019-02-02T17:34:49",
      "latitude": 35.025432,
      "longitude": 23.996553,
      "drift_speed_knots": 0.75,
      "drift_heading_deg": 283.6,
      "distance_from_start_km": 2.162
    },
    {
      "timestamp": "2019-02-02T17:49:49",
      "latitude": 35.026162,
      "longitude": 23.992857,
      "drift_speed_knots": 0.74,
      "drift_heading_deg": 282.5,
      "distance_from_start_km": 2.507
    },
    {
      "timestamp": "2019-02-02T18:04:49",
      "latitude": 35.026829,
      "longitude": 23.98919,
      "drift_speed_knots": 0.73,
      "drift_heading_deg": 281.5,
      "distance_from_start_km": 2.847
    },
    {
      "timestamp": "2019-02-02T18:19:49",
      "latitude": 35.027433,
      "longitude": 23.985553,
      "drift_speed_knots": 0.72,
      "drift_heading_deg": 280.5,
      "distance_from_start_km": 3.183
    },
    {
      "timestamp": "2019-02-02T18:34:49",
      "latitude": 35.027978,
      "longitude": 23.981947,
      "drift_speed_knots": 0.71,
      "drift_heading_deg": 279.4,
      "distance_from_start_km": 3.516
    },
    {
      "timestamp": "2019-02-02T18:49:49",
      "latitude": 35.028463,
      "longitude": 23.97837,
      "drift_speed_knots": 0.7,
      "drift_heading_deg": 278.3,
      "distance_from_start_km": 3.843
    },
    {
      "timestamp": "2019-02-02T19:04:49",
      "latitude": 35.028888,
      "longitude": 23.974825,
      "drift_speed_knots": 0.7,
      "drift_heading_deg": 277.2,
      "distance_from_start_km": 4.167
    },
    {
      "timestamp": "2019-02-02T19:19:49",
      "latitude": 35.029251,
      "longitude": 23.971303,
      "drift_speed_knots": 0.69,
      "drift_heading_deg": 276.1,
      "distance_from_start_km": 4.488
    },
    {
      "timestamp": "2019-02-02T19:34:49",
      "latitude": 35.029557,
      "longitude": 23.96779,
      "drift_speed_knots": 0.69,
      "drift_heading_deg": 275.0,
      "distance_from_start_km": 4.806
    },
    {
      "timestamp": "2019-02-02T19:49:49",
      "latitude": 35.029809,
      "longitude": 23.964286,
      "drift_speed_knots": 0.69,
      "drift_heading_deg": 273.9,
      "distance_from_start_km": 5.122
    },
    {
      "timestamp": "2019-02-02T20:04:49",
      "latitude": 35.030006,
      "longitude": 23.960791,
      "drift_speed_knots": 0.69,
      "drift_heading_deg": 272.9,
      "distance_from_start_km": 5.437
    },
    {
      "timestamp": "2019-02-02T20:19:49",
      "latitude": 35.030153,
      "longitude": 23.957299,
      "drift_speed_knots": 0.69,
      "drift_heading_deg": 272.0,
      "distance_from_start_km": 5.751
    },
    {
      "timestamp": "2019-02-02T20:34:49",
      "latitude": 35.030254,
      "longitude": 23.953805,
      "drift_speed_knots": 0.69,
      "drift_heading_deg": 271.1,
      "distance_from_start_km": 6.065
    },
    {
      "timestamp": "2019-02-02T20:49:49",
      "latitude": 35.030306,
      "longitude": 23.950311,
      "drift_speed_knots": 0.69,
      "drift_heading_deg": 270.1,
      "distance_from_start_km": 6.378
    },
    {
      "timestamp": "2019-02-02T21:04:49",
      "latitude": 35.030312,
      "longitude": 23.946815,
      "drift_speed_knots": 0.69,
      "drift_heading_deg": 269.2,
      "distance_from_start_km": 6.69
    },
    {
      "timestamp": "2019-02-02T21:19:49",
      "latitude": 35.03027,
      "longitude": 23.943313,
      "drift_speed_knots": 0.69,
      "drift_heading_deg": 268.3,
      "distance_from_start_km": 7.003
    },
    {
      "timestamp": "2019-02-02T21:34:49",
      "latitude": 35.030186,
      "longitude": 23.939794,
      "drift_speed_knots": 0.7,
      "drift_heading_deg": 267.5,
      "distance_from_start_km": 7.317
... [Truncated: 19 more lines] ...
```

### 9. GET `/api/v1/drift/spill_4e354b/diagnostic-plot`
**Description**: Diagnostic plot Cloudinary image URL for spill  
**HTTP Status**: `200`  
**Response Body**:
```json
{
  "spill_id": "spill_4e354b",
  "diagnostic_plot_url": "https://res.cloudinary.com/dll6vk0kp/image/upload/v1788710644/oil_spill_diagnostics/diagnostic_spill_4e354b.png"
}
```

### 10. POST `/api/v1/attribution`
**Description**: Direct vessel attribution engine query  
**HTTP Status**: `200`  
**Request Body**:
```json
{
  "observation_latitude": 35.0191,
  "observation_longitude": 24.019,
  "observation_time": "2019-02-02T16:04:49Z",
  "drift_duration_hours": 2.0,
  "synthetic_only": false
}
```
**Response Body**:
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

### 11. GET `/api/v1/demo/spills`
**Description**: List demo spills with pagination  
**HTTP Status**: `200`  
**Query Parameters**:
```json
{
  "page": 1,
  "page_size": 2
}
```
**Response Body**:
```json
{
  "total": 377,
  "page": 1,
  "page_size": 2,
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
      "candidate_count": 1,
      "image_url": "https://res.cloudinary.com/bro6lw9c/image/upload/oc-0004.jpg"
    },
    {
      "spill_id": "spill_5bcb47",
      "detected_at": "2019-01-04T15:56:38Z",
      "centroid": {
        "lon": 24.0814,
        "lat": 35.0316
      },
      "area_km2": 0.67,
      "confidence_score": 0.5,
      "candidate_count": 2,
      "image_url": "https://res.cloudinary.com/bro6lw9c/image/upload/oc-0004.jpg"
    }
  ]
}
```

### 12. GET `/api/v1/demo/spills/spill_4e354b`
**Description**: Get single demo spill details from catalog  
**HTTP Status**: `200`  
**Response Body**:
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
      35.0177
    ],
    [
      24.0173,
      35.0204
    ]
  ],
  "area_km2": 0.09,
  "confidence_score": 0.67,
  "image_url": "https://res.cloudinary.com/bro6lw9c/image/upload/ow-0031.jpg",
  "estimated_source_latitude": 34.92182377238791,
  "estimated_source_longitude": 24.242819424241073,
  "estimated_source_radius_km": 0.6490494132370475,
  "candidate_count": 1,
  "ranked_top_vessel": "SYNTH-Y2019-000026",
  "ranked_top_score": 0.85,
  "runtime_seconds": 2.077
}
```

### 13. GET `/api/v1/demo/spills/spill_4e354b/vessels`
**Description**: Attributed and candidate vessels with sub-scores  
**HTTP Status**: `200`  
**Response Body**:
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
      "slowdown_score": 0.0,
      "loiter_score": 0.0,
      "approach_score": 0.4567,
      "departure_score": 0.0,
      "vessel_name": "SYNTH-Y2019-000026",
      "mmsi": "209203562",
      "imo": "9203382",
      "country": "CY",
      "shiptype": 70,
      "shiptype_name": "Cargo",
      "vessel_type": "Cargo",
      "speed": 17.96,
      "course": null,
      "heading": 260.86,
      "distance_to_origin_km": 32.7,
      "time_difference_hours": 1.63,
      "trajectory_correlation": 0.94
    },
    {
      "vessel_id": "SYNTH-Y2019-000027",
      "is_mock": true,
      "is_mock_comparison": true,
      "identifiers_synthetic": true,
      "rank": 2,
      "score": 0.2306,
      "proximity_score": 0.2733,
      "temporal_score": 0.4,
      "slowdown_score": 0.0563,
      "loiter_score": 0.0,
      "approach_score": 0.6,
      "departure_score": 0.128,
      "vessel_name": "SYNTH-Y2019-000027",
      "mmsi": "636203615",
      "imo": "9203552",
      "country": "LR",
      "shiptype": 70,
      "shiptype_name": "Cargo, all ships of this type",
      "vessel_type": "Cargo",
      "speed": 13.4,
      "course": 210.2,
      "heading": 212.0,
      "distance_to_origin_km": 21.8,
      "time_difference_hours": 1.2,
      "trajectory_correlation": null
    },
    {
      "vessel_id": "SYNTH-Y2019-000028",
      "is_mock": true,
      "is_mock_comparison": true,
      "identifiers_synthetic": true,
      "rank": 3,
      "score": 0.0756,
      "proximity_score": 0.2033,
      "temporal_score": 0.0,
      "slowdown_score": 0.0508,
      "loiter_score": 0.0,
      "approach_score": 0.1167,
      "departure_score": 0.0,
      "vessel_name": "SYNTH-Y2019-000028",
      "mmsi": "215203668",
      "imo": "9203722",
      "country": "MT",
      "shiptype": 80,
      "shiptype_name": "Tanker, all ships of this type",
      "vessel_type": "Tanker",
      "speed": 11.2,
      "course": 195.0,
      "heading": 196.5,
      "distance_to_origin_km": 23.9,
      "time_difference_hours": 2.5,
      "trajectory_correlation": null
    },
    {
      "vessel_id": "SYNTH-Y2019-000029",
      "is_mock": true,
      "is_mock_comparison": true,
      "identifiers_synthetic": true,
      "rank": 4,
      "score": 0.2247,
      "proximity_score": 0.32,
      "temporal_score": 0.45,
      "slowdown_score": 0.0,
      "loiter_score": 0.0,
      "approach_score": 0.5333,
      "departure_score": 0.084,
      "vessel_name": "SYNTH-Y2019-000029",
      "mmsi": "239203721",
      "imo": "9203899",
      "country": "GR",
      "shiptype": 30,
      "shiptype_name": "Fishing",
      "vessel_type": "Fishing",
      "speed": 6.8,
      "course": 182.0,
      "heading": 184.5,
      "distance_to_origin_km": 20.4,
      "time_difference_hours": -1.1,
      "trajectory_correlation": null
    }
  ]
}
```

### 14. GET `/api/v1/demo/spills/spill_4e354b/attribution/trajectory`
**Description**: Attributed vessel AIS trajectory and CPA  
**HTTP Status**: `200`  
**Response Body**:
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
    "search_parameters": {
      "drift_uncertainty_radius_km": 0.649,
      "candidate_search_corridor_radius_km": 30.0,
      "temporal_window_hours": 2.0
    },
    "candidate_within_corridor": false,
    "culprit_position_timestamp": "2019-02-02T02:12:30Z",
    "origin_to_culprit_distance_km": 32.703,
    "within_backtrack_radius": false,
    "ais_points_in_window": 111,
    "display_trajectory_points": 44,
    "trajectory_window": {
      "start": "2019-02-01T21:30:00Z",
      "end": "2019-02-02T19:00:00Z"
    },
    "nearest_origin_ais_point": {
      "timestamp": "2019-02-02T02:12:30Z",
      "latitude": 34.63116,
      "longitude": 24.297407,
      "speed": 17.96,
      "course": null,
      "heading": 260.86,
      "polygon": [
        [
          24.297407,
          34.676059
        ],
        [
          24.335991,
          34.662908
        ],
        [
          24.351973,
          34.63116
        ],
        [
          24.335991,
          34.599412
        ],
        [
          24.297407,
          34.586261
        ],
        [
          24.258823,
          34.599412
        ],
        [
          24.242841,
          34.63116
        ],
        [
          24.258823,
          34.662908
        ],
        [
          24.297407,
          34.676059
        ]
      ]
    },
    "closest_approach_ais_point": {
      "timestamp": "2019-02-02T02:12:30Z",
      "latitude": 34.63116,
      "longitude": 24.297407,
      "speed": 17.96,
      "course": null,
      "heading": 260.86,
      "polygon": [
        [
          24.297407,
          34.676059
        ],
        [
          24.335991,
          34.662908
        ],
        [
          24.351973,
          34.63116
        ],
        [
          24.335991,
          34.599412
        ],
        [
          24.297407,
          34.586261
        ],
        [
          24.258823,
          34.599412
        ],
        [
          24.242841,
          34.63116
        ],
        [
          24.258823,
          34.662908
        ],
        [
          24.297407,
          34.676059
        ]
      ]
    },
    "closest_approach_distance_km": 32.703,
    "timestamp_nearest_ais_point": {
      "timestamp": "2019-02-02T00:34:00Z",
      "latitude": 34.586717,
      "longitude": 24.882928,
      "speed": 17.48,
      "course": 270.29,
      "heading": 270.29,
      "polygon": [
        [
          24.882928,
          34.630536
        ],
        [
          24.920564,
          34.617702
        ],
        [
          24.936154,
          34.586717
        ],
        [
          24.920564,
          34.555732
        ],
        [
          24.882928,
          34.542898
        ],
        [
          24.845292,
          34.555732
        ],
        [
          24.829702,
          34.586717
        ],
        [
          24.845292,
          34.617702
        ],
        [
          24.882928,
          34.630536
        ]
      ]
    },
    "timestamp_nearest_distance_from_origin_km": 69.342
  },
  "attribution": {
    "top_vessel": "SYNTH-Y2019-000026",
    "top_candidate_vessel_id": "SYNTH-Y2019-000026",
    "attribution_qualification": "Vessel identified within 30 km transit corridor during estimated release window; evaluated via multi-criteria trajectory and velocity scoring.",
    "top_score": 0.85,
    "rank": 1,
    "candidate_count": 1
  },
  "vessels": [
    {
      "vessel_id": "SYNTH-Y2019-000026",
      "is_mock": false,
      "is_mock_comparison": false,
      "rank": 1,
      "score": 0.85,
      "vessel_name": "SYNTH-Y2019-000026",
      "mmsi": "209203562",
      "imo": "9203382",
      "country": "CY",
      "vessel_type": "Cargo",
      "culprit_location": {
        "timestamp": "2019-02-02T02:12:30Z",
        "latitude": 34.63116,
        "longitude": 24.297407,
        "speed": 17.96,
        "course": null,
        "heading": 260.86,
        "polygon": [
          [
            24.297407,
            34.676059
          ],
          [
            24.335991,
... [Truncated: 8345 more lines] ...
```

### 15. POST `/api/v1/demo/spills/spill_4e354b/backtrack`
**Description**: Catalog backtrack endpoint  
**HTTP Status**: `200`  
**Response Body**:
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
      "longitude": 24.242819424241073,
      "radius_km": 0.6490494132370475
    }
  },
  "attribution": {
    "candidate_count": 0,
    "top_vessel": null,
    "top_score": 0.85
  }
}
```

### 16. GET `/api/v1/demo/spills/spill_4e354b/predict`
**Description**: Forward prediction for demo spill  
**HTTP Status**: `200`  
**Response Body**:
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
  "total_displacement_km": 7.949,
  "net_heading_deg": 278.7,
  "average_speed_knots": 0.72,
  "trajectory": [
    {
      "timestamp": "2019-02-02T16:04:49",
      "latitude": 35.0191,
      "longitude": 24.019,
      "drift_speed_knots": 0.8,
      "drift_heading_deg": 293.3,
      "distance_from_start_km": 0.0
    },
    {
      "timestamp": "2019-02-02T16:19:49",
      "latitude": 35.020416,
      "longitude": 24.015264,
      "drift_speed_knots": 0.79,
      "drift_heading_deg": 291.5,
      "distance_from_start_km": 0.37
    },
    {
      "timestamp": "2019-02-02T16:34:49",
      "latitude": 35.021631,
      "longitude": 24.011507,
      "drift_speed_knots": 0.78,
      "drift_heading_deg": 289.8,
      "distance_from_start_km": 0.738
    },
    {
      "timestamp": "2019-02-02T16:49:49",
      "latitude": 35.022739,
      "longitude": 24.007753,
      "drift_speed_knots": 0.77,
      "drift_heading_deg": 288.1,
      "distance_from_start_km": 1.101
    },
    {
      "timestamp": "2019-02-02T17:04:49",
      "latitude": 35.023739,
      "longitude": 24.004009,
      "drift_speed_knots": 0.77,
      "drift_heading_deg": 286.3,
      "distance_from_start_km": 1.459
    },
    {
      "timestamp": "2019-02-02T17:19:49",
      "latitude": 35.024635,
      "longitude": 24.000276,
      "drift_speed_knots": 0.76,
      "drift_heading_deg": 284.6,
      "distance_from_start_km": 1.813
    },
    {
      "timestamp": "2019-02-02T17:34:49",
      "latitude": 35.025432,
      "longitude": 23.996553,
      "drift_speed_knots": 0.75,
      "drift_heading_deg": 283.6,
      "distance_from_start_km": 2.162
    },
    {
      "timestamp": "2019-02-02T17:49:49",
      "latitude": 35.026162,
      "longitude": 23.992857,
      "drift_speed_knots": 0.74,
      "drift_heading_deg": 282.5,
      "distance_from_start_km": 2.507
    },
    {
      "timestamp": "2019-02-02T18:04:49",
      "latitude": 35.026829,
      "longitude": 23.98919,
      "drift_speed_knots": 0.73,
      "drift_heading_deg": 281.5,
      "distance_from_start_km": 2.847
    },
    {
      "timestamp": "2019-02-02T18:19:49",
      "latitude": 35.027433,
      "longitude": 23.985553,
      "drift_speed_knots": 0.72,
      "drift_heading_deg": 280.5,
      "distance_from_start_km": 3.183
    },
    {
      "timestamp": "2019-02-02T18:34:49",
      "latitude": 35.027978,
      "longitude": 23.981947,
      "drift_speed_knots": 0.71,
      "drift_heading_deg": 279.4,
      "distance_from_start_km": 3.516
    },
    {
      "timestamp": "2019-02-02T18:49:49",
      "latitude": 35.028463,
      "longitude": 23.97837,
      "drift_speed_knots": 0.7,
      "drift_heading_deg": 278.3,
      "distance_from_start_km": 3.843
    },
    {
      "timestamp": "2019-02-02T19:04:49",
      "latitude": 35.028888,
      "longitude": 23.974825,
      "drift_speed_knots": 0.7,
      "drift_heading_deg": 277.2,
      "distance_from_start_km": 4.167
    },
    {
      "timestamp": "2019-02-02T19:19:49",
      "latitude": 35.029251,
      "longitude": 23.971303,
      "drift_speed_knots": 0.69,
      "drift_heading_deg": 276.1,
      "distance_from_start_km": 4.488
    },
    {
      "timestamp": "2019-02-02T19:34:49",
      "latitude": 35.029557,
      "longitude": 23.96779,
      "drift_speed_knots": 0.69,
      "drift_heading_deg": 275.0,
      "distance_from_start_km": 4.806
    },
    {
      "timestamp": "2019-02-02T19:49:49",
      "latitude": 35.029809,
      "longitude": 23.964286,
      "drift_speed_knots": 0.69,
      "drift_heading_deg": 273.9,
      "distance_from_start_km": 5.122
    },
    {
      "timestamp": "2019-02-02T20:04:49",
      "latitude": 35.030006,
      "longitude": 23.960791,
      "drift_speed_knots": 0.69,
      "drift_heading_deg": 272.9,
      "distance_from_start_km": 5.437
    },
    {
      "timestamp": "2019-02-02T20:19:49",
      "latitude": 35.030153,
      "longitude": 23.957299,
      "drift_speed_knots": 0.69,
      "drift_heading_deg": 272.0,
      "distance_from_start_km": 5.751
    },
    {
      "timestamp": "2019-02-02T20:34:49",
      "latitude": 35.030254,
      "longitude": 23.953805,
      "drift_speed_knots": 0.69,
      "drift_heading_deg": 271.1,
      "distance_from_start_km": 6.065
    },
    {
      "timestamp": "2019-02-02T20:49:49",
      "latitude": 35.030306,
      "longitude": 23.950311,
      "drift_speed_knots": 0.69,
      "drift_heading_deg": 270.1,
      "distance_from_start_km": 6.378
    },
    {
      "timestamp": "2019-02-02T21:04:49",
      "latitude": 35.030312,
      "longitude": 23.946815,
      "drift_speed_knots": 0.69,
      "drift_heading_deg": 269.2,
      "distance_from_start_km": 6.69
    },
    {
      "timestamp": "2019-02-02T21:19:49",
      "latitude": 35.03027,
      "longitude": 23.943313,
      "drift_speed_knots": 0.69,
      "drift_heading_deg": 268.3,
      "distance_from_start_km": 7.003
    },
    {
      "timestamp": "2019-02-02T21:34:49",
      "latitude": 35.030186,
      "longitude": 23.939794,
      "drift_speed_knots": 0.7,
      "drift_heading_deg": 267.5,
      "distance_from_start_km": 7.317
... [Truncated: 19 more lines] ...
```

### 17. GET `/api/v1/visualization/spills/spill_4e354b`
**Description**: Full frontend visualization payload  
**HTTP Status**: `200`  
**Response Body**:
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
      "u": -6.211462,
      "v": 1.061857,
      "speed": 6.301571,
      "direction": 99.7,
      "unit": "m/s"
    },
    "current": {
      "u": -0.191708,
      "v": 0.130773,
      "speed": 0.232063,
      "direction": 304.3,
      "unit": "m/s"
    }
  },
  "trajectory": [
    {
      "timestamp": "2019-02-02T16:04:49Z",
      "latitude": 35.0191,
      "longitude": 24.019
    },
    {
      "timestamp": "2019-02-02T15:49:49Z",
      "latitude": 35.017784,
      "longitude": 24.022736
    },
    {
      "timestamp": "2019-02-02T15:34:49Z",
      "latitude": 35.016367,
      "longitude": 24.026463
    },
    {
      "timestamp": "2019-02-02T15:19:49Z",
      "latitude": 35.01485,
      "longitude": 24.030185
    },
    {
      "timestamp": "2019-02-02T15:04:49Z",
      "latitude": 35.013236,
      "longitude": 24.033903
    },
    {
      "timestamp": "2019-02-02T14:49:49Z",
      "latitude": 35.011524,
      "longitude": 24.037621
    },
    {
      "timestamp": "2019-02-02T14:34:49Z",
      "latitude": 35.009737,
      "longitude": 24.041344
    },
    {
      "timestamp": "2019-02-02T14:19:49Z",
      "latitude": 35.007887,
      "longitude": 24.045078
    },
    {
      "timestamp": "2019-02-02T14:04:49Z",
      "latitude": 35.005937,
      "longitude": 24.048824
    },
    {
      "timestamp": "2019-02-02T13:49:49Z",
      "latitude": 35.003882,
      "longitude": 24.052591
    },
    {
      "timestamp": "2019-02-02T13:34:49Z",
      "latitude": 35.001736,
      "longitude": 24.056406
    },
    {
      "timestamp": "2019-02-02T13:19:49Z",
      "latitude": 34.999507,
      "longitude": 24.060286
    },
    {
      "timestamp": "2019-02-02T13:04:49Z",
      "latitude": 34.997189,
      "longitude": 24.06424
    },
    {
      "timestamp": "2019-02-02T12:49:49Z",
      "latitude": 34.994778,
      "longitude": 24.068269
    },
    {
      "timestamp": "2019-02-02T12:34:49Z",
      "latitude": 34.992283,
      "longitude": 24.072386
    },
    {
      "timestamp": "2019-02-02T12:19:49Z",
      "latitude": 34.98971,
      "longitude": 24.076599
    },
    {
      "timestamp": "2019-02-02T12:04:49Z",
      "latitude": 34.987056,
      "longitude": 24.080914
    },
    {
      "timestamp": "2019-02-02T11:49:49Z",
      "latitude": 34.98432,
      "longitude": 24.085341
    },
    {
      "timestamp": "2019-02-02T11:34:49Z",
      "latitude": 34.981566,
      "longitude": 24.08982
    },
    {
      "timestamp": "2019-02-02T11:19:49Z",
      "latitude": 34.978853,
      "longitude": 24.094325
    },
    {
      "timestamp": "2019-02-02T11:04:49Z",
      "latitude": 34.976177,
      "longitude": 24.098855
    },
    {
      "timestamp": "2019-02-02T10:49:49Z",
      "latitude": 34.973545,
      "longitude": 24.103355
    },
    {
      "timestamp": "2019-02-02T10:34:49Z",
      "latitude": 34.970978,
      "longitude": 24.107797
    },
    {
      "timestamp": "2019-02-02T10:19:49Z",
      "latitude": 34.968482,
      "longitude": 24.11217
    },
    {
      "timestamp": "2019-02-02T10:04:49Z",
      "latitude": 34.966054,
      "longitude": 24.116482
    },
    {
      "timestamp": "2019-02-02T09:49:49Z",
      "latitude": 34.96369,
      "longitude": 24.120738
    },
    {
      "timestamp": "2019-02-02T09:34:49Z",
      "latitude": 34.961333,
      "longitude": 24.124932
    },
    {
      "timestamp": "2019-02-02T09:19:49Z",
      "latitude": 34.958955,
      "longitude": 24.129064
    },
    {
      "timestamp": "2019-02-02T09:04:49Z",
      "latitude": 34.956666,
      "longitude": 24.133106
    },
    {
      "timestamp": "2019-02-02T08:49:49Z",
      "latitude": 34.954468,
      "longitude": 24.137064
    },
    {
      "timestamp": "2019-02-02T08:34:49Z",
      "latitude": 34.952395,
      "longitude": 24.140925
    },
    {
      "timestamp": "2019-02-02T08:19:49Z",
      "latitude": 34.950464,
      "longitude": 24.144686
    },
    {
      "timestamp": "2019-02-02T08:04:49Z",
      "latitude": 34.948672,
      "longitude": 24.148353
    },
    {
      "timestamp": "2019-02-02T07:49:49Z",
      "latitude": 34.947018,
      "longitude": 24.151931
    },
    {
... [Truncated: 146 more lines] ...
```
