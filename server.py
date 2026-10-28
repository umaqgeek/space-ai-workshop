"""Dependency-free local workshop server. Python 3.9+."""
import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from rag import ask, load_records, SYSTEM_PROMPT

ROOT = Path(__file__).resolve().parent
RECORDS = load_records()
MAX_BODY = 16_384


class Handler(BaseHTTPRequestHandler):
    def respond(self, data, status=200, content_type='application/json; charset=utf-8'):
        body = data if isinstance(data, bytes) else json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

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
                 '/workshop-guide': ROOT / 'docs/FACILITATOR_GUIDE.md',
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
            self.respond(result)
        except (ValueError, TypeError, UnicodeDecodeError) as exc:
            self.respond({'error': str(exc)}, 400)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8080)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f'SpaceLab ready at http://{args.host}:{args.port} · {len(RECORDS)} synthetic records', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
