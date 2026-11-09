import http.server
import importlib.util
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def load_script(relative_path: str, name: str):
    path = ROOT / relative_path
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RecordingServer:
    def __init__(self, respond):
        self.requests = []
        recorder = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def _handle(self):
                recorder.requests.append(
                    {"path": self.path, "authorization": self.headers.get("Authorization")}
                )
                status, headers, body = respond(self.path)
                self.send_response(status)
                for key, value in headers.items():
                    self.send_header(key, value)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            do_GET = _handle
            do_POST = _handle

            def log_message(self, *args):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def redirect_pair():
    target = RecordingServer(lambda path: (200, {"Content-Type": "application/json"}, b"{}"))
    origin = RecordingServer(
        lambda path: (302, {"Location": f"{target.url}{path}"}, b"")
    )
    yield origin, target
    origin.close()
    target.close()
