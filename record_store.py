"""Validated record edits, persisted locally and shared by server workers."""
import csv
import io
import json
import math
import os
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

from rag import load_records
from scripts.generate_data import SITES, THEMES

ROOT = Path(__file__).resolve().parent
STATES = {site[1] for site in SITES}
TEXT_FIELDS = {'title': 200, 'location': 100, 'sensor': 200, 'limitations': 2000}
EDITABLE = set(TEXT_FIELDS) | {'state', 'latitude', 'longitude', 'observation_date',
                              'baseline_date', 'value', 'cloud_cover_pct'}


class EditConflict(Exception):
    pass


class RecordNotFound(Exception):
    pass


def database_path():
    return Path(os.environ.get('SPACELAB_DATA_DIR', str(ROOT / '.data'))) / 'record-edits.sqlite3'


def _merge(records, connection):
    if not connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='edits'").fetchone():
        return records
    overrides = {record_id: json.loads(body) for record_id, body in connection.execute('SELECT id, body FROM edits')}
    return [overrides.get(record['id'], record) for record in records]


def get_records():
    records = load_records()
    path = database_path()
    if path.exists():
        with closing(sqlite3.connect(str(path))) as connection:
            records = _merge(records, connection)
    return records


def validated_edit(original, changes):
    if not isinstance(changes, dict) or not changes or changes.keys() - EDITABLE:
        raise ValueError('Provide editable record fields only.')
    record = dict(original, **changes)
    for field, maximum in TEXT_FIELDS.items():
        value = record[field]
        if not isinstance(value, str) or not value.strip() or len(value) > maximum:
            raise ValueError(f'{field} must contain 1–{maximum} characters.')
        record[field] = value.strip()
    if not isinstance(record['state'], str) or record['state'] not in STATES:
        raise ValueError('Select a Malaysian state or federal territory.')
    for field, minimum, maximum in [('latitude', -90, 90), ('longitude', -180, 180),
                                     ('cloud_cover_pct', 0, 100),
                                     ('value', -1 if record['theme'] == 'vegetation' else 0,
                                      1 if record['theme'] == 'vegetation' else 1e12)]:
        value = record[field]
        if type(value) not in (float, int) or not minimum <= value <= maximum or not math.isfinite(value):
            raise ValueError(f'{field} must be a finite number between {minimum} and {maximum}.')
    for field in ('observation_date', 'baseline_date'):
        value = record[field]
        if field == 'baseline_date' and value is None and record['theme'] in ('flood', 'vegetation'):
            continue
        try:
            if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
                raise ValueError()
        except (TypeError, ValueError):
            raise ValueError(f'{field} must be a valid YYYY-MM-DD date.')
    if record['theme'] in ('flood', 'vegetation') and record['baseline_date'] is not None:
        raise ValueError('This application uses a single observation without a baseline date.')
    if record['baseline_date'] and record['baseline_date'] >= record['observation_date']:
        raise ValueError('Baseline date must be earlier than the observation date.')
    if record['theme'] == 'flood' and record['cloud_cover_pct'] != 0:
        raise ValueError('Radar cloud cover uses the zero placeholder.')
    # Keep narrative evidence consistent with edited measurements and dates.
    template = THEMES[record['theme']][5]
    record['description'] = (template.replace('2025-10-15', record['baseline_date'] or '')
                             .replace('2026-10-15', record['observation_date'])
                             .format(value=record['value']))
    record['quality'] = 'limited' if record['cloud_cover_pct'] > 25 else 'usable for classroom exercise'
    return record


def update_record(record_id, changes, original):
    if not isinstance(original, dict):
        raise ValueError('Provide the original record to detect conflicting edits.')
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(str(path), timeout=5)) as connection:
        connection.execute('CREATE TABLE IF NOT EXISTS edits (id TEXT PRIMARY KEY, body TEXT NOT NULL)')
        connection.commit()
        try:
            connection.execute('BEGIN IMMEDIATE')
            records = _merge(load_records(), connection)
            current = next((record for record in records if record['id'] == record_id), None)
            if current is None:
                raise RecordNotFound('Record not found.')
            if original != current:
                raise EditConflict('This record changed since you opened it. Cancel and reopen the editor to load the latest version.')
            updated = validated_edit(current, changes)
            connection.execute('INSERT OR REPLACE INTO edits (id, body) VALUES (?, ?)',
                               (record_id, json.dumps(updated, allow_nan=False)))
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return updated


def export_records(records, extension):
    if extension == 'csv':
        output = io.StringIO(newline='')
        writer = csv.DictWriter(output, fieldnames=records[0].keys(), lineterminator='\n')
        writer.writeheader()
        writer.writerows(records)
        return output.getvalue().encode()
    if extension == 'geojson':
        payload = {'type': 'FeatureCollection', 'features': [
            {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [r['longitude'], r['latitude']]},
             'properties': r} for r in records]}
    else:
        payload = records
    return (json.dumps(payload, indent=2, allow_nan=False) + '\n').encode()
