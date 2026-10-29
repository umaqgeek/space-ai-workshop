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

    def test_state_queries_only_retrieve_that_state(self):
        for state, count in [('Selangor', 6), ('Sabah', 3), ('Sarawak', 2), ('Perak', 2)]:
            with self.subTest(state=state):
                sources = rag.retrieve(f'flood observations in {state}', self.records)
                self.assertEqual(len(sources), count)
                self.assertTrue(all(r['state'] == state for r in sources))

    def test_comparison_across_east_and_peninsular_malaysia(self):
        sources = rag.retrieve('Compare vegetation in Kuching and George Town', self.records)
        self.assertEqual({r['location'] for r in sources}, {'Kuching', 'George Town'})
        self.assertTrue(all(r['theme'] == 'vegetation' for r in sources))

    def test_place_names_require_whole_words(self):
        sources = rag.retrieve('flood observations in Miriaman', self.records)
        self.assertGreater(len({r['location'] for r in sources}), 1)

    def test_default_retrieval_has_no_source_cap(self):
        self.assertEqual(len(rag.retrieve('flood', self.records)), 28)

    def test_nationwide_top_five_are_computed_from_all_records(self):
        question = 'from all data, list top 5 worst flood in Malaysia, including all states'
        with patch('rag.urllib.request.urlopen') as call:
            result = rag.ask(question, self.records, mode='qwen')
        call.assert_not_called()
        self.assertEqual(result['mode'], 'data')
        self.assertEqual([r['id'] for r in result['sources']],
                         ['FLOOD-024', 'FLOOD-018', 'FLOOD-012', 'FLOOD-023', 'FLOOD-017'])
        self.assertEqual([r['value'] for r in result['sources']], [221, 219, 217, 184, 182])
        self.assertIn('not overall flood severity', result['answer'])
        self.assertNotIn('Refs:', result['answer'].split('\n\nRefs: ')[0])

    def test_ranking_filters_and_direction(self):
        result = rag.ask('bottom 2 flood observations in Sabah', self.records)
        self.assertEqual([r['value'] for r in result['sources']], [149, 184])
        self.assertTrue(all(r['state'] == 'Sabah' for r in result['sources']))
        result = rag.ask('highest NDVI in Malaysia', self.records)
        self.assertEqual(result['sources'][0]['value'], max(r['value'] for r in self.records if r['theme'] == 'vegetation'))

    def test_list_all_returns_every_matching_record_without_llm(self):
        with patch('rag.urllib.request.urlopen') as call:
            result = rag.ask('List all flood observations', self.records, mode='qwen')
        call.assert_not_called()
        self.assertEqual(len(result['sources']), 28)
        self.assertEqual(len(rag.citation_ids(result['answer'])), 28)
        self.assertIn('28.', result['answer'])
        self.assertEqual(len(rag.ask('List all observations', self.records)['sources']), 103)
        self.assertEqual(len(rag.ask('Compare Kuching and Kota Kinabalu', self.records)['sources']), 7)

    def test_ambiguous_rankings_and_missing_data(self):
        self.assertEqual(rag.ask('top 5 observations', self.records)['status'], 'insufficient')
        self.assertEqual(rag.ask('list all moons of Jupiter', self.records)['sources'], [])
        result = rag.ask('top 50 flood observations in Sabah', self.records)
        self.assertEqual(len(result['sources']), 3)
        self.assertIn('Only 3 matching observations', result['answer'])
        result = rag.ask('top 5 coastal observations in Shah Alam', self.records)
        self.assertEqual(result['status'], 'insufficient')

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

    def test_offline_citations_only_appear_in_footer(self):
        result = rag.ask('Compare flood observations in Klang and Sepang', self.records)
        body, refs = result['answer'].rsplit('\n\nRefs: ', 1)
        self.assertNotRegex(body, r'\[[A-Z]+-\d{3}\]')
        self.assertEqual(set(refs.split(', ')), {'[FLOOD-001]', '[FLOOD-004]'})
        self.assertIn('142', body)
        self.assertIn('37', body)

    def test_qwen_citations_move_to_deduplicated_footer(self):
        result = self.qwen_response('Possible water is 142 ha [FLOOD-001].\n\nInvented observation [FLOOD-001].')
        self.assertEqual(result['mode'], 'qwen')
        self.assertIn('Possible water is 142 ha.\n\nInvented observation.', result['answer'])
        self.assertTrue(result['answer'].endswith('\n\nRefs: [FLOOD-001]'))
        self.assertEqual(result['answer'].count('[FLOOD-001]'), 1)

    def test_grouped_vegetation_citations_move_below_response(self):
        prose = ('As of 2026-10-15, Kota Kinabalu had a fictional NDVI value of 0.76, '
                 'while Kuching had a fictional NDVI value of 0.5. Higher NDVI can '
                 'indicate greener vegetation, though it does not establish species, '
                 'crop health, or biodiversity [VEGETATION-021, VEGETATION-023]. '
                 'Both observations are limited by clouds and mixed pixels '
                 '[VEGETATION-021, VEGETATION-023].')
        response = json.dumps({'message': {'content': prose}}).encode()
        with patch('rag.urllib.request.urlopen', return_value=io.BytesIO(response)):
            result = rag.ask('Compare vegetation in Kota Kinabalu and Kuching', self.records, mode='qwen')
        self.assertEqual(result['mode'], 'qwen')
        body, refs = result['answer'].rsplit('\n\nRefs: ', 1)
        self.assertNotIn('[VEGETATION-', body)
        self.assertIn('biodiversity. Both observations', body)
        self.assertTrue(body.endswith('clouds and mixed pixels.'))
        self.assertEqual(refs, '[VEGETATION-021], [VEGETATION-023]')

    def test_mixed_single_and_grouped_citations_are_deduplicated(self):
        answer = rag.move_references_below('First [FLOOD-001]. Second [ FLOOD-004,FLOOD-001 ].')
        self.assertEqual(answer, 'First. Second.\n\nRefs: [FLOOD-001], [FLOOD-004]')

    def test_grouped_fabricated_citation_fails_validation(self):
        result = self.qwen_response('Possible water is 142 ha [FLOOD-001, FLOOD-999].')
        self.assertEqual(result['mode'], 'offline')
        self.assertIn('citation checks', result['notice'])
        self.assertNotIn('FLOOD-999', result['answer'])

    def test_no_evidence_has_no_reference_footer(self):
        result = rag.ask('What is the mass of Jupiter?', self.records)
        self.assertNotIn('Refs:', result['answer'])

    def test_qwen_fabricated_or_missing_citations_fall_back(self):
        for response in ('The answer is 142 ha.', 'The answer is 142 ha [FLOOD-999].'):
            with self.subTest(response=response):
                result = self.qwen_response(response)
                self.assertEqual(result['mode'], 'offline')
                self.assertIn('citation checks', result['notice'])


