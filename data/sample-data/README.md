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
| `observations.json` | Bundled seed input: 103 source records |
| `observations.csv` | Bundled seed records for spreadsheets; the app download exports current data |
| `observations.geojson` | The same records as WGS84 Point features, longitude first |
| `practice-queries.json` | Questions, expected source IDs and discussion points |

The bundled seed corpus covers **28 locations across all 13 Malaysian states and three federal
territories**, including Sabah, Sarawak and Labuan. Each location has flood,
vegetation and land-use records (84 total); 19 locations also have coastal
records. Inland locations, including **Shah Alam and Hulu Langat, deliberately
have no coastal records** to support the evidence-insufficiency exercise.
The generator lists all places, states, approximate coordinates and coastal
scenario flags. Original Selangor citation IDs and values remain stable.

Every bundled seed observation is dated **2026-10-15**. Change metrics compare against the
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

Regenerate with `python3 data/generate_data.py` from the project root.


## Current data, editing and CSV imports

The bundled files above are the reproducible seed dataset. At runtime,
`data/record_store.py` merges them with saved SQLite overrides and imported
additions. Record counts and dates can therefore differ from this seed summary.
Regenerating the sample files preserves saved edits and additions; it does not
export the current merged dataset.

Data Explorer displays collapsible application groups with counts. Search and
application filters narrow the displayed records and map markers. Expand a
group, then a record, to inspect or edit it.

To update multiple observations, download the **current CSV from Data Explorer**,
modify the desired rows, then use **Upload CSV → Upload and save**. Matching IDs
update supplied editable fields; new IDs add observations; omitted records are
preserved. Existing IDs can be updated with just `id` and changed editable
columns. New records need the full editable fields, `theme` and
`synthetic=True`. See the [import guide](../../README.md#import-observations-from-csv)
for columns, ID prefixes and date rules.

The importer accepts UTF-8 CSV (with or without BOM), at most 2 MB / 2,000 rows.
It validates the entire file and rejects duplicate IDs or invalid rows before
committing one SQLite transaction. All data must remain synthetic. Summary and
quality are regenerated; existing provenance is retained and new observations
receive a user-uploaded synthetic provenance label. Imported records can be
edited normally and appear in retrieval, rankings and all download formats.
Practice queries describe the bundled seed; imports can change their results.

Saved edits and imports live in `data/database/record-edits.sqlite3` by default,
or under `SPACELAB_DATA_DIR`. Back up this directory to retain them. Heroku's
local filesystem is temporary; see the [deployment guide](../../docs/HEROKU.md)
for persistence limits.
