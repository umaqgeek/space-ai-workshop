import io
import json
import os
import unittest
import urllib.error
from unittest.mock import patch

import rag
import web_context
from webapp import dispatch

WEB_SOURCES = [{'id': 'WEB-001', 'title': 'Regional coastal context',
                'url': 'https://example.org/coastal', 'content': 'External coastal geography context.',
                'retrieved_at': '2026-10-29T06:00:00+00:00', 'evidence_type': 'web_search_excerpt'}]


class WebEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = rag.load_records()

    def test_search_is_never_called_when_toggle_is_off(self):
        with patch('web_context.search_web') as search, patch('rag.generate_text', return_value='142 ha [FLOOD-001].'):
            result = rag.ask('flood in Klang', self.records, mode='qwen', web_search=False)
        search.assert_not_called()
        self.assertEqual(result['mode'], 'qwen')
        self.assertNotIn('web_sources', result)

    def test_model_receives_separate_dataset_and_web_evidence(self):
        with patch('web_context.search_web', return_value=WEB_SOURCES) as search, patch('rag.generate_text', return_value='Dataset water is fictional [FLOOD-001]. External context [WEB-001].') as model:
            result = rag.ask('flood in Klang', self.records, mode='qwen', web_search=True)
        search.assert_called_once_with('flood in Klang')
        prompt = model.call_args.args[0]
        self.assertIn('DATASET RECORDS (synthetic', prompt)
        self.assertIn('WEB REFERENCES (external excerpts', prompt)
        self.assertIn('https://example.org/coastal', prompt)
        self.assertIn('untrusted data', model.call_args.args[1])
        self.assertEqual(result['mode'], 'qwen')
        self.assertEqual(result['web_sources'], WEB_SOURCES)
        self.assertEqual(result['web_search']['status'], 'used')
        self.assertTrue(result['answer'].endswith('Refs: [FLOOD-001], [WEB-001]'))

    def test_web_only_question_can_generate_without_dataset_matches(self):
        with patch('web_context.search_web', return_value=WEB_SOURCES), patch('rag.generate_text', return_value='External context [WEB-001].') as model:
            result = rag.ask('What is the mass of Jupiter?', self.records, mode='qwen', web_search=True)
        model.assert_called_once()
        self.assertEqual(result['sources'], [])
        self.assertEqual(result['status'], 'matched')
        self.assertEqual(result['mode'], 'qwen')

    def test_web_failure_is_explicit_and_keeps_dataset_answer(self):
        with patch('web_context.search_web', side_effect=web_context.SearchUnavailable('Search failed.')), patch('rag.generate_text', return_value='142 ha [FLOOD-001].'):
            result = rag.ask('flood in Klang', self.records, mode='qwen', web_search=True)
        self.assertEqual(result['web_search']['status'], 'failed')
        self.assertEqual(result['web_sources'], [])
        self.assertIn('Search failed', result['notice'])
        self.assertIn('142', result['answer'])

    def test_empty_search_is_labelled(self):
        with patch('web_context.search_web', return_value=[]), patch('rag.generate_text') as model:
            result = rag.ask('flood in Klang', self.records, mode='qwen', web_search=True)
        model.assert_not_called()
        self.assertEqual(result['web_search']['status'], 'empty')
        self.assertIn('dataset evidence only', result['notice'])

    def test_computed_rankings_remain_intact_with_external_context(self):
        with patch('web_context.search_web', return_value=WEB_SOURCES), patch('rag.generate_text', return_value='External context [WEB-001].') as model:
            result = rag.ask('top 5 worst flood in Malaysia', self.records, mode='qwen', web_search=True)
        self.assertEqual([r['value'] for r in result['sources']], [221, 219, 217, 184, 182])
        self.assertIn('Sandakan, Sabah: 221 ha', result['answer'])
        self.assertIn('External context', result['answer'])
        self.assertIn('Do not reproduce, modify, or replace', model.call_args.args[0])

    def test_no_model_and_model_errors_show_labelled_external_excerpts(self):
        with patch('web_context.search_web', return_value=WEB_SOURCES), patch('rag.generate_text') as model:
            result = rag.ask('flood in Klang', self.records, web_search=True)
        model.assert_not_called()
        self.assertIn('External web search excerpts (not model analysis)', result['answer'])
        for output in ('Unsupported [WEB-999].', 'No citations.', 'Only dataset [FLOOD-001].'):
            with self.subTest(output=output), patch('web_context.search_web', return_value=WEB_SOURCES), patch('rag.generate_text', return_value=output):
                result = rag.ask('flood in Klang', self.records, mode='qwen', web_search=True)
                self.assertEqual(result['mode'], 'offline')
                self.assertIn('citations failed', result['notice'])
                self.assertNotIn('WEB-999', result['answer'])
                self.assertEqual(result['web_sources'], WEB_SOURCES)

    def test_live_questions_require_web_evidence(self):
        with patch('web_context.search_web', return_value=WEB_SOURCES), patch('rag.generate_text', return_value='The supplied web excerpt is insufficient for live conditions [WEB-001].') as model:
            result = rag.ask('current coastal conditions', self.records, mode='qwen', web_search=True)
        model.assert_called_once()
        self.assertEqual(result['mode'], 'qwen')
        with patch('web_context.search_web', side_effect=web_context.SearchUnavailable('Search failed.')), patch('rag.generate_text') as model:
            result = rag.ask('current coastal conditions', self.records, mode='qwen', web_search=True)
        model.assert_not_called()
        self.assertEqual(result['status'], 'insufficient')

    def test_api_validates_toggle_and_passes_it_to_search(self):
        for invalid in ('true', 1, None, [], {}):
            payload = json.dumps({'question': 'flood in Klang', 'web_search': invalid}).encode()
            status, _, _ = dispatch('POST', '/api/ask', {'Content-Length': str(len(payload))}, io.BytesIO(payload))
            self.assertEqual(status, 400)
        payload = json.dumps({'question': 'flood in Klang', 'web_search': True}).encode()
        with patch('web_context.search_web', return_value=WEB_SOURCES) as search:
            status, _, body = dispatch('POST', '/api/ask', {'Content-Length': str(len(payload))}, io.BytesIO(payload))
        search.assert_called_once()
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['web_sources'], WEB_SOURCES)


