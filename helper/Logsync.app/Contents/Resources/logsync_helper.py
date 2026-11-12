#!/usr/bin/env python3
"""
Logsync – lokal hjälptjänst.

Startas av menyradsappen och lyssnar på 127.0.0.1:47811. Logsync i webbläsaren
pratar med den för det en webbsida inte kan göra själv:
  - transkribera kamerafiler (välja fil, starta, följa förloppet, hämta resultatet)
  - hämta branding (logotyp, färger, typsnitt) från en webbplats

Lyssnar bara på den egna datorn och svarar bara de sidor som står i ALLOWED_ORIGINS.
"""
import json, os, re, subprocess, sys, threading, time, traceback, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import transkribera as T
import branding as B

VERSION = "2"
PORT = int(os.environ.get("LOGSYNC_PORT", "47811"))
# Sidor som får prata med tjänsten. Lägg till din egen adress här om du kör Logsync från en annan plats.
ALLOWED_ORIGINS = ["https://philipatspoon.github.io"]
# Dessutom: sidor på den egna datorn (localhost) och lokala filer (file:// skickar ursprunget "null").
ALLOWED = re.compile(r"^(%s|http://(localhost|127\.0\.0\.1)(:\d+)?|null)$" % "|".join(map(re.escape, ALLOWED_ORIGINS)), re.I)

JOB = {"id": None, "state": "idle"}
ON_QUIT = None  # sätts av menyradsappen
SUPPORT = Path.home() / "Library/Application Support/Logsync"
PAGE_FILE = SUPPORT / "app_url.txt"  # Logsyncs adress i webbläsaren, lärs in när sidan ansluter


def remember_page(url):
    if url and ALLOWED.match(re.sub(r"^(https?://[^/]+).*$", r"\1", url)):
        try:
            SUPPORT.mkdir(parents=True, exist_ok=True)
            if not PAGE_FILE.exists() or PAGE_FILE.read_text() != url:
                PAGE_FILE.write_text(url)
        except OSError:
            pass


LOCK = threading.Lock()  # en transkribering åt gången


# ---------- Whisper-förlopp: koppla in i mlx_whispers tqdm ----------
_cur = {"done": 0, "total": 0}


def _patch_tqdm():
    try:
        import mlx_whisper  # noqa: F401  (mlx_whisper.transcribe är funktionen – hämta modulen ur sys.modules)
        mt = sys.modules["mlx_whisper.transcribe"]

        class Bar:
            def __init__(self, total=0, **k):
                _cur["total"], _cur["done"] = total or 0, 0
            def update(self, n=1):
                _cur["done"] += n
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
            def close(self):
                pass

        class Shim:
            tqdm = Bar
        mt.tqdm = Shim
    except Exception:
        pass  # utan detaljerat förlopp – fungerar ändå


# ---------- macOS-dialog ----------
def pick_files():
    script = '''
tell application "System Events"
  activate
  set fs to choose file with prompt "Välj kamerafil(er) (MXF, MOV eller MP4)" with multiple selections allowed
end tell
set out to ""
repeat with f in fs
  set out to out & POSIX path of f & linefeed
end repeat
return out'''
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if r.returncode != 0:
        return []  # avbrutet
    return [p for p in r.stdout.splitlines() if p.strip()]


def describe(paths):
    T.ensure_ffmpeg()
    out = []
    for p in paths:
        i = T.probe(Path(p))
        out.append({"path": p, "name": Path(p).name, "start_tc": i["start_tc"], "fps": i["fps"],
                    "duration": i["duration"], "channels": len(i["channels"]), "video": i["video"]})
    return out


