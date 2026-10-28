"""Dependency-free local space-tech RAG server. Python 3.9+."""
import argparse
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from webapp import dispatch


class Handler(BaseHTTPRequestHandler):
    def handle_request(self):
        status, headers, body = dispatch(self.command, self.path, self.headers, self.rfile)
        self.send_response(status)
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    do_GET = handle_request
    do_HEAD = handle_request
    do_POST = handle_request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='0.0.0.0' if os.environ.get('PORT') else '127.0.0.1')
    parser.add_argument('--port', type=int, default=int(os.environ.get('PORT', '8080')))
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f'SpaceLab ready at http://{args.host}:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
