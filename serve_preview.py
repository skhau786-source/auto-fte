#!/usr/bin/env python3
"""Simple HTTP server for previewing the project HTML page."""
import http.server
import socketserver
import sys

PORT = 8080
DIRECTORY = "frontend-fte/public"

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print(f"Serving preview at http://localhost:{PORT}/preview.html")
    httpd.serve_forever()
