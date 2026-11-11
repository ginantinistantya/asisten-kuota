"""
AGEN (orkestrator) - menyambungkan semua bagian:

    teks pelanggan -> llm_stub.understand()  (apa maksudnya?)
                   -> agent.py               (alur mana yang dijalankan?)
                   -> tools.Gateway          (ambil data lewat API)
                   -> rules.py               (KEPUTUSAN: eligible? paket apa? jaringan?)
                   -> llm_stub.say_*()       (tulis jawaban dari fakta)

Pembagian peran (sama dengan slide arsitektur):
    LLM (stub)  : memahami dan menjelaskan, TIDAK memutuskan.
    rules.py    : memutuskan.
    tools.py    : mengeksekusi lewat API.
    Pelanggan   : mengotorisasi pembelian/tiket LEWAT TOMBOL (bukan lewat teks yang diketik).
    Agen manusia: menerima handoff.

Agen ini TIDAK mengimpor dummy_data / mock_api: ia hanya tahu API (tidak ada akses langsung ke database).
"""
import hashlib
import secrets
import time

import llm_stub as llm
import rules
from tracelog import mask_number

CONFIRM_VALID_SECONDS = 300      # tombol konfirmasi berlaku 5 menit
MAX_API_FAILURES = 2             # gagal ambil data 2x dalam satu percakapan -> handoff


def reply(text, *buttons):
    return {"text": text, "buttons": list(buttons)}


def button(label, **action):
    return {"label": label, "action": action}


def quick_buttons():
    return [button("Kuota saya habis", type="say", text="kuota saya habis"),
            button("Internet saya lambat", type="say", text="internet saya lambat"),
            button("Cek sisa kuota", type="say", text="cek sisa kuota")]


class Conversation:
    """Ingatan satu percakapan. Hanya menyimpan yang perlu (minimisasi data): tanpa nama/email."""

    def __init__(self, conv_id, msisdn, cell):
        self.id = conv_id
        self.msisdn = msisdn          # dari sesi login aplikasi, BUKAN dari teks pelanggan
        self.cell = cell              # dari konteks aplikasi/perangkat (asumsi, lihat README)
        self.pending = None           # usulan yang menunggu konfirmasi (pembelian / tiket)
        self.affordable = {}          # bid -> paket yang boleh dipilih (hasil /offers terakhir)
        self.done = {}                # token -> jawaban; supaya tombol yang ditekan 2x tidak mengulang aksi
        self.unknown_count = 0        # berapa kali berturut-turut tidak paham
        self.api_failures = 0
        self.handed_off = False
        self.facts = {}               # temuan diagnosis, ikut dikirim ke agen manusia saat handoff


