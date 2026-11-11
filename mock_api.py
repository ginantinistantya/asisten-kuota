"""
MOCK ESB/API - tiruan 7 endpoint dari kontrak API case study.

   GET  /subscriber/{msisdn}/profile   profil, segmen, consent  (berisi PII)
   GET  /subscriber/{msisdn}/quota     sisa kuota & status FUP  (respons 200-800 ms)
   GET  /offers?msisdn=                daftar paket eligible (BID)
   POST /purchase                      beli paket (WAJIB header Idempotency-Key, bisa timeout)
   POST /loan/eligibility              cek Paket Darurat (limit & biaya)
   GET  /network/status?cell=          status jaringan di sel ("normal" / "degraded")
   POST /ticket                        buat tiket gangguan (mengembalikan nomor tiket)

Tambahan di luar kontrak (khusus demo): POST /admin/reset untuk mengembalikan data dummy.

PENTING: bentuk JSON request/response di bawah adalah SKEMA USULAN untuk prototipe,
bukan spesifikasi API Telkomsel yang asli (kontrak hanya memberi method, path, fungsi, catatan).

Hanya memakai pustaka bawaan Python. Bawaannya hanya mendengarkan 127.0.0.1
(di Docker, run.py mengubahnya lewat BIND_HOST, lihat docker-compose.yml).
"""
import copy
import json
import random
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import dummy_data

# Pengaturan simulasi. Test otomatis mengecilkan angka ini supaya cepat.
CONFIG = {
    "quota_latency": (0.2, 0.8),    # detik; sesuai catatan kontrak: respons quota 200-800 ms
    "slow_purchase_seconds": 6.0,   # lama "respons terlambat" untuk purchase_mode = timeout_once
}


class State:
    """Isi 'database' tiruan: semua ada di memori, hilang saat server dimatikan."""

    def __init__(self):
        self.customers = copy.deepcopy(dummy_data.CUSTOMERS)
        self.purchases = {}      # Idempotency-Key -> {"fingerprint": ..., "response": ...}
        self.tickets = []        # daftar tiket yang dibuat
        self.calls = []          # catatan setiap request (dipakai test)
        self.lock = threading.Lock()   # supaya dua request bersamaan tidak saling menimpa


STATE = State()


class ApiError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def customer_or_404(msisdn):
    customer = STATE.customers.get(msisdn)
    if customer is None:
        raise ApiError(404, "SUBSCRIBER_NOT_FOUND", "Nomor tidak ditemukan")
    return customer


# ---------------------------------------------------------------- 7 endpoint

def get_profile(msisdn, query, body, headers):
    c = customer_or_404(msisdn)
    return 200, {
        "msisdn": msisdn, "name": c["name"], "email": c["email"],   # <- PII, wajib di-mask di log
        "segment": c["segment"],
        "consent": {"granted": c["consent"], "purpose": "Asisten Kuota"},
        "balance_idr": c["balance_idr"],   # USULAN: kontrak tidak menyebut sumber saldo pulsa
    }


def get_quota(msisdn, query, body, headers):
    c = customer_or_404(msisdn)
    low, high = CONFIG["quota_latency"]
    time.sleep(random.uniform(low, high))   # simulasi 200-800 ms
    return 200, {"msisdn": msisdn, "remaining_mb": c["quota_mb"],
                 "total_mb": c["total_mb"], "fup_active": c["fup_active"]}


def get_offers(msisdn, query, body, headers):
    c = customer_or_404(query.get("msisdn", ""))
    offers = [dict(bid=bid, **dummy_data.OFFERS[bid]) for bid in c["eligible_bids"]]
    return 200, {"msisdn": query["msisdn"], "offers": offers}


def post_purchase(msisdn, query, body, headers):
    key = headers.get("Idempotency-Key")
    if not key:
        raise ApiError(400, "IDEMPOTENCY_KEY_REQUIRED", "Header Idempotency-Key wajib ada")
    fingerprint = json.dumps(body, sort_keys=True)

    with STATE.lock:
        old = STATE.purchases.get(key)
        if old:
            # Key yang sama = permintaan yang sama. Jangan proses lagi, kembalikan hasil lama.
            if old["fingerprint"] != fingerprint:
                raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "Key sama dipakai untuk permintaan berbeda")
            return 200, dict(old["response"], replayed=True)

        customer = customer_or_404(body.get("msisdn", ""))
        if customer["purchase_mode"] == "always_fail":
            raise ApiError(503, "SERVICE_UNAVAILABLE", "Layanan pembelian sedang gangguan")
        response = process_purchase(customer, body)
        STATE.purchases[key] = {"fingerprint": fingerprint, "response": response}
        mode = customer["purchase_mode"]

    # Transaksi SUDAH diproses di atas. Di sini kita pura-pura respons tidak sampai tepat waktu.
    if mode == "timeout_once":
        time.sleep(CONFIG["slow_purchase_seconds"])
    return 200, response


