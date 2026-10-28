"""Shared request handling for local development and Heroku/Gunicorn."""
import io
import json
import mimetypes
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlsplit

from rag import ask, load_records, SYSTEM_PROMPT

ROOT = Path(__file__).resolve().parent
RECORDS = load_records()
MAX_BODY = 16_384


class Request:
    def __init__(self, path, headers, body):
        self.path = path
        self.headers = headers
        self.rfile = body

    def respond(self, data, status=200, content_type='application/json; charset=utf-8'):
        body = data if isinstance(data, bytes) else json.dumps(data).encode()
        return status, [
            ('Content-Type', content_type),
            ('Content-Length', str(len(body))),
            ('X-Content-Type-Options', 'nosniff'),
            ('Cache-Control', 'no-store'),
        ], body

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/api/health':
            return self.respond({'status': 'ok', 'records': len(RECORDS), 'default_mode': 'offline', 'qwen': 'optional; connection checked when answering'})
        if path == '/api/records':
            return self.respond(RECORDS)
        if path == '/api/prompt':
            return self.respond({'system_prompt': SYSTEM_PROMPT})
        # Explicit allowlist keeps project source and local files off the web server.
        files = {'/': ROOT / 'app/index.html', '/app.js': ROOT / 'app/app.js', '/styles.css': ROOT / 'app/styles.css',
                 '/sample-data/observations.json': ROOT / 'sample-data/observations.json',
                 '/sample-data/observations.csv': ROOT / 'sample-data/observations.csv',
                 '/sample-data/observations.geojson': ROOT / 'sample-data/observations.geojson'}
        target = files.get(path)
        if not target:
            return self.respond({'error': 'Not found'}, 404)
        mime = mimetypes.guess_type(str(target))[0] or 'text/plain'
        return self.respond(target.read_bytes(), content_type=mime + '; charset=utf-8')

    def do_POST(self):
        if urlsplit(self.path).path != '/api/ask':
            return self.respond({'error': 'Not found'}, 404)
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if size <= 0 or size > MAX_BODY:
                return self.respond({'error': 'Request must contain 1–16384 bytes.'}, 413)
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError('Expected a JSON object.')
            question = data.get('question', '')
            if not isinstance(question, str) or not 3 <= len(question.strip()) <= 1000:
                raise ValueError('Enter a question between 3 and 1000 characters.')
            mode, theme, style = data.get('mode', 'offline'), data.get('theme', 'all'), data.get('style', 'concise')
            top_k = data.get('top_k', 3)
            if mode not in ('offline', 'qwen') or theme not in ('all', 'flood', 'vegetation', 'land-use', 'coastal') or style not in ('concise', 'briefing'):
                raise ValueError('Invalid mode, topic or answer style.')
            if type(top_k) is not int or not 1 <= top_k <= 6:
                raise ValueError('Source count must be an integer from 1 to 6.')
            result = ask(question.strip(), RECORDS, mode, theme, top_k, style)
            result['question'] = question.strip()
            return self.respond(result)
        except (ValueError, TypeError, UnicodeDecodeError) as exc:
            return self.respond({'error': str(exc)}, 400)



def dispatch(method, path, headers, body):
    request = Request(path, headers, body)
    if method in ('GET', 'HEAD'):
        status, response_headers, content = request.do_GET()
        return status, response_headers, b'' if method == 'HEAD' else content
    if method == 'POST':
        return request.do_POST()
    return request.respond({'error': 'Method not allowed'}, 405)


def application(environ, start_response):
    status, headers, body = dispatch(
        environ['REQUEST_METHOD'], environ.get('PATH_INFO', '/'),
        {'Content-Length': environ.get('CONTENT_LENGTH', '0')},
        environ.get('wsgi.input', io.BytesIO()),
    )
    start_response(f'{status} {HTTPStatus(status).phrase}', headers)
    return [body]
