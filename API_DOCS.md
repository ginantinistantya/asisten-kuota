# Dokumentasi API - Prototipe Asisten Kuota

Ada dua lapis API:

1. **Mock ESB/API** (`mock_api.py`, port 8001): 7 endpoint dari kontrak case study.
2. **API aplikasi chat** (`server.py`, port 8000): dipakai `index.html`. Bukan bagian kontrak.

> **Penting.** Dari kontrak case study hanya **method, path, fungsi, dan catatan** yang resmi (tabel di bawah).
> Semua bentuk JSON request/response di dokumen ini adalah **skema usulan untuk prototipe**,
> bukan spesifikasi API Telkomsel yang asli. Contoh JSON di bawah adalah keluaran asli dari mock yang berjalan.

## 1. Kontrak (sumber: case study)

| Method | Endpoint | Fungsi | Catatan kontrak |
|---|---|---|---|
| GET | `/subscriber/{msisdn}/profile` | Profil, segmen, consent | Berisi PII, wajib masking di log |
| GET | `/subscriber/{msisdn}/quota` | Sisa kuota & status FUP | Respons 200-800 ms |
| GET | `/offers?msisdn=` | Daftar paket (BID) yang eligible | Harga & masa aktif |
| POST | `/purchase` | Beli paket | Wajib header `Idempotency-Key`; bisa timeout |
| POST | `/loan/eligibility` | Cek Paket Darurat | Mengembalikan limit & biaya |
| GET | `/network/status?cell=` | Status jaringan di sel | Bisa "normal" atau "degraded" |
| POST | `/ticket` | Buat tiket gangguan | Mengembalikan nomor tiket |

## 2. Skema usulan prototipe

Format error semua endpoint: `{"error": {"code": "KODE", "message": "..."}}`.

### GET /subscriber/{msisdn}/profile
```json
{"msisdn": "081200000002", "name": "Budi Dummy", "email": "budi.dummy@example.com", "segment": "Light",
 "consent": {"granted": true, "purpose": "Asisten Kuota"}, "balance_idr": 1500}
```
- `name` dan `email` adalah PII: agen membuangnya dan log meng-mask-nya.
- `balance_idr` adalah **tambahan usulan**. Kontrak tidak menyebut dari mana saldo pulsa diambil.
- Error: `404 SUBSCRIBER_NOT_FOUND`.

### GET /subscriber/{msisdn}/quota
```json
{"msisdn": "081200000002", "remaining_mb": 0, "total_mb": 5120, "fup_active": false}
```
Mock menunda 200-800 ms (acak) sesuai catatan kontrak. Agen mencatat peringatan di trace bila lebih dari 800 ms.

### GET /offers?msisdn=
```json
{"msisdn": "081200000002", "offers": [
  {"bid": "BID-D1", "name": "Internet Harian 1 GB", "quota_mb": 1024, "price_idr": 6000, "validity_days": 1},
  {"bid": "BID-W5", "name": "Internet Mingguan 5 GB", "quota_mb": 5120, "price_idr": 25000, "validity_days": 7},
  {"bid": "BID-M12", "name": "Internet Bulanan 12 GB", "quota_mb": 12288, "price_idr": 50000, "validity_days": 30}]}
```
Daftar berbeda per pelanggan (pelanggan "Light" tidak melihat paket 30 GB).

### POST /loan/eligibility
Request: `{"msisdn": "081200000002"}`
```json
{"msisdn": "081200000002", "eligible": true, "limit_idr": 10000, "fee_idr": 2000}
```
Bila tidak layak: `"eligible": false` dan `"reason": "NOT_ELIGIBLE"`.

### POST /purchase
Header wajib: `Idempotency-Key: <string unik per usulan pembelian>`
Request:
```json
{"msisdn": "081200000002", "bid": "BID-D1", "payment_method": "emergency"}
```
`payment_method`: `"balance"` (potong pulsa) atau `"emergency"` (Paket Darurat).

Respons sukses (200):
```json
{"loan_outstanding_idr": 8000, "transaction_id": "TRX-000001", "status": "success", "msisdn": "081200000002",
 "bid": "BID-D1", "name": "Internet Harian 1 GB", "price_idr": 6000, "payment_method": "emergency",
 "balance_idr": 1500, "quota_mb_added": 1024, "validity_days": 1}
```
`loan_outstanding_idr` hanya ada untuk Paket Darurat (harga + biaya).

**Idempotency:** request kedua dengan key dan isi yang sama tidak memproses ulang. Server mengembalikan hasil yang sama
ditambah `"replayed": true`, dan saldo tidak dipotong lagi.

