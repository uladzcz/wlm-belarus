import http.server
import socketserver
import os
import sys
import webbrowser

PORT = 8085
DIRECTORY = os.path.dirname(os.path.abspath(__file__))

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def end_headers(self):
        # Enable CORS and caching headers
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache')
        super().end_headers()

print(f"Запуск сервера Вікі любіць славутасці (WLM Belarus)...")
print(f"Адрас: http://localhost:{PORT}")
print(f"Каталог: {DIRECTORY}")

if hasattr(http.server, 'ThreadingHTTPServer'):
    ServerClass = http.server.ThreadingHTTPServer
else:
    class ServerClass(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True

with ServerClass(("", PORT), Handler) as httpd:
    print(f"Сервер актыўны на порце {PORT}. Каб спыніць, націсніце Ctrl+C.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nСервер спынены.")