# ---------- körning ----------
def run_job(jid, paths, names, lang, base):
    t0 = time.time()

    def progress(stage, msg, pct=None):
        JOB.update(stage=stage, msg=msg)
        if pct:
            JOB["part"] = pct  # (index, antal) för kanaler

    try:
        _patch_tqdm()
        files = [Path(p) for p in paths]
        nfiles = len(files)
        JOB.update(state="running", msg="Startar …", started=t0)
        # förlopp: (fil, kanal) × whisper-andel
        def ticker():
            while JOB.get("id") == jid and JOB["state"] == "running":
                part = JOB.get("part") or (0, 1)
                w = (_cur["done"] / _cur["total"]) if _cur["total"] else 0
                fi = JOB.get("file_i", 0)
                JOB["pct"] = round(100 * (fi + (part[0] + min(w, 1)) / part[1]) / nfiles, 1)
                JOB["elapsed"] = round(time.time() - t0)
                time.sleep(0.5)
        threading.Thread(target=ticker, daemon=True).start()
        res = None
        if nfiles == 1:
            res = T.run(files, names, lang, base=base, progress=progress)
        else:
            # flera filer: kör alla i ett svep men räkna fram filindex för förloppet
            orig = T.process
            def proc(path, *a, **k):
                JOB["file_i"] = files.index(path)
                return orig(path, *a, **k)
            T.process = proc
            try:
                res = T.run(files, names, lang, base=base, progress=progress)
            finally:
                T.process = orig
        res.pop("words", None)  # appen behöver replikerna; orden ligger i JSON-filen
        JOB.update(state="done", pct=100, msg="Klart", result=res, elapsed=round(time.time() - t0))
    except Exception as e:
        JOB.update(state="error", msg=str(e), trace=traceback.format_exc())


# ---------- HTTP ----------
class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _origin_ok(self):
        o = self.headers.get("Origin")
        return o is None or bool(ALLOWED.match(o))

    def _cors(self):
        o = self.headers.get("Origin")
        if o and ALLOWED.match(o):
            self.send_header("Access-Control-Allow-Origin", o)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Logsync, X-Logsync-Page")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Private-Network", "true")

    def _send(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _guard(self):
        # Kräver egen header (tvingar fram CORS-preflight) och tillåtet ursprung
        if not self._origin_ok() or self.headers.get("X-Logsync") != "1":
            self._send(403, {"error": "forbidden"})
            return False
        remember_page(self.headers.get("X-Logsync-Page"))
        return True

    def do_OPTIONS(self):
        self.send_response(204 if self._origin_ok() else 403)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if not self._guard():
            return
        if self.path == "/status":
            return self._send(200, {"ok": True, "version": VERSION, "state": JOB["state"]})
        if self.path == "/job":
            j = {k: v for k, v in JOB.items() if k != "trace"}
            return self._send(200, j)
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._guard():
            return
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._send(400, {"error": "bad json"})
        if self.path == "/quit":
            if JOB["state"] == "running":
                return self._send(409, {"error": "En transkribering pågår"})
            self._send(200, {"ok": True})
            if ON_QUIT:
                threading.Timer(0.3, ON_QUIT).start()
            return
        if self.path == "/brand":  # hämta branding från en webbplats
            try:
                return self._send(200, B.fetch_brand(body.get("url"), want_fonts=body.get("fonts", True)))
            except B.BrandError as e:
                return self._send(422, {"error": str(e)})
            except Exception as e:
                return self._send(500, {"error": f"Kunde inte läsa sidan ({e})"})
        if self.path == "/pick":
            paths = pick_files()
            try:
                return self._send(200, {"files": describe(paths)})
            except Exception as e:
                return self._send(500, {"error": str(e)})
        if self.path == "/describe":  # sökväg inklistrad i appen
            paths = [p for p in body.get("paths", []) if Path(p).is_file()]
            try:
                return self._send(200, {"files": describe(paths)})
            except Exception as e:
                return self._send(500, {"error": str(e)})
        if self.path == "/transcribe":
            with LOCK:
                if JOB["state"] == "running":
                    return self._send(409, {"error": "En transkribering pågår redan"})
                paths = [p for p in body.get("paths", []) if Path(p).is_file()]
                if not paths:
                    return self._send(400, {"error": "Inga filer"})
                names = {int(k): v for k, v in (body.get("names") or {"1": "Värd", "2": "Gäst"}).items()}
                jid = uuid.uuid4().hex[:8]
                JOB.clear()
                JOB.update(id=jid, state="running", pct=0, msg="Startar …", file_i=0)
                threading.Thread(target=run_job, args=(jid, paths, names, body.get("lang", "en"), body.get("base")),
                                 daemon=True).start()
                return self._send(200, {"id": jid})
        self._send(404, {"error": "not found"})


def serve():
    """Starta servern i en bakgrundstråd. Returnerar servern (shutdown() stänger)."""
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


if __name__ == "__main__":
    print(f"Logsync-tjänsten lyssnar på http://127.0.0.1:{PORT}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
