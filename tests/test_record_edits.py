import csv
import io
import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from wsgiref.util import setup_testing_defaults

import rag
import record_store
from webapp import dispatch, application


class RecordEditTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.config = patch.dict(os.environ, {'SPACELAB_DATA_DIR': self.directory.name})
        self.config.start()
        self.addCleanup(self.config.stop)
        self.original = record_store.get_records()[0]

    def request(self, method, path, data=None, content_type='application/json'):
        body = json.dumps(data).encode() if data is not None else b''
        status, headers, payload = dispatch(method, path, {'Content-Length': str(len(body)),
                                                        'Content-Type': content_type}, io.BytesIO(body))
        return status, payload

    def save(self, changes, original=None, record_id=None):
        return self.request('POST', '/api/records/' + (record_id or self.original['id']),
                            {'changes': changes, 'original': original or self.original})

    def test_edits_persist_and_update_answers_rankings_and_downloads(self):
        status, payload = self.save({'value': 999, 'latitude': 3.2, 'longitude': 101.4,
                                     'observation_date': '2026-10-20', 'limitations': 'Edited teaching limitation.'})
        self.assertEqual(status, 200)
        updated = json.loads(payload)['record']
        self.assertEqual(updated['id'], self.original['id'])
        self.assertIn('999 ha', updated['description'])
        self.assertEqual(record_store.get_records()[0], updated)
        status, payload = self.request('POST', '/api/ask', {'question': 'top 1 flood observations'})
        result = json.loads(payload)
        self.assertEqual(status, 200)
        self.assertEqual(result['sources'][0], updated)
        self.assertIn('999 ha', result['answer'])
        self.assertIn('2026-10-20', result['answer'])
        status, payload = self.request('POST', '/api/ask', {'question': 'flood in Klang'})
        self.assertIn('999 ha', json.loads(payload)['answer'])
        exports = {}
        for extension in ('csv', 'json', 'geojson'):
            status, payload = self.request('GET', '/sample-data/observations.' + extension)
            self.assertEqual(status, 200)
            exports[extension] = payload.decode()
        self.assertEqual(json.loads(exports['json'])[0], updated)
        row = next(csv.DictReader(io.StringIO(exports['csv'])))
        self.assertEqual(float(row['value']), 999)
        feature = json.loads(exports['geojson'])['features'][0]
        self.assertEqual(feature['properties'], updated)
        self.assertEqual(feature['geometry']['coordinates'], [101.4, 3.2])
        self.assertEqual(rag.load_records()[0], self.original)

    def test_invalid_edits_leave_existing_record_unchanged(self):
        for changes in ({'value': -1}, {'value': True}, {'value': float('nan')},
                        {'value': float('inf')}, {'value': 'large'}, {'latitude': 91},
                        {'state': 'Unknown'}, {'longitude': -181}, {'title': '   '},
                        {'sensor': None}, {'observation_date': '2026-02-30'},
                        {'observation_date': 'invalid'}, {'cloud_cover_pct': 10},
                        {'baseline_date': '2025-10-15'}, {'synthetic': False},
                        {'id': 'FLOOD-999'}, {'theme': 'vegetation'}, {}, []):
            with self.subTest(changes=changes):
                status, _ = self.save(changes)
                self.assertEqual(status, 400)
                self.assertEqual(record_store.get_records()[0], self.original)

    def test_optical_quality_dates_and_ndvi_validation(self):
        original = next(r for r in record_store.get_records() if r['theme'] == 'vegetation')
        status, payload = self.save({'value': 0.8, 'cloud_cover_pct': 50}, original, original['id'])
        self.assertEqual(status, 200)
        updated = json.loads(payload)['record']
        self.assertEqual(updated['quality'], 'limited')
        self.assertIn('0.8', updated['description'])
        self.assertEqual(self.save({'value': 2}, updated, updated['id'])[0], 400)
        change = next(r for r in record_store.get_records() if r['theme'] == 'land-use')
        self.assertEqual(self.save({'baseline_date': '2027-01-01'}, change, change['id'])[0], 400)
        status, payload = self.save({'baseline_date': '2024-01-01', 'observation_date': '2026-10-20'}, change, change['id'])
        self.assertEqual(status, 200)
        self.assertIn('2024-01-01 to 2026-10-20', json.loads(payload)['record']['description'])

    def test_conflicts_and_missing_records(self):
        self.assertEqual(self.save({'value': 200})[0], 200)
        self.assertEqual(self.save({'value': 300})[0], 409)
        self.assertEqual(record_store.get_records()[0]['value'], 200)
        self.assertEqual(self.save({'value': 200}, record_id='FLOOD-999')[0], 404)
        status, _ = self.request('POST', '/api/records/FLOOD-001', {'changes': {'value': 200}})
        self.assertEqual(status, 400)
        self.assertEqual(self.request('POST', '/api/records/FLOOD-001', {}, 'text/plain')[0], 415)

    def test_concurrent_edits_preserve_changes_to_different_records(self):
        originals = record_store.get_records()[:2]
        def edit(record):
            return record_store.update_record(record['id'], {'value': 500}, record)
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(edit, originals))
        self.assertEqual([r['value'] for r in record_store.get_records()[:2]], [500, 500])

    def test_wsgi_saves_json_edits(self):
        body = json.dumps({'changes': {'value': 700}, 'original': self.original}).encode()
        environ = {}
        setup_testing_defaults(environ)
        environ.update(REQUEST_METHOD='POST', PATH_INFO='/api/records/FLOOD-001',
                       CONTENT_LENGTH=str(len(body)), CONTENT_TYPE='application/json',
                       **{'wsgi.input': io.BytesIO(body)})
        captured = {}
        response = application(environ, lambda status, headers: captured.update(status=status))
        payload = json.loads(b''.join(response))
        self.assertEqual(captured['status'], '200 OK')
        self.assertEqual(payload['record']['value'], 700)
        self.assertEqual(record_store.get_records()[0]['value'], 700)

    def test_failed_save_is_reported_and_does_not_change_data(self):
        with patch('record_store.sqlite3.connect', side_effect=OSError('disk unavailable')):
            status, payload = self.save({'value': 500})
        self.assertEqual(status, 500)
        self.assertIn('have not been saved', json.loads(payload)['error'])
        self.assertEqual(record_store.get_records()[0], self.original)
