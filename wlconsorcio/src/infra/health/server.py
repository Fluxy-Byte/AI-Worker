import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


class _Handler(BaseHTTPRequestHandler):
    def _write_json(self, status: int, body: dict) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._write_json(200, {"status": "ok", "service": "ai-worker-generic"})
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/rag/ingest":
            self.send_response(404)
            self.end_headers()
            return

        if self.headers.get("x-internal-api-key") != os.getenv("INTERNAL_API_KEY"):
            self._write_json(401, {"success": False, "result": None, "message": "Chave interna inválida."})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            self._write_json(422, {"success": False, "result": None, "message": "Corpo inválido."})
            return

        required = ("ragDocumentId", "agentId", "organizationId", "s3Key", "fileName", "chunkSize")
        if any(field not in payload for field in required):
            self._write_json(422, {"success": False, "result": None, "message": "Campos obrigatórios ausentes."})
            return

        # Dispara em background e responde na hora — a extração/chunking/
        # embedding pode demorar, o chamador (Agent-Api) não espera.
        from src.services.rag_ingestion.ingest import run_ingestion

        threading.Thread(target=run_ingestion, args=(payload,), daemon=True).start()
        self._write_json(202, {"success": True, "result": {"ragDocumentId": payload["ragDocumentId"]}, "message": "Ingestão iniciada."})

    def log_message(self, format: str, *args) -> None:
        pass


def start_health_server(port: int) -> None:
    server = HTTPServer(("0.0.0.0", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"HTTP (health + /rag/ingest) em http://0.0.0.0:{port}")