| Status | Kode | Arti |
|---|---|---|
| 400 | `IDEMPOTENCY_KEY_REQUIRED` | Header key tidak ada |
| 400 | `INVALID_PAYMENT_METHOD` | `payment_method` bukan balance/emergency |
| 402 | `INSUFFICIENT_BALANCE` | Pulsa tidak cukup |
| 403 | `CONSENT_REQUIRED` | Pelanggan belum memberi consent (validasi di backend) |
| 409 | `IDEMPOTENCY_KEY_REUSED` | Key sama dipakai untuk isi berbeda |
| 422 | `PACKAGE_NOT_ELIGIBLE` | Paket tidak ada di daftar eligible pelanggan |
| 422 | `EMERGENCY_NOT_ELIGIBLE` | Tidak layak Paket Darurat, atau harga melebihi limit |
| 503 | `SERVICE_UNAVAILABLE` | Disimulasikan untuk pelanggan 081200000008 |

Simulasi timeout (pelanggan 081200000007): transaksi **diproses**, tetapi respons ditunda 6 detik sehingga klien (timeout 5 detik) menyerah.
Retry dengan key yang sama langsung mendapat hasil `replayed`.

### GET /network/status?cell=
```json
{"cell": "CELL-002", "status": "degraded", "detail": "Throughput turun, beban sel tinggi"}
```
`status`: `"normal"` atau `"degraded"`. Error: `404 CELL_NOT_FOUND`.

### POST /ticket
Request:
```json
{"msisdn": "081200000003", "cell": "CELL-002", "category": "network_degraded", "summary": "Internet lambat"}
```
```json
{"ticket_id": "TKT-000001", "status": "open", "msisdn": "081200000003", "cell": "CELL-002",
 "category": "network_degraded", "summary": "Internet lambat", "existing": false}
```
Status 201 untuk tiket baru. Bila sudah ada tiket untuk nomor + sel yang sama: status 200, `"existing": true`, nomor tiket lama.
Pencegahan tiket ganda ini adalah **usulan prototipe**, bukan bagian kontrak.

### POST /admin/reset (khusus demo, bukan kontrak)
Mengembalikan saldo, kuota, pembelian, dan tiket ke kondisi awal.

## 3. Perilaku Tool Gateway (`tools.py`)

| Tool | Endpoint | Timeout | Retry |
|---|---|---|---|
| `get_profile`, `get_quota`, `get_offers`, `get_network` | GET masing-masing | 2 detik | 1x |
| `check_loan` | POST `/loan/eligibility` (hanya membaca) | 2 detik | 1x |
| `purchase` | POST `/purchase` | 5 detik | 2x, **key yang sama** |
| `create_ticket` | POST `/ticket` | 2 detik | tidak ada |

Retry hanya untuk timeout, koneksi putus, dan 5xx. Kode 4xx tidak di-retry. Semua angka adalah usulan dan bisa diubah di `tools.py`.
Setiap percobaan dicatat di trace (data pribadi di-mask).

## 4. API aplikasi chat (khusus UI prototipe)

| Method | Path | Fungsi |
|---|---|---|
| GET | `/` | Halaman chat |
| GET | `/api/customers` | Daftar pelanggan dummy untuk dropdown |
| POST | `/api/chat` | Kirim pesan atau tombol, terima balasan |
| GET | `/api/trace?conversation_id=` | Trace langkah agen (ter-mask) |
| POST | `/api/reset` | Reset data mock |

**POST /api/chat** - request (percakapan baru: tanpa `conversation_id`, wajib `msisdn`):
```json
{"conversation_id": null, "msisdn": "081200000001", "text": "kuota saya habis"}
```
atau mengetuk tombol: `{"conversation_id": "a1b2c3d4", "msisdn": "081200000001", "action": {"type": "confirm_purchase", "token": "..."}}`

Respons:
```json
{"conversation_id": "a1b2c3d4",
 "replies": [{"text": "Pulsa Kakak saat ini Rp60.000. ...", "buttons": [
    {"label": "Ya, beli sekarang", "action": {"type": "confirm_purchase", "token": "..."}},
    {"label": "Batal", "action": {"type": "cancel"}}]}],
 "handoff": null}
```
Jenis `action.type`: `say` (pintasan teks), `confirm_purchase`, `confirm_ticket`, `see_packages`, `other_packages`,
`choose_package`, `cancel`, `handoff`. `handoff` berisi ringkasan untuk agen manusia bila percakapan diserahkan.

## 5. Format trace

Setiap langkah agen menjadi satu baris JSON di `logs/trace.jsonl` (dan di panel UI):
```json
{"time": "16:13:32", "conversation_id": "a1b2c3d4", "step": 19, "actor": "tool", "event": "api_call",
 "details": {"tool": "purchase", "method": "POST", "path": "/purchase", "attempt": "1/3", "result": "TimeoutError", "ms": 5005, "...": "..."}}
```
`actor`: `customer`, `llm`, `rules`, `tool`, `agent`, `human`. Nomor telepon di-mask (`0812****0007`), `name` dan `email` menjadi `***`.
