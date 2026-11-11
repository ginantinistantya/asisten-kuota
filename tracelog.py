"""
TRACE / LOG setiap langkah agen + MASKING data pribadi.

Aturan: apa pun yang ditulis ke log WAJIB lewat mask() dulu (syarat UU PDP: data pribadi
di-mask di log). Contoh nomor 081200000001 -> 0812****0001.

Setiap baris log berisi: waktu, conversation_id, nomor langkah, siapa (actor), kejadian (event),
dan detail. Disimpan di memori (untuk panel trace di UI) dan ke file logs/trace.jsonl.
"""
import json
import os
import re
import threading
import time

NUMBER = re.compile(r"\b\d{9,14}\b")                        # nomor telepon / angka panjang
EMAIL = re.compile(r"[\w.+-]+@([\w-]+\.[\w.]+)")
PII_KEYS = {"name", "email"}                                # field yang selalu disembunyikan penuh


def mask_number(number):
    s = str(number)
    return s[:4] + "****" + s[-4:] if len(s) >= 9 else "****"


def mask_text(text):
    text = NUMBER.sub(lambda m: mask_number(m.group()), text)
    return EMAIL.sub(lambda m: "***@" + m.group(1), text)


def mask(value):
    """Mask rekursif untuk dict / list / string."""
    if isinstance(value, dict):
        return {k: "***" if k in PII_KEYS else mask(v) for k, v in value.items()}
    if isinstance(value, list):
        return [mask(v) for v in value]
    if isinstance(value, str):
        return mask_text(value)
    return value


class Trace:
    def __init__(self, path=None):
        self.path = path
        self.entries = {}           # conversation_id -> daftar baris log
        self.lock = threading.Lock()
        if path:
            os.makedirs(os.path.dirname(path), exist_ok=True)

    def log(self, conv_id, actor, event, **details):
        with self.lock:
            rows = self.entries.setdefault(conv_id, [])
            row = {"time": time.strftime("%H:%M:%S"), "conversation_id": conv_id,
                   "step": len(rows) + 1, "actor": actor, "event": event, "details": mask(details)}
            rows.append(row)
            if self.path:
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def get(self, conv_id):
        with self.lock:
            return list(self.entries.get(conv_id, []))
