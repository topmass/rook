"""A stand-in for the plugin backend's overlay server, for trying overlay/page and the overlay process off the Deck.

    uv run --no-project overlay/dev/fake_server.py [--port 47331]

Serves overlay/page at /overlay (index.html) and /overlay/<file>, and /overlay/events as SSE: one JSON message per
change, {"state", "text", "draft"}, as the backend sends. /overlay/events cycles through Rook's states with a
streaming answer; /overlay/events?scene=listening|thinking|speaking|answer|waiting|resting holds one scene (for
screenshots).
"""

import argparse
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "page")
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css",
         ".json": "application/json", ".txt": "text/plain; charset=utf-8"}

ANSWER = ("The quest wants six Gnarlpine necklaces. They drop from the furbolgs in the Ban'ethil Barrow Den, south "
          "of Dolanaar. Most carry one; the shamans on the lower floor carry two.\n\nYour bags have room for all six, "
          "and the den is level ten, so you can clear it alone.")
DRAFT = "omw, 2 min — grabbing the necklaces first"
SCENES = {
    "resting": [{"state": "resting", "text": "", "draft": None}],
    "listening": [{"state": "listening", "text": "", "draft": None}],
    "thinking": [{"state": "thinking", "text": "", "draft": None}],
    "speaking": [{"state": "speaking", "text": ANSWER[:190], "draft": None}],
    "answer": [{"state": "speaking", "text": ANSWER, "draft": None}],
    "waiting": [{"state": "waiting", "text": "Mira whispers: “are you coming to the den?” Shall I answer:",
                 "draft": DRAFT}],
}


def cycle():
    """(delay, message) pairs, forever."""
    while True:
        yield 2.0, {"state": "resting", "text": "", "draft": None}
        yield 2.5, {"state": "listening", "text": "", "draft": None}
        yield 2.5, {"state": "thinking", "text": "", "draft": None}
        words = ANSWER.split(" ")
        for i in range(1, len(words) + 1, 3):
            yield 0.25, {"state": "speaking", "text": " ".join(words[:i]), "draft": None}
        yield 1.5, {"state": "speaking", "text": ANSWER, "draft": None}
        yield 7.0, {"state": "resting", "text": ANSWER, "draft": None}
        yield 5.0, SCENES["waiting"][0]
        yield 8.0, {"state": "resting", "text": "", "draft": None}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/overlay/events":
            return self.events(parse_qs(url.query).get("scene", [None])[0])
        name = "index.html" if url.path in ("/overlay", "/overlay/") else url.path.removeprefix("/overlay/")
        path = os.path.normpath(os.path.join(PAGE, name))
        if not url.path.startswith("/overlay") or not path.startswith(os.path.normpath(PAGE)) or not os.path.isfile(path):
            self.send_error(404)
            return
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", TYPES.get(os.path.splitext(path)[1], "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send(self, msg):
        self.wfile.write(f"data: {json.dumps(msg)}\n\n".encode())
        self.wfile.flush()

    def events(self, scene):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            if scene in SCENES:
                for msg in SCENES[scene]:
                    self.send(msg)
                while True:
                    time.sleep(15)
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
            for delay, msg in cycle():
                self.send(msg)
                time.sleep(delay)
        except (BrokenPipeError, ConnectionResetError):
            pass


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=47331)
    p.add_argument("--host", default="127.0.0.1")
    a = p.parse_args()
    server = ThreadingHTTPServer((a.host, a.port), Handler)
    server.daemon_threads = True
    print(f"fake overlay server on http://{a.host}:{a.port}/overlay", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
