"""
Jalankan semuanya dengan satu perintah:   python run.py

  - Mock API (ESB tiruan)  -> http://localhost:8001
  - Aplikasi chat          -> http://localhost:8000   (buka ini di browser)

Pengaturan lewat environment variable (semuanya opsional):
  APP_PORT, MOCK_PORT  port aplikasi dan mock API
  BIND_HOST            alamat yang didengarkan. Bawaan 127.0.0.1 (hanya komputer ini).
                       Di Docker diisi 0.0.0.0 supaya port bisa dipublikasikan ke host;
                       pembatasan akses ke host ada di docker-compose.yml.
"""
import os

import mock_api
import server

MOCK_PORT = int(os.environ.get("MOCK_PORT", "8001"))
APP_PORT = int(os.environ.get("APP_PORT", "8000"))
BIND_HOST = os.environ.get("BIND_HOST", "127.0.0.1")

if __name__ == "__main__":
    mock_api.start(MOCK_PORT, BIND_HOST)
    print("Mock API  : http://localhost:%d" % MOCK_PORT)
    print("Aplikasi  : http://localhost:%d   <- buka di browser (Ctrl+C untuk berhenti)" % APP_PORT)
    try:
        # Agen selalu memanggil mock API di proses yang sama, jadi alamatnya tetap 127.0.0.1.
        server.serve(APP_PORT, "http://127.0.0.1:%d" % MOCK_PORT, host=BIND_HOST)
    except KeyboardInterrupt:
        print("\nBerhenti.")
