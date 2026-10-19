# serves the built frontend (frontend/dist) like Vite does and forwards /api to Flask with Host/Origin localhost:5173
import http.server, socketserver, requests, os
ROOT = os.environ.get("E2E_STATIC", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "frontend", "dist"))
class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k): super().__init__(*a, directory=ROOT, **k)
    def log_message(self, *a): pass
    def _proxy(self, method):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else None
        hdr = {k: v for k, v in self.headers.items() if k.lower() not in ("host", "content-length", "origin")}
        hdr["Host"] = "localhost:5173"
        if method != "GET": hdr["Origin"] = "http://localhost:5173"
        r = requests.request(method, "http://127.0.0.1:5000" + self.path, data=body, headers=hdr, allow_redirects=False)
        self.send_response(r.status_code)
        for k, v in r.headers.items():
            if k.lower() not in ("transfer-encoding", "connection", "content-encoding", "content-length"):
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(r.content)))
        self.end_headers(); self.wfile.write(r.content)
    def do_GET(self):
        if self.path.startswith("/api/"): return self._proxy("GET")
        if not os.path.exists(ROOT + self.path.split("?")[0]) or self.path == "/": self.path = "/index.html"
        return super().do_GET()
    def do_POST(self): self._proxy("POST")
    def do_PATCH(self): self._proxy("PATCH")
    def do_PUT(self): self._proxy("PUT")
    def do_DELETE(self): self._proxy("DELETE")
socketserver.ThreadingTCPServer.allow_reuse_address = True
socketserver.ThreadingTCPServer(("127.0.0.1", 5173), H).serve_forever()
