import csv
import io
import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import rag
from server import Handler

ROOT = Path(__file__).resolve().parents[1]


class RetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = rag.load_records()

    def test_sample_query_answer_key(self):
        queries = json.loads((ROOT / 'sample-data/practice-queries.json').read_text())
        for query in queries:
            with self.subTest(question=query['question']):
                result = rag.ask(query['question'], self.records)
                self.assertEqual(set(query['expected_source_ids']), {r['id'] for r in result['sources']})

    def test_comparison_retrieves_two_places(self):
        result = rag.ask('Compare vegetation in Hulu Langat and Shah Alam.', self.records)
        self.assertIn('0.78', result['answer'])
        self.assertIn('0.51', result['answer'])
        self.assertTrue(all(r['theme'] == 'vegetation' for r in result['sources']))

    def test_filter_does_not_substitute_wrong_place(self):
        result = rag.ask('coastal observations in Shah Alam', self.records, theme='coastal')
        self.assertEqual(result['status'], 'insufficient')
        self.assertEqual(result['sources'], [])

    def test_top_k_limits_evidence(self):
        self.assertEqual(len(rag.retrieve('flood', self.records, top_k=1)), 1)
        self.assertEqual(len(rag.retrieve('flood', self.records, top_k=6)), 6)

    def test_forecasts_are_not_sent_to_llm(self):
        with patch('rag.urllib.request.urlopen') as call:
            result = rag.ask('Will Klang flood tomorrow?', self.records, mode='qwen')
        call.assert_not_called()
        self.assertEqual(result['status'], 'insufficient')
        self.assertIn('cannot answer live conditions', result['answer'])

    def test_empty_evidence_never_calls_qwen(self):
        with patch('rag.urllib.request.urlopen') as call:
            result = rag.ask('What is the mass of Jupiter?', self.records, mode='qwen')
        call.assert_not_called()
        self.assertEqual(result['status'], 'insufficient')

    def test_ollama_failure_falls_back_transparently(self):
        with patch('rag.urllib.request.urlopen', side_effect=OSError('offline')):
            result = rag.ask('flood in Klang', self.records, mode='qwen')
        self.assertEqual(result['mode'], 'offline')
        self.assertIn('Qwen unavailable', result['notice'])
        self.assertIn('142', result['answer'])

    def qwen_response(self, content):
        body = json.dumps({'message': {'content': content}}).encode()
        with patch('rag.urllib.request.urlopen', return_value=io.BytesIO(body)) as call:
            result = rag.ask('flood in Klang', self.records, mode='qwen')
            payload = json.loads(call.call_args.args[0].data)
            self.assertFalse(payload['stream'])
            self.assertIn('FLOOD-001', payload['messages'][1]['content'])
            self.assertEqual(payload['messages'][0]['role'], 'system')
        return result

    def test_qwen_valid_citation(self):
        result = self.qwen_response('Fictional possible surface water is 142 ha [FLOOD-001].')
        self.assertEqual(result['mode'], 'qwen')
        self.assertIsNone(result['notice'])

    def test_qwen_fabricated_or_missing_citations_fall_back(self):
        for response in ('The answer is 142 ha.', 'The answer is 142 ha [FLOOD-999].'):
            with self.subTest(response=response):
                result = self.qwen_response(response)
                self.assertEqual(result['mode'], 'offline')
                self.assertIn('citation checks', result['notice'])


class DataTests(unittest.TestCase):
    def test_export_formats_agree(self):
        records = rag.load_records()
        with (ROOT / 'sample-data/observations.csv').open() as f:
            rows = list(csv.DictReader(f))
        geo = json.loads((ROOT / 'sample-data/observations.geojson').read_text())
        self.assertEqual(len(records), 22)
        self.assertEqual({r['id'] for r in records}, {r['id'] for r in rows})
        self.assertEqual(geo['type'], 'FeatureCollection')
        self.assertEqual([f['properties'] for f in geo['features']], records)
        for record, row, feature in zip(records, rows, geo['features']):
            self.assertTrue(record['synthetic'])
            self.assertEqual(float(row['value']), record['value'])
            self.assertEqual(feature['geometry']['coordinates'], [record['longitude'], record['latitude']])
            self.assertEqual(row['description'], record['description'])


class QuietHandler(Handler):
    def log_message(self, *_args):
        pass


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def request(self, path, data=None):
        request = urllib.request.Request(self.base + path, data=data, headers={'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, response.read(), response.headers
        except urllib.error.HTTPError as response:
            try:
                return response.code, response.read(), response.headers
            finally:
                response.close()

    def test_page_assets_and_downloads(self):
        for path in ('/', '/app.js', '/styles.css', '/api/health', '/api/records', '/api/prompt',
                     '/sample-data/observations.csv', '/sample-data/observations.json',
                     '/sample-data/observations.geojson'):
            with self.subTest(path=path):
                status, body, headers = self.request(path)
                self.assertEqual(status, 200)
                self.assertGreater(len(body), 10)
                self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')

    def test_project_files_are_not_exposed(self):
        for path in ('/server.py', '/../rag.py', '/.git/config', '/sample-data/../../server.py', '/workshop-guide'):
            self.assertEqual(self.request(path)[0], 404)

    def test_complete_answer_over_http(self):
        status, body, _ = self.request('/api/ask', json.dumps({'question':'flood observations in Klang'}).encode())
        self.assertEqual(status, 200)
        result = json.loads(body)
        self.assertEqual(result['sources'][0]['id'], 'FLOOD-001')
        self.assertIn('142', result['answer'])

    def test_bad_inputs_return_client_errors(self):
        payloads = [b'{', b'[]', b'null', b'\xff', b'{}', b'{"question":3}',
                    json.dumps({'question':'flood', 'top_k':True}).encode(),
                    json.dumps({'question':'flood', 'top_k':7}).encode(),
                    json.dumps({'question':'flood', 'mode':'remote'}).encode(),
                    json.dumps({'question':'flood', 'theme':'rainfall'}).encode(),
                    json.dumps({'question':'flood', 'style':'invent'}).encode(),
                    json.dumps({'question':'x'*1001}).encode()]
        for payload in payloads:
            with self.subTest(payload=payload[:80]):
                self.assertEqual(self.request('/api/ask', payload)[0], 400)
        self.assertEqual(self.request('/api/ask', b'x'*17000)[0], 413)


if __name__ == '__main__':
    unittest.main()
