"""Shared request handling for local development and Heroku/Gunicorn."""
import csv
import io
import json
import mimetypes
import re
import sqlite3
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlsplit

from rag_server.rag import ask, SYSTEM_PROMPT
from backend import admin
from data.record_store import get_records, update_record, export_records, import_csv, EditConflict, RecordNotFound

ROOT = Path(__file__).resolve().parents[1]
MAX_BODY = 16_384
MAX_CSV_BODY = 2 * 1024 * 1024


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
        if path == '/api/settings':
            return self.respond(admin.settings())
        if path == '/api/admin/session':
            return self.respond({'admin': admin.is_admin(self.headers.get('Authorization', ''))})
        if path == '/api/health':
            return self.respond({'status': 'ok', 'records': len(get_records()), 'default_mode': 'offline', 'qwen': 'optional; connection checked when answering'})
        if path == '/api/records':
            return self.respond(get_records())
        if path == '/api/prompt':
            return self.respond({'system_prompt': SYSTEM_PROMPT})
        download = re.fullmatch(r'/sample-data/observations\.(json|csv|geojson)', path)
        if download:
            extension = download.group(1)
            mime = {'json': 'application/json', 'csv': 'text/csv', 'geojson': 'application/geo+json'}[extension]
            return self.respond(export_records(get_records(), extension), content_type=mime + '; charset=utf-8')
        # Explicit allowlist keeps project source and local files off the web server.
        files = {'/': ROOT / 'frontend/index.html', '/app.js': ROOT / 'frontend/app.js', '/styles.css': ROOT / 'frontend/styles.css',
                 '/assets/adl-black.jpeg': ROOT / 'frontend/assets/adl-black.jpeg',
                 '/assets/adl-blue.png': ROOT / 'frontend/assets/adl-blue.png',
                 '/favicon.jpg': ROOT / 'frontend/assets/adl-black.jpeg',
                 '/site.webmanifest': ROOT / 'frontend/site.webmanifest',
                 '/robots.txt': ROOT / 'frontend/robots.txt',
                 '/sitemap.xml': ROOT / 'frontend/sitemap.xml',
                 '/maps/malaysia.geojson': ROOT / 'frontend/maps/malaysia.geojson',
                 '/diagrams/architecture.svg': ROOT / 'docs/diagrams/architecture.svg',
                 '/diagrams/process-flow.svg': ROOT / 'docs/diagrams/process-flow.svg',
                 '/diagrams/plain-language-flow.svg': ROOT / 'docs/diagrams/plain-language-flow.svg',
                 '/sample-data/observations.json': ROOT / 'data/sample-data/observations.json',
                 '/sample-data/observations.csv': ROOT / 'data/sample-data/observations.csv',
                 '/sample-data/observations.geojson': ROOT / 'data/sample-data/observations.geojson'}
        target = files.get(path)
        if not target:
            return self.respond({'error': 'Not found'}, 404)
        mime = mimetypes.guess_type(str(target))[0] or 'text/plain'
        text_asset = mime.startswith('text/') or mime in ('application/json', 'application/manifest+json', 'application/xml', 'application/javascript', 'image/svg+xml')
        return self.respond(target.read_bytes(), content_type=mime + ('; charset=utf-8' if text_asset else ''))

    def do_POST(self):
        path = urlsplit(self.path).path
        edit = re.fullmatch(r'/api/records/([A-Z]+-\d{3})', path)
        importing = path == '/api/records/import'
        admin_route = path in ('/api/admin/login', '/api/admin/logout', '/api/admin/settings')
        if path != '/api/ask' and not edit and not importing and not admin_route:
            return self.respond({'error': 'Not found'}, 404)
        try:
            size = int(self.headers.get('Content-Length', '0'))
            limit = MAX_CSV_BODY if importing else MAX_BODY
            if size <= 0 or size > limit:
                return self.respond({'error': f'Request must contain 1–{limit} bytes.'}, 413)
            authorization = self.headers.get('Authorization', '')
            permissions = admin.settings()
            if (edit or importing) and not permissions['allow_record_updates'] and not admin.is_admin(authorization):
                return self.respond({'error': 'Record updates and CSV uploads are disabled by an admin.'}, 403)
            if importing:
                if self.headers.get('Content-Type', '').split(';')[0].strip().lower() != 'text/csv':
                    return self.respond({'error': 'CSV uploads require text/csv.'}, 415)
                result = import_csv(self.rfile.read(size).decode('utf-8-sig'))
                return self.respond(dict(result, records=get_records()))
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError('Expected a JSON object.')
            if path == '/api/admin/login':
                try:
                    return self.respond({'token': admin.login(data.get('password'))})
                except RuntimeError as exc:
                    return self.respond({'error': str(exc)}, 503)
            if path == '/api/admin/logout':
                admin.logout(authorization)
                return self.respond({'admin': False})
            if path == '/api/admin/settings':
                if not admin.is_admin(authorization):
                    return self.respond({'error': 'Sign in as an admin to change settings.'}, 403)
                return self.respond(admin.settings(data))
            if edit:
                if self.headers.get('Content-Type', '').split(';')[0].strip().lower() != 'application/json':
                    return self.respond({'error': 'Record edits require application/json.'}, 415)
                updated = update_record(edit.group(1), data.get('changes'), data.get('original'))
                return self.respond({'record': updated})
            question = data.get('question', '')
            if not isinstance(question, str) or not 3 <= len(question.strip()) <= 1000:
                raise ValueError('Enter a question between 3 and 1000 characters.')
            mode, theme, style = data.get('mode', 'offline'), data.get('theme', 'all'), data.get('style', 'concise')
            if mode not in ('offline', 'qwen') or theme not in ('all', 'flood', 'vegetation', 'land-use', 'coastal') or style not in ('concise', 'briefing'):
                raise ValueError('Invalid mode, topic or answer style.')
            web_search = data.get('web_search', False)
            if type(web_search) is not bool:
                raise ValueError('Web search must be true or false.')
            if permissions['excerpt_only'] and (mode != 'offline' or web_search):
                return self.respond({'error': 'Only excerpt mode is currently allowed by the admin.'}, 403)
            result = ask(question.strip(), get_records(), mode, theme, style, web_search=web_search)
            result['question'] = question.strip()
            return self.respond(result)
        except EditConflict as exc:
            return self.respond({'error': str(exc)}, 409)
        except RecordNotFound as exc:
            return self.respond({'error': str(exc)}, 404)
        except PermissionError as exc:
            return self.respond({'error': str(exc)}, 403)
        except (OSError, sqlite3.Error):
            return self.respond({'error': 'Could not save this record. Try again; your edits have not been saved.'}, 500)
        except (ValueError, TypeError, UnicodeDecodeError, csv.Error) as exc:
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
        {'Content-Length': environ.get('CONTENT_LENGTH', '0'),
         'Content-Type': environ.get('CONTENT_TYPE', ''),
         'Authorization': environ.get('HTTP_AUTHORIZATION', '')},
        environ.get('wsgi.input', io.BytesIO()),
    )
    start_response(f'{status} {HTTPStatus(status).phrase}', headers)
    return [body]
