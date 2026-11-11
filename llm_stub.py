"""
PENGGANTI LLM (stub) - hanya 2 tugas, sama seperti yang direncanakan untuk LLM asli:
  1. understand(): memahami MAKSUD teks pelanggan (intent).
  2. say_*(): menulis KALIMAT jawaban dalam Bahasa Indonesia dari fakta yang sudah diberikan.

Yang TIDAK dilakukan file ini (dan tidak boleh dilakukan LLM asli):
  - memutuskan eligibility, memilih paket, menentukan jaringan terganggu atau tidak,
  - memanggil API, membeli, atau mengonfirmasi pembelian.
Semua itu ada di rules.py dan agent.py. Fakta dalam kalimat HANYA datang dari argumen
yang diberikan agen (hasil API), jadi tidak ada angka yang dikarang.

Di prototipe ini tidak ada LLM sungguhan (tidak butuh API key). Intent dibaca dari kata kunci.
Untuk memakai LLM asli, cukup ganti isi file ini, lihat README bagian "Mengganti stub dengan LLM".
"""
import re

# ------------------------------------------------------------------ 1. memahami maksud

ANGRY_WORDS = ["marah", "kesal", "kesel", "sebel", "bohong", "penipu", "nipu", "parah", "payah", "tidak becus", "ga becus"]
YES_WORDS = {"ya", "iya", "y", "yes", "oke", "ok", "okay", "boleh", "setuju", "lanjut", "siap"}
NO_WORDS = {"tidak", "nggak", "enggak", "gak", "ga", "batal", "jangan", "no", "tidak jadi", "gak jadi", "ga jadi", "nggak jadi"}

# urutan penting: yang paling atas dicek lebih dulu
KEYWORDS = [
    ("handoff",       ["agen", "agent", "operator", "customer service", "cs", "petugas", "manusia", "call center"]),
    ("check_quota",   ["sisa kuota", "cek kuota", "kuota berapa", "berapa kuota", "sisa paket"]),
    ("slow_internet", ["lambat", "lemot", "lelet", "loading", "buffering", "sinyal jelek", "putus-putus",
                       "tidak stabil", "gangguan", "bisa internet", "bisa browsing"]),
    ("need_package",  ["habis", "paket", "beli", "isi kuota", "tambah kuota", "kuota"]),
    ("thanks",        ["terima kasih", "makasih", "thanks", "thx"]),
    ("greeting",      ["halo", "hai", "hi", "hello", "selamat pagi", "selamat siang", "selamat sore", "selamat malam"]),
]


def has_word(text, word):
    return re.search(r"\b" + re.escape(word) + r"\b", text) is not None


def understand(text):
    """Mengembalikan {"intent": ..., "angry": True/False}."""
    t = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    angry = any(has_word(t, w) for w in ANGRY_WORDS)
    if t in YES_WORDS:
        return {"intent": "yes", "angry": angry}
    if t in NO_WORDS:
        return {"intent": "no", "angry": angry}
    for intent, words in KEYWORDS:
        if any(has_word(t, w) for w in words):
            return {"intent": intent, "angry": angry}
    return {"intent": "unknown", "angry": angry}


# ------------------------------------------------------------------ 2. menulis jawaban

def rp(amount):
    return "Rp" + format(amount, ",").replace(",", ".")


def mb(n):
    if n >= 1024:
        gb = n / 1024
        return ("%d GB" % gb) if gb == int(gb) else ("%.1f GB" % gb).replace(".", ",")
    return "%d MB" % n


def say_greeting():
    return ("Halo Kak! Saya Asisten Kuota MyTelkomsel. Saya bisa cek sisa kuota, bantu beli paket, "
            "dan bantu cek kendala internet. Ada yang bisa dibantu?")


def say_rephrase():
    return 'Maaf Kak, saya belum paham maksudnya. Bisa ditulis ulang? Contoh: "kuota saya habis" atau "internet saya lambat".'