class Agent:
    def __init__(self, gateway, tracelog):
        self.gw = gateway
        self.trace = tracelog
        self.handoffs = []            # antrean handoff ke agen manusia (simulasi, bukan endpoint kontrak)

    def new_conversation(self, msisdn, cell):
        conv = Conversation(secrets.token_hex(4), msisdn, cell)
        self.trace.log(conv.id, "agent", "conversation_started", msisdn=msisdn, cell=cell)
        return conv

    # ============================================================ pintu masuk

    def handle(self, conv, text=None, action=None):
        """Terima satu pesan (text) ATAU satu ketukan tombol (action). Kembalikan daftar balasan."""
        replies = self.route(conv, text, action)
        for r in replies:
            self.trace.log(conv.id, "agent", "reply", text=r["text"], buttons=[b["label"] for b in r["buttons"]])
        return replies

    def route(self, conv, text, action):
        if conv.handed_off:
            return [reply(llm.say_after_handoff(conv.id))]

        if action and action.get("type") == "say":      # tombol pintasan = sama dengan mengetik teks
            text, action = action["text"], None
        if action:
            self.trace.log(conv.id, "customer", "button", action=action)
            return self.on_button(conv, action)

        self.trace.log(conv.id, "customer", "message", text=(text or "")[:300])
        understood = llm.understand(text or "")
        self.trace.log(conv.id, "llm", "intent", **understood)
        intent = understood["intent"]

        if understood["angry"]:
            return self.handoff(conv, "angry")
        if intent == "handoff":
            return self.handoff(conv, "customer_request")
        if intent != "unknown":
            conv.unknown_count = 0

        if intent in ("check_quota", "slow_internet", "need_package"):
            conv.pending = None          # topik baru: tombol konfirmasi lama tidak berlaku lagi
        if intent == "check_quota":
            return self.flow_check_quota(conv)
        if intent == "slow_internet":
            return self.flow_slow_internet(conv)
        if intent == "need_package":
            return self.flow_need_package(conv)

        if intent == "yes" and conv.pending:
            # Sengaja TIDAK memproses "ya" yang diketik. Pembelian hanya sah lewat tombol.
            return [reply(llm.say_use_button())]
        if intent == "no" and conv.pending:
            conv.pending = None
            return [reply(llm.say_cancelled())]
        if intent == "thanks":
            return [reply(llm.say_thanks())]
        if intent in ("greeting", "yes", "no"):
            return [reply(llm.say_greeting(), *quick_buttons())]

        conv.unknown_count += 1          # tidak paham
        if conv.unknown_count >= 2:
            return self.handoff(conv, "misunderstood_twice")
        return [reply(llm.say_rephrase(), *quick_buttons())]

    def on_button(self, conv, action):
        kind = action.get("type")
        if kind == "confirm_purchase":
            return self.confirm(conv, action.get("token"), "purchase")
        if kind == "confirm_ticket":
            return self.confirm(conv, action.get("token"), "ticket")
        if kind == "see_packages":
            info, blocked = self.diagnose_quota(conv)
            return blocked or self.offer_flow(conv, info["balance"])
        if kind == "other_packages":
            return self.show_other_packages(conv)
        if kind == "choose_package":
            return self.choose_package(conv, action.get("bid"))
        if kind == "cancel":
            conv.pending = None
            return [reply(llm.say_cancelled())]
        if kind == "handoff":
            return self.handoff(conv, "customer_request")
        return [reply(llm.say_confirm_invalid())]

    # ============================================================ langkah awal bersama

    def diagnose_quota(self, conv):
        """Langkah awal semua alur: cek consent, lalu kuota. Kembalikan (info, jawaban_jika_terhalang)."""
        result = self.gw.call(conv, "get_profile")
        if not result["ok"]:
            return None, self.api_failed(conv)
        profile = result["data"]
        granted = rules.has_consent(profile)
        self.trace.log(conv.id, "rules", "consent_check", granted=granted)
        if not granted:                  # tanpa consent: berhenti, tidak ada data lain yang diambil
            conv.facts["consent"] = "belum diberikan"
            return None, [reply(llm.say_no_consent(), button("Hubungi agen", type="handoff"))]
        balance = profile["balance_idr"]   # dari profil hanya saldo yang dipakai; nama/email dibuang di sini

        result = self.gw.call(conv, "get_quota")
        if not result["ok"]:
            return None, self.api_failed(conv)
        quota = result["data"]
        state = rules.quota_state(quota)
        self.trace.log(conv.id, "rules", "quota_state", state=state,
                       remaining_mb=quota["remaining_mb"], fup_active=quota["fup_active"])
        conv.facts.update(quota_state=state, remaining_mb=quota["remaining_mb"], fup_active=quota["fup_active"])
        return {"balance": balance, "quota": quota, "state": state}, None

    # ============================================================ alur-alur

    def flow_check_quota(self, conv):
        info, blocked = self.diagnose_quota(conv)
        if blocked:
            return blocked
        return [reply(llm.say_quota_status(info["quota"]), button("Lihat paket kuota", type="see_packages"))]

    def flow_need_package(self, conv):
        info, blocked = self.diagnose_quota(conv)
        if blocked:
            return blocked
        if info["state"] != "depleted":      # pelanggan bilang habis, tetapi data bilang belum: katakan apa adanya
            return [reply(llm.say_quota_not_depleted(info["quota"]),
                          button("Lihat paket", type="see_packages"), button("Tidak perlu", type="cancel"))]
        return [reply(llm.say_quota_depleted())] + self.offer_flow(conv, info["balance"])

    def flow_slow_internet(self, conv):
        info, blocked = self.diagnose_quota(conv)
        if blocked:
            return blocked
        if info["state"] == "depleted":      # penyebab = kuota habis -> alur beli paket, BUKAN tiket jaringan
            return [reply(llm.say_slow_because_depleted())] + self.offer_flow(conv, info["balance"])
        if info["state"] == "fup":           # penyebab = FUP -> tidak membuat tiket jaringan
            return [reply(llm.say_slow_because_fup(info["quota"]),
                          button("Lihat paket", type="see_packages"), button("Hubungi agen", type="handoff"))]

        # Kuota & FUP normal -> baru periksa jaringan di lokasi pelanggan
        if not conv.cell:
            return [reply(llm.say_network_unknown(), button("Hubungi agen", type="handoff"))]
        result = self.gw.call(conv, "get_network")
        if not result["ok"]:
            return self.api_failed(conv)
        network = result["data"]
        degraded = rules.network_degraded(network)
        self.trace.log(conv.id, "rules", "network_state", cell=network["cell"], status=network["status"])
        conv.facts["network_status"] = network["status"]
        if not degraded:                     # normal -> tidak ada tiket
            return [reply(llm.say_network_normal(info["quota"]), button("Hubungi agen", type="handoff"))]
        pending = self.new_pending(conv, "ticket")
        return [reply(llm.say_network_degraded(network["cell"], network["detail"], info["quota"]),
                      button("Buat tiket gangguan", type="confirm_ticket", token=pending["token"]),
                      button("Hubungi agen", type="handoff"), button("Tidak perlu", type="cancel"))]

    # ------------------------------------------------------------ rekomendasi paket

    def offer_flow(self, conv, balance):
        result = self.gw.call(conv, "get_offers")
        if not result["ok"]:
            return self.api_failed(conv)
        offers = result["data"]["offers"]
        can_buy = rules.affordable(offers, balance)
        self.trace.log(conv.id, "rules", "affordable", balance_idr=balance, bids=[o["bid"] for o in can_buy])

        if can_buy:                          # pulsa cukup -> rekomendasikan, minta konfirmasi
            conv.affordable = {o["bid"]: o for o in can_buy}
            best = rules.recommend(can_buy)
            self.trace.log(conv.id, "rules", "recommend", bid=best["bid"])
            return [self.propose_purchase(conv, best, "balance", balance, recommended=True)]

        # pulsa tidak cukup untuk paket apa pun -> cek Paket Darurat lewat API (bukan tebakan LLM)
        conv.affordable = {}
        result = self.gw.call(conv, "check_loan", body={"msisdn": conv.msisdn})
        if not result["ok"]:
            return self.api_failed(conv)
        loan = result["data"]
        self.trace.log(conv.id, "rules", "emergency_eligibility", eligible=loan["eligible"], limit_idr=loan["limit_idr"])
        if not loan["eligible"]:
            return [reply(llm.say_no_emergency(balance, rules.cheapest(offers)["price_idr"]),
                          button("Hubungi agen", type="handoff"))]
        options = rules.within_limit(offers, loan["limit_idr"])
        if not options:
            return [reply(llm.say_nothing_in_limit(loan["limit_idr"]), button("Hubungi agen", type="handoff"))]
        best = rules.recommend(options)
        return [self.propose_purchase(conv, best, "emergency", balance, loan=loan)]

    def propose_purchase(self, conv, offer, method, balance, recommended=False, loan=None):
        """Buat usulan pembelian + tombol konfirmasi. BELUM membeli apa pun."""
        pending = self.new_pending(conv, "purchase", offer=offer, method=method,
                                   fee=loan["fee_idr"] if loan else 0)
        self.trace.log(conv.id, "agent", "confirmation_requested", bid=offer["bid"],
                       price_idr=offer["price_idr"], method=method)
        if method == "emergency":
            text = llm.say_emergency(offer, balance, loan)
            yes_label = "Ya, ambil Paket Darurat"
        else:
            text = llm.say_propose(offer, balance, recommended)
            yes_label = "Ya, beli sekarang"
        buttons = [button(yes_label, type="confirm_purchase", token=pending["token"])]
        if method == "balance" and len(conv.affordable) > 1:
            buttons.append(button("Lihat paket lain", type="other_packages"))
        buttons.append(button("Batal", type="cancel"))
        return reply(text, *buttons)

    def show_other_packages(self, conv):
        if not conv.affordable:
            return [reply(llm.say_confirm_invalid())]
        options = sorted(conv.affordable.values(), key=lambda o: o["price_idr"])
        buttons = [button("%s - %s" % (o["name"], llm.rp(o["price_idr"])), type="choose_package", bid=o["bid"])
                   for o in options]
        return [reply(llm.say_other_packages(), *buttons)]

    def choose_package(self, conv, bid):
        offer = conv.affordable.get(bid)         # hanya paket dari hasil /offers yang terjangkau
        if offer is None:
            return [reply(llm.say_confirm_invalid())]
        profile = self.gw.call(conv, "get_profile")      # ambil saldo terbaru
        if not profile["ok"]:
            return self.api_failed(conv)
        return [self.propose_purchase(conv, offer, "balance", profile["data"]["balance_idr"])]

    # ============================================================ konfirmasi & eksekusi

    def new_pending(self, conv, kind, offer=None, method=None, fee=0):
        """Catat usulan yang menunggu konfirmasi. Token ini yang harus dibawa tombol konfirmasi."""
        token = secrets.token_hex(8)
        pending = {"kind": kind, "token": token, "method": method, "fee": fee,
                   "expires": time.time() + CONFIRM_VALID_SECONDS}
        if offer:
            pending.update(bid=offer["bid"], name=offer["name"], price=offer["price_idr"])
            # Idempotency-Key: satu usulan = satu key. Retry memakai key yang sama.
            raw = "%s|%s|%s|%s" % (conv.msisdn, offer["bid"], conv.id, token)
            pending["idem_key"] = hashlib.sha256(raw.encode()).hexdigest()[:32]
        conv.pending = pending
        return pending

    def confirm(self, conv, token, kind):
        if token in conv.done:                   # tombol ditekan lagi: beri jawaban lama, JANGAN mengulang aksi
            self.trace.log(conv.id, "agent", "duplicate_confirm_ignored")
            return conv.done[token]
        pending = conv.pending
        if not pending or pending["token"] != token or pending["kind"] != kind:
            self.trace.log(conv.id, "agent", "confirm_rejected", reason="token tidak cocok")
            return [reply(llm.say_confirm_invalid())]
        if time.time() > pending["expires"]:
            conv.pending = None
            self.trace.log(conv.id, "agent", "confirm_rejected", reason="kedaluwarsa")
            return [reply(llm.say_confirm_expired())]

        conv.pending = None                      # token dipakai sekali; dihanguskan SEBELUM memanggil API
        self.trace.log(conv.id, "customer", "confirmed", kind=kind)
        replies = self.execute_purchase(conv, pending) if kind == "purchase" else self.execute_ticket(conv)
        conv.done[token] = replies
        return replies

    def execute_purchase(self, conv, p):
        # 1) Validasi ulang ke API: data bisa berubah sejak tombol ditampilkan.
        profile = self.gw.call(conv, "get_profile")
        if not profile["ok"]:
            return self.api_failed(conv)
        if not rules.has_consent(profile["data"]):
            return [reply(llm.say_no_consent(), button("Hubungi agen", type="handoff"))]
        offers = self.gw.call(conv, "get_offers")
        if not offers["ok"]:
            return self.api_failed(conv)
        offer = next((o for o in offers["data"]["offers"] if o["bid"] == p["bid"]), None)
        changed = offer is None or offer["price_idr"] != p["price"]
        if p["method"] == "balance" and profile["data"]["balance_idr"] < p["price"]:
            changed = True
        if p["method"] == "emergency" and not changed:
            loan = self.gw.call(conv, "check_loan", body={"msisdn": conv.msisdn})
            if not loan["ok"]:
                return self.api_failed(conv)
            data = loan["data"]
            changed = (not data["eligible"]) or p["price"] > data["limit_idr"] or data["fee_idr"] != p["fee"]
        self.trace.log(conv.id, "rules", "revalidation", passed=not changed)
        if changed:
            return [reply(llm.say_offer_changed(), button("Lihat paket terbaru", type="see_packages"))]

        # 2) Eksekusi pembelian dengan Idempotency-Key.
        body = {"msisdn": conv.msisdn, "bid": p["bid"], "payment_method": p["method"]}
        result = self.gw.call(conv, "purchase", body=body, idempotency_key=p["idem_key"])
        data = result["data"] or {}
        if result["ok"] and data.get("status") == "success":
            conv.facts["purchase"] = "berhasil (%s)" % data["transaction_id"]
            quota = self.gw.call(conv, "get_quota")      # ambil kuota terbaru untuk ditampilkan
            remaining = quota["data"]["remaining_mb"] if quota["ok"] else None
            return [reply(llm.say_purchase_success(data, remaining))]
        if result["status"] is not None and result["status"] < 500:
            code = data.get("error", {}).get("code", "UNKNOWN")      # ditolak jelas: tidak ada transaksi
            return [reply(llm.say_purchase_rejected(code), button("Hubungi agen", type="handoff"))]
        # Timeout / error server setelah semua retry: status TIDAK JELAS. Jangan beli ulang, serahkan ke manusia.
        conv.facts["purchase"] = "status tidak jelas, JANGAN beli ulang (key %s)" % p["idem_key"]
        return self.handoff(conv, "purchase_unknown")

    def execute_ticket(self, conv):
        body = {"msisdn": conv.msisdn, "cell": conv.cell, "category": "network_degraded",
                "summary": "Pelanggan melaporkan internet lambat. Kuota & FUP normal. Status sel: degraded."}
        result = self.gw.call(conv, "create_ticket", body=body)
        if not result["ok"]:
            return self.api_failed(conv)
        ticket = result["data"]
        conv.facts["ticket"] = ticket["ticket_id"]
        return [reply(llm.say_ticket_created(ticket["ticket_id"], ticket.get("existing", False)),
                      button("Hubungi agen", type="handoff"))]

    # ============================================================ kegagalan & handoff

    def api_failed(self, conv):
        conv.api_failures += 1
        self.trace.log(conv.id, "agent", "api_failed", count=conv.api_failures)
        if conv.api_failures >= MAX_API_FAILURES:
            return self.handoff(conv, "api_failures")
        return [reply(llm.say_api_error(), button("Hubungi agen", type="handoff"))]

    def handoff(self, conv, reason):
        """Serahkan ke agen manusia beserta ringkasan (data pribadi di-mask)."""
        conv.handed_off = True
        conv.pending = None
        summary = {"conversation": conv.id, "msisdn": mask_number(conv.msisdn), "cell": conv.cell,
                   "reason": reason, "facts": dict(conv.facts)}
        self.handoffs.append(summary)
        self.trace.log(conv.id, "human", "handoff", **summary)
        return [reply(llm.say_handoff(reason, conv.id))]