class DataTests(unittest.TestCase):
    def test_nationwide_coverage_and_theme_availability(self):
        records = rag.load_records()
        self.assertEqual(len({r['location'] for r in records}), 28)
        self.assertEqual({r['state'] for r in records}, {
            'Johor', 'Kedah', 'Kelantan', 'Melaka', 'Negeri Sembilan', 'Pahang',
            'Penang', 'Perak', 'Perlis', 'Sabah', 'Sarawak', 'Selangor',
            'Terengganu', 'Kuala Lumpur', 'Putrajaya', 'Labuan',
        })
        for place in {r['location'] for r in records}:
            themes = {r['theme'] for r in records if r['location'] == place}
            self.assertTrue({'flood', 'vegetation', 'land-use'} <= themes)
        self.assertEqual(sum(r['theme'] == 'coastal' for r in records), 19)

    def test_generator_reproduces_bundled_exports(self):
        import contextlib
        import tempfile
        from scripts import generate_data

        with tempfile.TemporaryDirectory() as directory:
            with patch.object(generate_data, 'ROOT', Path(directory)), contextlib.redirect_stdout(io.StringIO()):
                generate_data.generate()
            for name in ('observations.json', 'observations.csv', 'observations.geojson'):
                self.assertEqual((Path(directory) / name).read_bytes(), (ROOT / 'sample-data' / name).read_bytes())

    def test_export_formats_agree(self):
        records = rag.load_records()
        with (ROOT / 'sample-data/observations.csv').open() as f:
            rows = list(csv.DictReader(f))
        geo = json.loads((ROOT / 'sample-data/observations.geojson').read_text())
        self.assertEqual(len(records), 103)
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
                     '/diagrams/architecture.svg', '/diagrams/process-flow.svg',
                     '/diagrams/plain-language-flow.svg',
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

    def test_api_has_no_legacy_source_cap(self):
        status, body, _ = self.request('/api/ask', json.dumps({'question': 'list all flood observations', 'top_k': 3}).encode())
        self.assertEqual(status, 200)
        self.assertEqual(len(json.loads(body)['sources']), 28)

    def test_bad_inputs_return_client_errors(self):
        payloads = [b'{', b'[]', b'null', b'\xff', b'{}', b'{"question":3}',
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
