import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        record = {
            "path": self.path,
            "payload": json.loads(body.decode("utf-8")),
            "user_agent": self.headers.get("User-Agent", ""),
        }
        with open(__file__.replace("mock_server.py", "mock_hits.json"), "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        resp = json.dumps({"code": 0, "msg": "ok"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)

    def log_message(self, *args):
        pass


HTTPServer(("127.0.0.1", 59955), Handler).serve_forever()