def say_thanks():
    return "Sama-sama Kak! Kalau ada kendala lagi, kabari saya ya."


def say_no_consent():
    return ("Untuk membantu, saya perlu persetujuan Kakak untuk memakai data layanan (kuota dan jaringan). "
            "Saat ini persetujuan belum aktif, jadi saya tidak bisa melanjutkan. "
            "Kakak bisa mengaktifkannya di menu Privasi MyTelkomsel, atau saya hubungkan ke agen.")


def say_api_error():
    return ("Maaf Kak, data layanan belum bisa saya ambil saat ini. "
            "Silakan ketik ulang permintaan Kakak sebentar lagi, atau saya hubungkan ke agen.")


def say_quota_status(quota):
    fup = ("Status FUP: AKTIF, kecepatan internet sedang dibatasi."
           if quota["fup_active"] else "Status FUP: tidak aktif.")
    return "Sisa kuota Kakak %s dari %s. %s" % (mb(quota["remaining_mb"]), mb(quota["total_mb"]), fup)


def say_quota_not_depleted(quota):
    return "Kuota Kakak sebenarnya belum habis. " + say_quota_status(quota) + " Mau tetap lihat paket tambahan?"


def say_quota_depleted():
    return "Kuota Kakak sudah habis (sisa 0 MB)."


def say_slow_because_depleted():
    return "Internet terasa lambat karena kuota Kakak sudah habis (sisa 0 MB), bukan karena gangguan jaringan."


def say_slow_because_fup(quota):
    return ("Penyebab yang terdeteksi: FUP aktif. Sisa kuota Kakak %s, tetapi kecepatan sedang dibatasi. "
            "Karena penyebabnya FUP, saya tidak membuat tiket gangguan jaringan." % mb(quota["remaining_mb"]))


def say_propose(offer, balance, recommended):
    detail = "%s (%s, berlaku %d hari) seharga %s" % (
        offer["name"], mb(offer["quota_mb"]), offer["validity_days"], rp(offer["price_idr"]))
    if recommended:
        return ("Pulsa Kakak saat ini %s. Rekomendasi saya: %s, paling hemat per GB dari paket yang cukup "
                "dengan pulsa Kakak. Harga dipotong dari pulsa. Mau beli sekarang?" % (rp(balance), detail))
    return "Baik. %s, dipotong dari pulsa Kakak (%s). Lanjut beli?" % (detail, rp(balance))


def say_other_packages():
    return "Ini pilihan paket lain yang cukup dengan pulsa Kakak. Silakan pilih satu:"


def say_emergency(offer, balance, loan):
    return ("Pulsa Kakak %s belum cukup untuk paket yang tersedia, tetapi Kakak memenuhi syarat Paket Darurat "
            "(limit %s). Paket: %s (%s, berlaku %d hari) seharga %s. Ada biaya layanan %s, jadi total yang "
            "harus dibayar nanti %s (dipotong dari top-up berikutnya). Mau ambil Paket Darurat ini?" % (
                rp(balance), rp(loan["limit_idr"]), offer["name"], mb(offer["quota_mb"]), offer["validity_days"],
                rp(offer["price_idr"]), rp(loan["fee_idr"]), rp(offer["price_idr"] + loan["fee_idr"])))


def say_no_emergency(balance, cheapest_price):
    return ("Pulsa Kakak %s belum cukup untuk paket termurah (%s), dan saat ini Kakak belum memenuhi syarat "
            "Paket Darurat. Kakak bisa isi pulsa dulu, atau saya hubungkan ke agen." % (rp(balance), rp(cheapest_price)))


def say_nothing_in_limit(limit):
    return ("Kakak memenuhi syarat Paket Darurat dengan limit %s, tetapi tidak ada paket yang harganya masuk "
            "limit tersebut. Saya hubungkan ke agen untuk dibantu." % rp(limit))


def say_offer_changed():
    return "Harga atau ketersediaan paket berubah sejak tadi, jadi pembelian saya batalkan demi keamanan. Mau lihat paket terbaru?"


