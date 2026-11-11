"""
TOOL GATEWAY - satu-satunya pintu agen ke API (ESB).

Yang dijaga di sini:
  1. Allowlist: hanya 7 tool di TOOLS yang bisa dipanggil. Tidak ada tool lain.
  2. Nomor pelanggan (msisdn) SELALU dari sesi login, bukan dari teks yang diketik pelanggan.
  3. POST /purchase WAJIB membawa Idempotency-Key (tanpa key -> ditolak sebelum dikirim).
  4. Timeout + retry. Retry hanya untuk error sementara (timeout, koneksi putus, 5xx),
     tidak untuk 4xx. Retry purchase memakai key yang SAMA, jadi tidak mungkin beli dua kali.
  5. Setiap percobaan dicatat ke trace (data pribadi di-mask).

Angka timeout/retry adalah USULAN prototipe (bisa diubah di bawah, test mengecilkannya).
"""
import json
import time
import urllib.error
import urllib.request

# nama tool -> (method, path). {msisdn} dan {cell} diisi oleh gateway.
TOOLS = {
    "get_profile":   ("GET",  "/subscriber/{msisdn}/profile"),
    "get_quota":     ("GET",  "/subscriber/{msisdn}/quota"),
    "get_offers":    ("GET",  "/offers?msisdn={msisdn}"),
    "purchase":      ("POST", "/purchase"),
    "check_loan":    ("POST", "/loan/eligibility"),
    "get_network":   ("GET",  "/network/status?cell={cell}"),
    "create_ticket": ("POST", "/ticket"),
}

TIMEOUT_DEFAULT = 2.0      # detik, untuk semua tool selain purchase
TIMEOUT_PURCHASE = 5.0     # detik
RETRIES = {"purchase": 2, "create_ticket": 0}   # selain ini: 1 kali retry
QUOTA_SLA_SECONDS = 0.8    # kontrak: respons quota 200-800 ms


class Gateway:
    def __init__(self, base_url, tracelog):
        self.base_url = base_url
        self.trace = tracelog

    def call(self, conv, tool, body=None, idempotency_key=None):
        """
        Panggil satu tool. Mengembalikan dict:
          {"ok": True/False, "status": kode HTTP atau None, "data": isi JSON, "attempts": jumlah percobaan}
        """
        if tool not in TOOLS:
            raise ValueError("Tool tidak ada di allowlist: %s" % tool)
        method, path = TOOLS[tool]
        path = path.format(msisdn=conv.msisdn, cell=conv.cell)   # identitas dari sesi, bukan dari chat

        headers = {"Content-Type": "application/json"}
        if tool == "purchase":
            if not idempotency_key:
                raise ValueError("purchase wajib memakai idempotency_key")
            headers["Idempotency-Key"] = idempotency_key
        timeout = TIMEOUT_PURCHASE if tool == "purchase" else TIMEOUT_DEFAULT
        max_attempts = 1 + RETRIES.get(tool, 1)

        result = {"ok": False, "status": None, "data": None, "attempts": 0}
        for attempt in range(1, max_attempts + 1):
            result["attempts"] = attempt
            started = time.perf_counter()
            status, data, error = self._send(method, path, body, headers, timeout)
            seconds = time.perf_counter() - started
            result.update(status=status, data=data)

            note = error or ("HTTP %s" % status)
            if tool == "get_quota" and seconds > QUOTA_SLA_SECONDS:
                note += " (melebihi 800 ms)"
            self.trace.log(conv.id, "tool", "api_call", tool=tool, method=method, path=path,
                           attempt="%d/%d" % (attempt, max_attempts), result=note,
                           ms=int(seconds * 1000), request=body, response=data,
                           idempotency_key=idempotency_key)

            if status is not None and status < 500:     # sukses, atau 4xx: jangan di-retry
                result["ok"] = 200 <= status < 300
                return result
            # selain itu (timeout / koneksi putus / 5xx): coba lagi kalau masih ada jatah

        return result

    def _send(self, method, path, body, headers, timeout):
        """Kirim satu request. Mengembalikan (status, data, error_text)."""
        payload = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(self.base_url + path, data=payload, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status, json.loads(response.read()), None
        except urllib.error.HTTPError as e:                # server menjawab dengan 4xx / 5xx
            try:
                return e.code, json.loads(e.read()), None
            except ValueError:
                return e.code, None, None
        except Exception as e:                             # timeout, koneksi ditolak, dll.
            return None, None, "%s" % type(e).__name__
