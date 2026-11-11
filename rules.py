"""
RULE ENGINE - aturan bisnis yang DETERMINISTIK (input sama -> hasil sama, tanpa LLM).

Semua keputusan penting ada di sini: consent, status kuota, paket mana yang terjangkau,
paket mana yang direkomendasikan, jaringan terganggu atau tidak. Isinya fungsi murni
(tidak memanggil API, tidak mengubah apa pun) sehingga mudah dites dan dijelaskan.

Aturan rekomendasi di bawah adalah ATURAN SEDERHANA UNTUK PROTOTIPE (placeholder).
Di produksi, aturan ini ditentukan Product bersama Data & Analytics.
"""


def has_consent(profile):
    return bool(profile.get("consent", {}).get("granted"))


def quota_state(quota):
    """'depleted' = kuota habis, 'fup' = masih ada kuota tapi dibatasi FUP, 'ok' = normal."""
    if quota["remaining_mb"] <= 0:
        return "depleted"
    if quota["fup_active"]:
        return "fup"
    return "ok"


def price_per_gb(offer):
    return offer["price_idr"] / (offer["quota_mb"] / 1024)


def affordable(offers, balance):
    """Paket yang harganya tidak melebihi pulsa."""
    return [o for o in offers if o["price_idr"] <= balance]


def within_limit(offers, limit):
    """Paket yang harganya masuk limit Paket Darurat."""
    return [o for o in offers if o["price_idr"] <= limit]


def recommend(offers):
    """Rekomendasi = paket paling hemat per GB dari daftar yang diberikan."""
    return min(offers, key=price_per_gb) if offers else None


def cheapest(offers):
    return min(offers, key=lambda o: o["price_idr"])


def network_degraded(network):
    return network.get("status") == "degraded"
