# Skrip Demo (maksimal 3 menit)

Syarat D4: video demo maksimal 3 menit. Video: https://youtu.be/OlyiUIJwpFE (direkam mengikuti skrip ini).
Total target: sekitar 2 menit 50 detik. Latih sekali dulu supaya pas.

**Persiapan (sebelum merekam):** `python run.py` (atau `docker compose up --build`), buka http://localhost:8000, klik **Reset data mock**. Zoom browser 100%.
Panel kiri = chat, panel kanan = trace langkah agen.

| Waktu | Aksi di layar | Yang diucapkan (pegangan, bukan hafalan) |
|---|---|---|
| 0:00-0:15 | Tunjukkan halaman, dropdown pelanggan | "Ini prototipe Asisten Kuota. Agen ini bisa bertindak, bukan cuma menjawab. Semua data dummy, API-nya mock sesuai kontrak." |
| 0:15-0:55 | **S1**: pilih 081200000001, klik "Kuota saya habis". Tunjuk trace: get_profile, get_quota, get_offers, rules. **Belum klik beli.** Lalu ketik `ya` | "Agen cek consent, kuota, lalu paket. Pilihan paket diputuskan rule engine, bukan LLM. Perhatikan: kalau saya cuma mengetik 'ya', tidak terjadi pembelian. Konfirmasi hanya lewat tombol." |
| 0:55-1:10 | Klik **Ya, beli sekarang**. Tunjuk trace: revalidation, purchase, key | "Sebelum beli, agen validasi ulang harga dan saldo. Pembelian membawa Idempotency-Key. Pulsa jadi Rp10.000." |
| 1:10-1:40 | **S2**: pilih 081200000002, "Kuota saya habis". Tunjuk `loan/eligibility` di trace, lalu klik **Ya, ambil Paket Darurat** | "Pulsa Rp1.500 tidak cukup, jadi agen cek eligibility ke API, bukan menebak. Limit dan biaya ditampilkan jelas sebelum konfirmasi." |
| 1:40-2:05 | **S3**: pilih 081200000003, "Internet saya lambat". Tunjuk trace: kuota normal, network degraded. Klik **Buat tiket gangguan** | "Diagnosis berurutan: kuota dan FUP dulu, baru jaringan. Jaringan benar terganggu, jadi tiket ditawarkan dan dibuat setelah saya konfirmasi." |
| 2:05-2:15 | (Opsional, cepat) pilih 081200000006, "Internet saya lambat" | "Kalau penyebabnya FUP, tidak ada tiket jaringan. Ini masalah bisnis yang diselesaikan." |
| 2:15-2:45 | **Timeout**: pilih 081200000007, "Kuota saya habis", klik **Ya, beli sekarang**. Tunggu sekitar 5 detik. Tunjuk trace: percobaan 1/3 TimeoutError, percobaan 2/3 HTTP 200, key sama | "Respons pembelian sengaja dibuat timeout padahal transaksi sudah diproses. Agen retry dengan key yang sama, server mengenali dan tidak memproses dua kali. Pulsa terpotong sekali." |
| 2:45-2:55 | Pilih 081200000008, ulangi sampai pesan handoff muncul | "Kalau status tidak bisa dipastikan, agen tidak beli ulang. Diserahkan ke manusia dengan ringkasan." |
| 2:55-3:00 | (Opsional) terminal: `python -m unittest` | "36 test otomatis lulus." |

## Tips
- Kalau waktu mepet, **buang** baris 2:05-2:15 dan 2:55-3:00.
- Jangan diam saat menunggu timeout (sekitar 5 detik): gunakan waktu itu untuk menjelaskan idempotency.
- Kalau pelanggan sudah dipakai dan hasilnya aneh (pulsa berubah), klik **Reset data mock**.
- Jangan klaim ada LLM sungguhan atau biaya LLM terukur. Katakan: "bagian LLM di sini stub; arsitekturnya sudah memisahkan LLM dari keputusan, jadi bisa diganti".
