# Space-tech sample data

**All observation values, sensor descriptions, quality labels and environmental
findings are synthetic.** These records were invented for teaching, not obtained
from Sentinel, Landsat, an agency, or a satellite processing service. They must
not be represented as real observations. Real place names and approximate
place-centre coordinates provide scenario context; points are not study-area
boundaries or a record of an actual event.

## Files

| File | Purpose |
| --- | --- |
| `observations.json` | Authoritative app input: 22 source records |
| `observations.csv` | The same records for spreadsheets |
| `observations.geojson` | The same records as WGS84 Point features, longitude first |
| `practice-queries.json` | Questions, expected source IDs and discussion points |

Six locations: Klang, Shah Alam, Kuala Selangor, Sepang, Hulu Langat and Sabak
Bernam. Each has flood, vegetation and land-use records. Four have coastal
records; **Shah Alam and Hulu Langat deliberately have none**. Missing records
support the evidence-insufficiency exercise.

Every observation is dated **2026-10-15**. Change metrics compare against the
fictional baseline **2025-10-15**. No time series, live monitoring, predictions,
population exposure, elevation, rainfall, legal ownership or imagery is included.

## Data dictionary

| Field | Meaning |
| --- | --- |
| `id` | Stable citation ID; e.g. `FLOOD-001` |
| `title`, `location`, `state` | Display name and place context |
| `latitude`, `longitude` | Approximate decimal-degree place reference; WGS84 |
| `theme` | `flood`, `vegetation`, `land-use`, or `coastal` |
| `observation_date` | Fictional observation date, ISO 8601 |
| `baseline_date` | Fictional change baseline; null for single observations |
| `sensor` | A sensor-like teaching label, not a real acquisition |
| `metric`, `value`, `unit` | The invented measurement and units below |
| `cloud_cover_pct` | Fictional optical scene cloud percentage; radar uses zero as a non-applicable placeholder |
| `quality` | Teaching quality label; optical cloud >25% is `limited` |
| `description` | Searchable observation text used in answer excerpts |
| `limitations` | Cautions participants must inspect |
| `synthetic`, `provenance` | Explicit invented-data flag and origin |

| Metric | Units | Classroom meaning |
| --- | --- | --- |
| `inundated_area_ha` | hectares | Classified possible surface water; not flood severity or a forecast |
| `ndvi` | dimensionless index | Vegetation greenness indicator; not a health diagnosis |
| `built_up_change_ha` | hectares | Fictional class change; not legal land-use status |
| `shoreline_retreat_m` | metres | Fictional shoreline position difference; not a validated erosion rate |

The purpose is interpreting reference records, not deriving metrics from raw
pixels. Real remote-sensing processing, calibration, segmentation, image
classification and spatial calculations are outside this starter.

Regenerate with `python3 scripts/generate_data.py` from the project root.
