"""
DATA DUMMY untuk prototipe Asisten Kuota.

Semua data di sini FIKTIF. Tidak ada data pelanggan, kode, atau dokumen internal asli.
Nomor 0812000000NN hanya pola nomor uji, bukan nomor pelanggan sebenarnya.

File ini HANYA dibaca oleh mock_api.py (dan server.py untuk daftar pilihan demo).
Agen (agent.py, tools.py) TIDAK PERNAH membaca file ini: agen hanya bicara lewat API.
"""

# Katalog paket (BID = kode paket). Harga dalam rupiah, kuota dalam MB.
OFFERS = {
    "BID-D1":  {"name": "Internet Harian 1 GB",   "quota_mb": 1024,  "price_idr": 6000,  "validity_days": 1},
    "BID-W5":  {"name": "Internet Mingguan 5 GB", "quota_mb": 5120,  "price_idr": 25000, "validity_days": 7},
    "BID-M12": {"name": "Internet Bulanan 12 GB", "quota_mb": 12288, "price_idr": 50000, "validity_days": 30},
    "BID-M30": {"name": "Internet Bulanan 30 GB", "quota_mb": 30720, "price_idr": 90000, "validity_days": 30},
}

# Kondisi jaringan per sel (cell). Di aplikasi asli, sel diketahui dari konteks perangkat.
CELLS = {
    "CELL-001": {"status": "normal",   "detail": "Jaringan normal"},
    "CELL-002": {"status": "degraded", "detail": "Throughput turun, beban sel tinggi"},
}

# purchase_mode mengatur perilaku POST /purchase untuk pelanggan ini:
#   "normal"       = berjalan normal
#   "timeout_once" = transaksi DIPROSES, tapi respons terlambat (klien timeout). Menguji idempotency.
#   "always_fail"  = selalu error 503 dan tidak diproses. Menguji handoff "status tidak jelas".
CUSTOMERS = {
    "081200000001": {
        "scenario": "S1 - Kuota habis, pulsa cukup",
        "name": "Andi Dummy", "email": "andi.dummy@example.com", "segment": "Regular",
        "consent": True, "balance_idr": 60000,
        "quota_mb": 0, "total_mb": 12288, "fup_active": False,
        "cell": "CELL-001",
        "loan": {"eligible": False, "limit_idr": 0, "fee_idr": 0},
        "eligible_bids": ["BID-D1", "BID-W5", "BID-M12", "BID-M30"],
        "purchase_mode": "normal",
    },
    "081200000002": {
        "scenario": "S2 - Kuota habis, pulsa kurang, layak Paket Darurat",
        "name": "Budi Dummy", "email": "budi.dummy@example.com", "segment": "Light",
        "consent": True, "balance_idr": 1500,
        "quota_mb": 0, "total_mb": 5120, "fup_active": False,
        "cell": "CELL-001",
        "loan": {"eligible": True, "limit_idr": 10000, "fee_idr": 2000},
        "eligible_bids": ["BID-D1", "BID-W5", "BID-M12"],
        "purchase_mode": "normal",
    },
    "081200000003": {
        "scenario": "S3 - Internet lambat, jaringan memang terganggu",
        "name": "Citra Dummy", "email": "citra.dummy@example.com", "segment": "Regular",
        "consent": True, "balance_idr": 30000,
        "quota_mb": 4096, "total_mb": 12288, "fup_active": False,
        "cell": "CELL-002",
        "loan": {"eligible": False, "limit_idr": 0, "fee_idr": 0},
        "eligible_bids": ["BID-D1", "BID-W5", "BID-M12", "BID-M30"],
        "purchase_mode": "normal",
    },
    "081200000004": {
        "scenario": "Edge - Pulsa kurang, TIDAK layak Paket Darurat",
        "name": "Dewi Dummy", "email": "dewi.dummy@example.com", "segment": "Light",
        "consent": True, "balance_idr": 1000,
        "quota_mb": 0, "total_mb": 5120, "fup_active": False,
        "cell": "CELL-001",
        "loan": {"eligible": False, "limit_idr": 0, "fee_idr": 0},
        "eligible_bids": ["BID-D1", "BID-W5", "BID-M12"],
        "purchase_mode": "normal",
    },
    "081200000005": {
        "scenario": "Edge - Belum memberi consent",
        "name": "Eko Dummy", "email": "eko.dummy@example.com", "segment": "Regular",
        "consent": False, "balance_idr": 40000,
        "quota_mb": 0, "total_mb": 12288, "fup_active": False,
        "cell": "CELL-001",
        "loan": {"eligible": False, "limit_idr": 0, "fee_idr": 0},
        "eligible_bids": ["BID-D1", "BID-W5", "BID-M12", "BID-M30"],
        "purchase_mode": "normal",
    },
    "081200000006": {
        "scenario": "Edge - Lambat karena FUP (bukan jaringan)",
        "name": "Fani Dummy", "email": "fani.dummy@example.com", "segment": "Heavy",
        "consent": True, "balance_idr": 80000,
        "quota_mb": 2048, "total_mb": 30720, "fup_active": True,
        "cell": "CELL-001",
        "loan": {"eligible": False, "limit_idr": 0, "fee_idr": 0},
        "eligible_bids": ["BID-D1", "BID-W5", "BID-M12", "BID-M30"],
        "purchase_mode": "normal",
    },
    "081200000007": {
        "scenario": "Edge - Pembelian timeout (uji idempotency)",
        "name": "Gita Dummy", "email": "gita.dummy@example.com", "segment": "Regular",
        "consent": True, "balance_idr": 60000,
        "quota_mb": 0, "total_mb": 12288, "fup_active": False,
        "cell": "CELL-001",
        "loan": {"eligible": False, "limit_idr": 0, "fee_idr": 0},
        "eligible_bids": ["BID-D1", "BID-W5", "BID-M12", "BID-M30"],
        "purchase_mode": "timeout_once",
    },
    "081200000008": {
        "scenario": "Edge - API pembelian error terus (handoff)",
        "name": "Hadi Dummy", "email": "hadi.dummy@example.com", "segment": "Regular",
        "consent": True, "balance_idr": 60000,
        "quota_mb": 0, "total_mb": 12288, "fup_active": False,
        "cell": "CELL-001",
        "loan": {"eligible": False, "limit_idr": 0, "fee_idr": 0},
        "eligible_bids": ["BID-D1", "BID-W5", "BID-M12", "BID-M30"],
        "purchase_mode": "always_fail",
    },
    "081200000009": {
        "scenario": "Edge - Lambat, tapi kuota & jaringan normal",
        "name": "Indah Dummy", "email": "indah.dummy@example.com", "segment": "Regular",
        "consent": True, "balance_idr": 20000,
        "quota_mb": 5120, "total_mb": 12288, "fup_active": False,
        "cell": "CELL-001",
        "loan": {"eligible": False, "limit_idr": 0, "fee_idr": 0},
        "eligible_bids": ["BID-D1", "BID-W5", "BID-M12", "BID-M30"],
        "purchase_mode": "normal",
    },
}
