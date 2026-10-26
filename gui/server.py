"""islandGen GUI. Run:  python gui/server.py   then it opens your browser.

Python stays the source of truth: the page only draws what the generator returns.
Stdlib only.
"""
import json
import os
import sys
import webbrowser
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from islandgen import meta  # noqa: E402
from islandgen.export import write_meta, face_materials  # noqa: E402

PORT = int(os.environ.get("ISLANDGEN_PORT", 8765))


def payload(res):
    """Indexed mesh; the page splits it into flat-shaded triangles."""
    return {
        "verts": [round(x, 2) for x in res["verts"].ravel().tolist()],
        "faces": res["faces"].ravel().tolist(),
        "mat": face_materials(res).tolist(),
        "stats": res["stats"],
        "player_at": [res["balls"][0]["x"], res["balls"][0]["h"], res["balls"][0]["z"]] if res["balls"] else [0, 0, 0],
        "player_height": res["settings"]["player_height"],
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=os.path.join(ROOT, "gui"), **kw)

    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/params":
            return self._json(meta.PARAMS)
        if self.path == "/used":
            return self._json(meta.USED_BY)
        return super().do_GET()

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        req = json.loads(self.rfile.read(n) or b"{}")
        seed = int(req.get("seed", 1))
        settings = req.get("settings", {})
        try:
            res = meta.generate(seed, settings)
            if self.path == "/generate":
                return self._json(payload(res))
            if self.path == "/export":
                target = req.get("target", "unity")
                folder = write_meta(res, os.path.join(ROOT, "out", f"meta_{seed}_{target}"), target)
                return self._json({"folder": os.path.relpath(folder, ROOT)})
            self._json({"error": "unknown route"}, 404)
        except Exception as e:  # show errors in the page instead of dying
            self._json({"error": str(e)}, 500)


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://127.0.0.1:{PORT}/"
    print(f"islandGen GUI at {url}  (Ctrl+C to stop)")
    if "--no-browser" not in sys.argv:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
