"""Validated record edits, persisted locally and shared by server workers."""
import csv
import io
import json
import math
import os
import re
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

from rag_server.rag import load_records
from data.generate_data import SITES, THEMES

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
    return Path(os.environ.get('SPACELAB_DATA_DIR', str(ROOT / 'database'))) / 'record-edits.sqlite3'


def _merge(records, connection):
    if not connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='edits'").fetchone():
        return records
    overrides = {record_id: json.loads(body) for record_id, body in connection.execute('SELECT id, body FROM edits')}
    base_ids = {record['id'] for record in records}
    return ([overrides.get(record['id'], record) for record in records]
            + [record for key, record in overrides.items() if key not in base_ids])


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


def import_csv(text):
    """Validate the complete upload before atomically inserting/updating by ID."""
    reader = csv.DictReader(io.StringIO(text.lstrip('\ufeff'), newline=''), strict=True)
    columns = reader.fieldnames
    allowed = EDITABLE | {'id', 'theme', 'metric', 'unit', 'synthetic',
                          'description', 'quality', 'provenance'}
    if not columns or 'id' not in columns or len(columns) != len(set(columns)) or set(columns) - allowed:
        raise ValueError('CSV needs an id column, unique headers and supported columns. Use the CSV download as a template.')
    try:
        rows = list(reader)
    except csv.Error as exc:
        raise ValueError(f'Invalid CSV: {exc}')
    if not 1 <= len(rows) <= 2000:
        raise ValueError('Upload between 1 and 2000 records at a time.')
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(str(path), timeout=5)) as connection:
        connection.execute('CREATE TABLE IF NOT EXISTS edits (id TEXT PRIMARY KEY, body TEXT NOT NULL)')
        connection.commit()
        try:
            connection.execute('BEGIN IMMEDIATE')
            current = {r['id']: r for r in _merge(load_records(), connection)}
            seen, updates = set(), []
            added = updated = 0
            for number, row in enumerate(rows, 2):
                try:
                    if None in row or any(value is None for value in row.values()):
                        raise ValueError('Column count does not match the header.')
                    row = {key: value.strip() for key, value in row.items()}
                    record_id = row['id']
                    if not re.fullmatch(r'[A-Z]+-\d{3}', record_id):
                        raise ValueError('ID must use uppercase letters and three digits, e.g. FLOOD-029.')
                    if record_id in seen:
                        raise ValueError(f'Duplicate ID {record_id}.')
                    seen.add(record_id)
                    original = current.get(record_id)
                    if original is None:
                        required = EDITABLE | {'theme', 'synthetic'}
                        if required - row.keys():
                            raise ValueError('New records need columns: ' + ', '.join(sorted(required - row.keys())))
                        theme = row['theme']
                        if theme not in THEMES or not record_id.startswith(theme.upper().replace('-', '') + '-'):
                            raise ValueError('Use a supported theme and its matching ID prefix.')
                        spec = THEMES[theme]
                        original = {'id': record_id, 'theme': theme, 'metric': spec[2], 'unit': spec[3],
                                    'synthetic': True, 'provenance': 'User-uploaded synthetic teaching observation; not real satellite measurements.'}
                        added += 1
                    else:
                        updated += 1
                    for key in ('theme', 'metric', 'unit'):
                        if key in row and row[key] != original[key]:
                            raise ValueError(f'{key} must match the application: {original[key]}.')
                    if 'synthetic' in row and row['synthetic'].lower() != 'true':
                        raise ValueError('Only synthetic teaching data (synthetic=True) is supported.')
                    changes = {key: value for key, value in row.items() if key in EDITABLE}
                    for key in ('latitude', 'longitude', 'value', 'cloud_cover_pct'):
                        if key in changes:
                            try:
                                changes[key] = float(changes[key])
                            except ValueError:
                                raise ValueError(f'{key} must be a number.')
                    if changes.get('baseline_date') == '':
                        changes['baseline_date'] = None
                    validated = validated_edit(original, changes) if changes else original
                    updates.append((record_id, json.dumps(validated, allow_nan=False)))
                except ValueError as exc:
                    raise ValueError(f'CSV row {number}: {exc}')
            connection.executemany('INSERT OR REPLACE INTO edits (id, body) VALUES (?, ?)', updates)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return {'added': added, 'updated': updated}


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