def say_purchase_success(data, remaining_mb):
    if data["payment_method"] == "emergency":
        paid = "Paket Darurat aktif. Tagihan %s akan dipotong dari top-up berikutnya." % rp(data["loan_outstanding_idr"])
    else:
        paid = "Harga %s sudah dipotong dari pulsa. Sisa pulsa %s." % (rp(data["price_idr"]), rp(data["balance_idr"]))
    now = " Sisa kuota Kakak sekarang %s." % mb(remaining_mb) if remaining_mb is not None else ""
    return "Berhasil! %s sudah aktif. %s%s Nomor transaksi: %s." % (data["name"], paid, now, data["transaction_id"])


def say_purchase_rejected(code):
    return "Pembelian ditolak oleh sistem (kode: %s). Kakak bisa mencoba lagi nanti, atau saya hubungkan ke agen." % code


def say_confirm_invalid():
    return "Konfirmasi ini sudah tidak berlaku. Silakan ulangi permintaan Kakak."


def say_confirm_expired():
    return "Konfirmasi ini sudah kedaluwarsa (lebih dari 5 menit). Silakan ulangi permintaan Kakak."


def say_use_button():
    return 'Untuk keamanan, pembelian hanya bisa dikonfirmasi lewat tombol "Ya, beli sekarang" di atas ya Kak.'


def say_cancelled():
    return "Baik, tidak jadi. Ada lagi yang bisa saya bantu?"


def say_network_degraded(cell, detail, quota):
    return ("Kuota Kakak aman (sisa %s, FUP tidak aktif), tetapi jaringan di lokasi Kakak (%s) terdeteksi terganggu: %s. "
            "Ini kemungkinan penyebab internet lambat. Mau saya buatkan tiket gangguan?" % (mb(quota["remaining_mb"]), cell, detail))


def say_network_normal(quota):
    return ("Kuota Kakak aman (sisa %s, FUP tidak aktif) dan jaringan di lokasi Kakak terpantau normal. "
            "Coba aktifkan mode pesawat 10 detik lalu matikan lagi. Kalau masih lambat, saya hubungkan ke agen." % mb(quota["remaining_mb"]))


def say_network_unknown():
    return "Lokasi Kakak belum terbaca, jadi saya belum bisa mengecek jaringan. Saya bisa hubungkan ke agen untuk dibantu."


def say_ticket_created(ticket_id, existing):
    if existing:
        return "Sudah ada tiket gangguan untuk lokasi Kakak: %s. Saya tidak membuat tiket baru." % ticket_id
    return "Tiket gangguan sudah dibuat. Nomor tiket Kakak: %s. Tim jaringan akan menindaklanjuti." % ticket_id


HANDOFF_TEXT = {
    "customer_request":   "Baik Kak, saya hubungkan ke agen. Ringkasan percakapan ini ikut diteruskan supaya Kakak tidak perlu mengulang.",
    "angry":              "Mohon maaf atas ketidaknyamanannya, Kak. Saya hubungkan ke agen supaya bisa dibantu langsung.",
    "misunderstood_twice": "Maaf, saya masih belum paham maksud Kakak. Saya hubungkan ke agen supaya bisa dibantu langsung.",
    "api_failures":       "Maaf, sistem sedang bermasalah. Saya hubungkan ke agen supaya bisa dibantu.",
    "purchase_unknown":   ("Maaf Kak, saya belum bisa memastikan status pembelian Kakak. Mohon JANGAN membeli ulang dulu. "
                           "Saya teruskan ke agen untuk mengecek status transaksinya."),
    "no_consent":         "Baik Kak, saya hubungkan ke agen.",
}


def say_handoff(reason, conv_id):
    return "%s (Ref: %s)" % (HANDOFF_TEXT[reason], conv_id)


def say_after_handoff(conv_id):
    return "Percakapan ini sudah diteruskan ke agen (Ref: %s). Agen akan melanjutkan dari ringkasan percakapan." % conv_id
