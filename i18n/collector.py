"""Receives the texts the app shows during the tests (collect mode) and keeps them, one JSON list per line."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import os
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'runtime.jsonl')
class H(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get('Content-Length') or 0); b = self.rfile.read(n)
        with open(OUT, 'ab') as f: f.write(b + b'\n')
        self.send_response(204); self.send_header('Access-Control-Allow-Origin', '*'); self.end_headers()
    def log_message(self, *a): pass
HTTPServer(('127.0.0.1', 9299), H).serve_forever()
