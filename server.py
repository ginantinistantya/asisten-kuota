"""
SERVER WEB - menyajikan halaman chat dan JSON API untuk chat.

File ini juga berperan sebagai SIMULASI APLIKASI MyTelkomsel: aplikasi asli tahu siapa yang
sedang login (msisdn) dan sel (cell) perangkatnya. Di demo, informasi itu diambil dari daftar
pelanggan dummy supaya bisa dipilih lewat dropdown. Itu sebabnya file ini (dan hanya file ini,
selain mock_api.py) mengimpor dummy_data. Agen sendiri tidak pernah menyentuh dummy_data.

Endpoint (khusus UI prototipe, BUKAN bagian kontrak API):
  GET  /                      halaman chat
  GET  /api/customers         daftar pelanggan dummy untuk dropdown
  POST /api/chat              kirim pesan atau ketukan tombol, terima balasan agen
  GET  /api/trace?conversation_id=...   log/trace langkah agen (sudah di-mask)
  POST /api/reset             kembalikan data mock ke kondisi awal
"""
import json
import os
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import dummy_data
from agent import Agent
from tools import Gateway
from tracelog import Trace

HERE = os.path.dirname(os.path.abspath(__file__))
MAX_BODY_BYTES = 10_000

# Diisi oleh serve()
AGENT = None
TRACE = None
MOCK_URL = None
CONVERSATIONS = {}
LOCK = threading.Lock()    # satu pesan diproses satu per satu (cukup untuk demo satu pengguna)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    # ---------------------------------------------------------------- helper
    def send_bytes(self, status, content_type, payload):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def send_json(self, status, data):
        self.send_bytes(status, "application/json", json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY_BYTES:
            return None
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return None
        return data if isinstance(data, dict) else None

    # ---------------------------------------------------------------- routes
    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/":
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                self.send_bytes(200, "text/html; charset=utf-8", f.read())
        elif url.path == "/api/customers":
            self.send_json(200, [{"msisdn": m, "scenario": c["scenario"], "cell": c["cell"]}
                                 for m, c in dummy_data.CUSTOMERS.items()])
        elif url.path == "/api/trace":
            conv_id = parse_qs(url.query).get("conversation_id", [""])[0]
            self.send_json(200, TRACE.get(conv_id))
        else:
            self.send_json(404, {"error": "tidak ditemukan"})

    def do_POST(self):
        url = urlparse(self.path)
        body = self.read_json()
        if body is None:
            return self.send_json(400, {"error": "body bukan JSON yang valid / terlalu besar"})
        if url.path == "/api/chat":
            self.chat(body)
        elif url.path == "/api/reset":
            self.reset()
        else:
            self.send_json(404, {"error": "tidak ditemukan"})

    def chat(self, body):
        conv_id = body.get("conversation_id")
        text, action = body.get("text"), body.get("action")
        if not isinstance(text, (str, type(None))) or not isinstance(action, (dict, type(None))):
            return self.send_json(400, {"error": "text harus string, action harus objek"})
        if not text and not action:
            return self.send_json(400, {"error": "isi text atau action"})

        with LOCK:
            conv = CONVERSATIONS.get(conv_id)
            if conv is None:                      # percakapan baru: pelanggan "login" sebagai msisdn ini
                customer = dummy_data.CUSTOMERS.get(body.get("msisdn"))
                if customer is None:
                    return self.send_json(400, {"error": "msisdn tidak dikenal (hanya pelanggan dummy)"})
                conv = AGENT.new_conversation(body["msisdn"], customer["cell"])
                CONVERSATIONS[conv.id] = conv
            replies = AGENT.handle(conv, text=text, action=action)

        handoff = AGENT.handoffs[-1] if conv.handed_off and AGENT.handoffs else None
        self.send_json(200, {"conversation_id": conv.id, "replies": replies, "handoff": handoff})

    def reset(self):
        request = urllib.request.Request(MOCK_URL + "/admin/reset", data=b"{}", method="POST",
                                         headers={"Content-Type": "application/json"})
        urllib.request.urlopen(request, timeout=3).read()
        with LOCK:
            CONVERSATIONS.clear()
        self.send_json(200, {"status": "reset"})


def make_server(port, mock_url, log_path=None, host="127.0.0.1"):
    """Siapkan agen dan server (belum berjalan). port=0 berarti pilih port bebas."""
    global AGENT, TRACE, MOCK_URL
    TRACE = Trace(log_path or os.path.join(HERE, "logs", "trace.jsonl"))
    AGENT = Agent(Gateway(mock_url, TRACE), TRACE)
    MOCK_URL = mock_url
    CONVERSATIONS.clear()
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server


def serve(port, mock_url, log_path=None, host="127.0.0.1"):
    """Jalankan server (blocking)."""
    make_server(port, mock_url, log_path, host).serve_forever()
