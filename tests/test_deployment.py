import io
import json
import os
import unittest
from unittest.mock import patch
from wsgiref.util import setup_testing_defaults
from wsgiref.validate import validator

from rag_server import rag
from backend.webapp import application


class WsgiTests(unittest.TestCase):
    def request(self, method, path, body=b'', length=None):
        environ = {}
        setup_testing_defaults(environ)
        environ.update(REQUEST_METHOD=method, PATH_INFO=path, QUERY_STRING='',
                       CONTENT_LENGTH=str(len(body)) if length is None else length,
                       **{'wsgi.input': io.BytesIO(body)})
        captured = {}

        def start_response(status, headers, exc_info=None):
            captured.update(status=int(status.split()[0]), headers=dict(headers))

        response = validator(application)(environ, start_response)
        try:
            captured['body'] = b''.join(response)
        finally:
            response.close()
        return captured

    def test_wsgi_serves_assets_api_and_downloads(self):
        for path in ('/', '/app.js', '/styles.css', '/api/health', '/api/records',
                     '/diagrams/architecture.svg', '/diagrams/process-flow.svg',
                     '/diagrams/plain-language-flow.svg', '/maps/malaysia.geojson',
                     '/api/prompt', '/sample-data/observations.json',
                     '/sample-data/observations.csv', '/sample-data/observations.geojson'):
            with self.subTest(path=path):
                response = self.request('GET', path)
                self.assertEqual(response['status'], 200)
                self.assertEqual(int(response['headers']['Content-Length']), len(response['body']))

    def test_wsgi_answer_contains_expected_evidence(self):
        response = self.request('POST', '/api/ask', json.dumps({'question': 'flood in Klang'}).encode())
        self.assertEqual(response['status'], 200)
        self.assertEqual(json.loads(response['body'])['sources'][0]['id'], 'FLOOD-001')

    def test_wsgi_rejects_bad_bodies_and_unknown_routes(self):
        self.assertEqual(self.request('POST', '/api/ask', b'{')['status'], 400)
        self.assertEqual(self.request('POST', '/api/ask', length='17000')['status'], 413)
        self.assertEqual(self.request('GET', '/.env')['status'], 404)
        self.assertEqual(self.request('GET', '/webapp.py')['status'], 404)
        self.assertEqual(self.request('DELETE', '/api/records')['status'], 405)

    def test_head_returns_headers_without_body(self):
        response = self.request('HEAD', '/')
        self.assertEqual(response['status'], 200)
        self.assertEqual(response['body'], b'')
        self.assertGreater(int(response['headers']['Content-Length']), 0)


class HostedModelTests(unittest.TestCase):
    def test_hosted_model_authentication_and_heroku_timeout(self):
        body = json.dumps({'message': {'content': '142 ha [FLOOD-001].'}}).encode()
        config = {'DYNO': 'web.1', 'OLLAMA_URL': 'https://model.example.test',
                  'OLLAMA_API_KEY': 'test-placeholder', 'OLLAMA_MODEL': 'qwen3:4b'}
        with patch.dict(os.environ, config, clear=True), patch('rag_server.rag.urllib.request.urlopen', return_value=io.BytesIO(body)) as call:
            result = rag.ask('flood in Klang', rag.load_records(), mode='qwen')
        self.assertEqual(result['mode'], 'qwen')
        request = call.call_args.args[0]
        self.assertEqual(request.full_url, 'https://model.example.test/api/chat')
        self.assertEqual(request.get_header('Authorization'), 'Bearer test-placeholder')
        self.assertEqual(call.call_args.kwargs['timeout'], 20)

    def test_secret_never_sent_to_plain_http(self):
        config = {'OLLAMA_URL': 'http://model.example.test', 'OLLAMA_API_KEY': 'test-placeholder'}
        with patch.dict(os.environ, config, clear=True), patch('rag_server.rag.urllib.request.urlopen') as call:
            result = rag.ask('flood in Klang', rag.load_records(), mode='qwen')
        call.assert_not_called()
        self.assertEqual(result['mode'], 'offline')
        self.assertNotIn('test-placeholder', json.dumps(result))

    def test_invalid_timeout_falls_back(self):
        for timeout in ('invalid', '0', '-1', '61', 'nan'):
            with self.subTest(timeout=timeout), patch.dict(os.environ, {'OLLAMA_TIMEOUT_SECONDS': timeout}, clear=True), patch('rag_server.rag.urllib.request.urlopen') as call:
                result = rag.ask('flood in Klang', rag.load_records(), mode='qwen')
                self.assertEqual(result['mode'], 'offline')
                call.assert_not_called()