def process_purchase(customer, body):
    """Validasi di sisi backend lalu eksekusi. Dipanggil di dalam lock."""
    bid, method = body.get("bid"), body.get("payment_method")
    if not customer["consent"]:
        raise ApiError(403, "CONSENT_REQUIRED", "Pelanggan belum memberi consent")
    if bid not in customer["eligible_bids"]:
        raise ApiError(422, "PACKAGE_NOT_ELIGIBLE", "Paket tidak eligible untuk pelanggan ini")
    offer = dummy_data.OFFERS[bid]
    price = offer["price_idr"]

    result = {}
    if method == "balance":
        if customer["balance_idr"] < price:
            raise ApiError(402, "INSUFFICIENT_BALANCE", "Pulsa tidak cukup")
        customer["balance_idr"] -= price
    elif method == "emergency":
        loan = customer["loan"]
        if not loan["eligible"] or price > loan["limit_idr"]:
            raise ApiError(422, "EMERGENCY_NOT_ELIGIBLE", "Tidak memenuhi syarat Paket Darurat")
        result["loan_outstanding_idr"] = price + loan["fee_idr"]   # dibayar dari top-up berikutnya
        loan["eligible"] = False                                   # satu kali pakai
    else:
        raise ApiError(400, "INVALID_PAYMENT_METHOD", "payment_method harus 'balance' atau 'emergency'")

    customer["quota_mb"] += offer["quota_mb"]
    customer["total_mb"] += offer["quota_mb"]
    result.update({
        "transaction_id": "TRX-%06d" % (len(STATE.purchases) + 1),
        "status": "success", "msisdn": body["msisdn"], "bid": bid, "name": offer["name"],
        "price_idr": price, "payment_method": method, "balance_idr": customer["balance_idr"],
        "quota_mb_added": offer["quota_mb"], "validity_days": offer["validity_days"],
    })
    return result


def post_loan_eligibility(msisdn, query, body, headers):
    c = customer_or_404(body.get("msisdn", ""))
    loan = c["loan"]
    result = {"msisdn": body["msisdn"], "eligible": loan["eligible"],
              "limit_idr": loan["limit_idr"], "fee_idr": loan["fee_idr"]}
    if not loan["eligible"]:
        result["reason"] = "NOT_ELIGIBLE"
    return 200, result


def get_network_status(msisdn, query, body, headers):
    cell = dummy_data.CELLS.get(query.get("cell", ""))
    if cell is None:
        raise ApiError(404, "CELL_NOT_FOUND", "Sel tidak ditemukan")
    return 200, {"cell": query["cell"], "status": cell["status"], "detail": cell["detail"]}


def post_ticket(msisdn, query, body, headers):
    customer_or_404(body.get("msisdn", ""))
    with STATE.lock:
        # Sudah ada tiket terbuka untuk nomor + sel yang sama? Kembalikan yang lama (cegah tiket ganda).
        for t in STATE.tickets:
            if t["msisdn"] == body["msisdn"] and t["cell"] == body.get("cell"):
                return 200, dict(t, existing=True)
        ticket = {"ticket_id": "TKT-%06d" % (len(STATE.tickets) + 1), "status": "open",
                  "msisdn": body["msisdn"], "cell": body.get("cell"),
                  "category": body.get("category"), "summary": body.get("summary")}
        STATE.tickets.append(ticket)
    return 201, dict(ticket, existing=False)


def admin_reset(msisdn, query, body, headers):
    global STATE
    STATE = State()
    return 200, {"status": "reset"}


# ---------------------------------------------------------------- routing & server

ROUTES = [
    ("GET",  r"^/subscriber/(\d+)/profile$", get_profile),
    ("GET",  r"^/subscriber/(\d+)/quota$",   get_quota),
    ("GET",  r"^/offers$",                   get_offers),
    ("POST", r"^/purchase$",                 post_purchase),
    ("POST", r"^/loan/eligibility$",         post_loan_eligibility),
    ("GET",  r"^/network/status$",           get_network_status),
    ("POST", r"^/ticket$",                   post_ticket),
    ("POST", r"^/admin/reset$",              admin_reset),
]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):   # matikan log bawaan agar terminal bersih
        pass

    def handle_request(self, method):
        url = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        STATE.calls.append((method, self.path))
        try:
            body = json.loads(raw) if raw else {}
            if not isinstance(body, dict):
                raise ValueError("body harus objek JSON")
            for route_method, pattern, function in ROUTES:
                match = re.match(pattern, url.path)
                if route_method == method and match:
                    arg = match.group(1) if match.groups() else None
                    status, data = function(arg, query, body, self.headers)
                    break
            else:
                raise ApiError(404, "NOT_FOUND", "Endpoint tidak ada")
        except ApiError as e:
            status, data = e.status, {"error": {"code": e.code, "message": e.message}}
        except ValueError:
            status, data = 400, {"error": {"code": "INVALID_JSON", "message": "Body bukan JSON"}}
        self.send_json(status, data)

    def send_json(self, status, data):
        payload = json.dumps(data).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass   # klien sudah menyerah (timeout); transaksi tetap sudah tercatat di server

    def do_GET(self):
        self.handle_request("GET")

    def do_POST(self):
        self.handle_request("POST")


def start(port=8001, host="127.0.0.1"):
    """Jalankan mock API di thread latar belakang. port=0 berarti pilih port bebas."""
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


if __name__ == "__main__":
    srv = start(8001)
    print("Mock API jalan di http://127.0.0.1:%d  (Ctrl+C untuk berhenti)" % srv.server_address[1])
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
