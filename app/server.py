from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .config import Config
from .message_service import MessageService


class HouseholdRequestHandler(BaseHTTPRequestHandler):
    service: MessageService

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", "0") or "0")
        raw_body = self.rfile.read(content_length) if content_length else b"{}"
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            payload = {}

        if parsed.path == "/send":
            status, body = self.service.handle_send(self.headers.get("X-Internal-Token", ""), payload)
        elif parsed.path in {"", "/", "/webhook"}:
            token = parse_qs(parsed.query).get("token", [""])[0]
            status, body = self.service.handle_webhook(token, payload)
        else:
            status, body = 404, {"status": "error", "reason": "not_found"}

        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def serve(config: Config, message_service: MessageService, host: str = "127.0.0.1", port: int = 5005) -> None:
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    HouseholdRequestHandler.service = message_service
    with ThreadingHTTPServer((host, port), HouseholdRequestHandler) as server:
        print(f"Household listener running on http://{host}:{port}")
        server.serve_forever()

