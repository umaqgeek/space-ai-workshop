"""Rebuild the fictional, deterministic workshop corpus. No downloads required."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'sample-data'
# Place, state / federal territory, approximate latitude / longitude, coastal sample.
# Keep the original six places first so existing citation IDs remain stable.
SITES = [
    ('Klang', 'Selangor', 3.0449, 101.4456, True),
    ('Shah Alam', 'Selangor', 3.0733, 101.5185, False),
    ('Kuala Selangor', 'Selangor', 3.3402, 101.2498, True),
    ('Sepang', 'Selangor', 2.6931, 101.7498, True),
    ('Hulu Langat', 'Selangor', 3.1130, 101.8150, False),
    ('Sabak Bernam', 'Selangor', 3.7698, 100.9879, True),
    ('Alor Setar', 'Kedah', 6.1248, 100.3678, False),
    ('Langkawi', 'Kedah', 6.3500, 99.8000, True),
    ('George Town', 'Penang', 5.4141, 100.3288, True),
    ('Ipoh', 'Perak', 4.5975, 101.0901, False),
    ('Lumut', 'Perak', 4.2323, 100.6298, True),
    ('Kangar', 'Perlis', 6.4414, 100.1986, False),
    ('Kuala Perlis', 'Perlis', 6.4000, 100.1333, True),
    ('Seremban', 'Negeri Sembilan', 2.7297, 101.9381, False),
    ('Port Dickson', 'Negeri Sembilan', 2.5228, 101.7959, True),
    ('Melaka', 'Melaka', 2.1896, 102.2501, True),
    ('Johor Bahru', 'Johor', 1.4927, 103.7414, True),
    ('Kuantan', 'Pahang', 3.8077, 103.3260, True),
    ('Kuala Terengganu', 'Terengganu', 5.3296, 103.1370, True),
    ('Kota Bharu', 'Kelantan', 6.1254, 102.2381, True),
    ('Kuching', 'Sarawak', 1.5533, 110.3592, False),
    ('Miri', 'Sarawak', 4.3995, 113.9914, True),
    ('Kota Kinabalu', 'Sabah', 5.9804, 116.0735, True),
    ('Sandakan', 'Sabah', 5.8394, 118.1172, True),
    ('Kuala Lumpur', 'Kuala Lumpur', 3.1390, 101.6869, False),
    ('Putrajaya', 'Putrajaya', 2.9264, 101.6964, False),
    ('Labuan', 'Labuan', 5.2831, 115.2308, True),
    ('Tawau', 'Sabah', 4.2448, 117.8912, True),
]
THEMES = {
    'flood': ('Flood observation', 'Sentinel-1-like radar', 'inundated_area_ha', 'ha',
              [142, 68, 94, 37, 119, 83],
              'Radar-like classification indicates {value} ha of possible surface water in the fictional study area. This is an observation, not a flood forecast.',
              'Radar can observe through clouds, but permanent water, wet soil and radar shadow can cause false detections. Ground verification is needed.'),
    'vegetation': ('Vegetation condition', 'Sentinel-2-like optical', 'ndvi', 'index',
                   [0.42, 0.51, 0.73, 0.46, 0.78, 0.67],
                   'The fictional vegetation index (NDVI) is {value}. Higher NDVI can indicate greener vegetation; it does not establish crop health or species.',
                   'Clouds and mixed pixels affect optical observations. NDVI alone cannot diagnose disease or establish biodiversity.'),
    'land-use': ('Land-use change', 'Landsat-like optical', 'built_up_change_ha', 'ha',
                 [28, 34, 12, 46, 18, 9],
                 'The fictional comparison from 2025-10-15 to 2026-10-15 shows {value} ha classified as newly built-up land.',
                 'Classification changes may reflect seasonal differences or misclassification. This is not evidence of legal status, ownership or planning approval.'),
    'coastal': ('Coastal observation', 'Sentinel-2-like optical', 'shoreline_retreat_m', 'm',
                [4.2, None, 7.8, 3.1, None, 9.4],
                'The fictional comparison from 2025-10-15 to 2026-10-15 suggests {value} m of shoreline retreat in a sample coastal sector.',
                'Tides, georeferencing and pixel size affect shoreline estimates. These invented values do not demonstrate real erosion.'),
}


def generate():
    ROOT.mkdir(exist_ok=True)
    records = []
    for theme, (title, sensor, metric, unit, values, template, limitation) in THEMES.items():
        for i, (place, state, lat, lon, coastal) in enumerate(SITES):
            if theme == 'coastal' and not coastal:
                continue
            # Preserve the original examples; vary new values deterministically.
            if i < len(values):
                value = values[i]
            elif theme == 'flood':
                value = 30 + (i * 37) % 220
            elif theme == 'vegetation':
                value = round(0.35 + ((i * 13) % 49) / 100, 2)
            elif theme == 'land-use':
                value = 8 + (i * 11) % 65
            else:
                value = round(1.5 + ((i * 17) % 90) / 10, 1)
            if value is None:
                continue
            record_id = f'{theme.upper().replace("-", "")}-{i+1:03d}'
            cloud = 0 if theme == 'flood' else [18, 24, 12, 31, 9, 16][i % 6]
            records.append({
                'id': record_id, 'title': f'{place} · {title}', 'location': place,
                'state': state, 'latitude': lat, 'longitude': lon,
                'theme': theme, 'observation_date': '2026-10-15',
                'baseline_date': '2025-10-15' if theme in ('land-use', 'coastal') else None,
                'sensor': sensor, 'metric': metric, 'value': value, 'unit': unit,
                'cloud_cover_pct': cloud,
                'quality': 'limited' if cloud > 25 else 'usable for classroom exercise',
                'description': template.format(value=value), 'limitations': limitation,
                'synthetic': True, 'provenance': 'Invented by the workshop data generator; not downloaded satellite measurements.',
            })
    (ROOT / 'observations.json').write_text(json.dumps(records, indent=2) + '\n')
    with (ROOT / 'observations.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=records[0].keys(), lineterminator='\n')
        writer.writeheader()
        writer.writerows(records)
    features = [{'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [r['longitude'], r['latitude']]},
                 'properties': r} for r in records]
    (ROOT / 'observations.geojson').write_text(json.dumps({'type': 'FeatureCollection', 'features': features}, indent=2) + '\n')
    print(f'Generated {len(records)} synthetic records in JSON, CSV and GeoJSON.')


if __name__ == '__main__':
    generate()