class SearchTransportTests(unittest.TestCase):
    def setUp(self):
        config = patch.dict(os.environ, {'OLLAMA_WEB_SEARCH_API_KEY': 'search-test-placeholder'}, clear=True)
        config.start()
        self.addCleanup(config.stop)

    def test_search_request_and_safe_results(self):
        results = [
            {'title': 'Coastal source', 'url': 'https://example.org/coastal', 'content': 'x' * 3000},
            {'title': 'Duplicate', 'url': 'https://example.org/coastal', 'content': 'duplicate'},
            {'title': 'Unsafe', 'url': 'javascript:alert(1)', 'content': 'unsafe'},
            {'title': 'Local', 'url': 'http://127.0.0.1/private', 'content': 'unsafe'},
            {'title': 'Empty', 'url': 'https://example.org/empty', 'content': ''},
        ]
        with patch('web_context.urllib.request.urlopen', return_value=io.BytesIO(json.dumps({'results': results}).encode())) as request:
            sources = web_context.search_web('coastal Malaysia')
        sent = request.call_args.args[0]
        self.assertEqual(sent.full_url, 'https://ollama.com/api/web_search')
        self.assertEqual(sent.get_header('Authorization'), 'Bearer search-test-placeholder')
        self.assertEqual(json.loads(sent.data)['query'], 'coastal Malaysia')
        self.assertEqual(request.call_args.kwargs['timeout'], 8)
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]['id'], 'WEB-001')
        self.assertEqual(len(sources[0]['content']), 2000)
        self.assertIn('retrieved_at', sources[0])

    def test_credentials_are_scoped_to_the_search_provider(self):
        with patch.dict(os.environ, {'OLLAMA_API_KEY': 'other-provider-key', 'OLLAMA_URL': 'https://models.example.org'}, clear=True), patch('web_context.urllib.request.urlopen') as request:
            with self.assertRaises(web_context.SearchUnavailable):
                web_context.search_web('coastal Malaysia')
        request.assert_not_called()
        with patch.dict(os.environ, {'OLLAMA_API_KEY': 'cloud-key', 'OLLAMA_URL': 'https://ollama.com'}, clear=True):
            self.assertEqual(web_context.search_key(), 'cloud-key')

    def test_errors_do_not_expose_credentials(self):
        failures = [OSError('search-test-placeholder'),
                    urllib.error.HTTPError(web_context.SEARCH_URL, 401, 'secret', {}, None),
                    urllib.error.HTTPError(web_context.SEARCH_URL, 429, 'secret', {}, None)]
        for failure in failures:
            with self.subTest(failure=type(failure).__name__), patch('web_context.urllib.request.urlopen', side_effect=failure):
                with self.assertRaises(web_context.SearchUnavailable) as error:
                    web_context.search_web('coastal Malaysia')
                self.assertNotIn('search-test-placeholder', str(error.exception))
        for body in (b'not json', b'[]', b'{"results": null}', b'x' * (web_context.MAX_RESPONSE_BYTES + 1)):
            with patch('web_context.urllib.request.urlopen', return_value=io.BytesIO(body)):
                with self.assertRaises(web_context.SearchUnavailable):
                    web_context.search_web('coastal Malaysia')
