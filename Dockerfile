# Image prototipe Asisten Kuota. Hanya butuh Python (tanpa paket tambahan).
# Diuji di Python 3.11-3.13; 3.12 dipilih sebagai tengah-tengahnya.
FROM python:3.12-slim

# - output langsung tampil di `docker logs`
# - tidak membuat file .pyc
# - BIND_HOST=0.0.0.0: di dalam container server harus mendengarkan semua alamat supaya port bisa
#   dipublikasikan. Pembatasan akses ke host diatur saat publish port (lihat docker-compose.yml).
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    BIND_HOST=0.0.0.0

# Jalan sebagai user biasa, bukan root
RUN useradd --create-home --uid 10001 app

WORKDIR /app
COPY --chown=app:app . .

# Folder log harus milik user app supaya bisa ditulis (volume baru mewarisi kepemilikan ini)
RUN mkdir -p /app/logs && chown app:app /app/logs

USER app
EXPOSE 8000 8001

# Sehat bila halaman daftar pelanggan bisa dibuka
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/customers', timeout=2)"

CMD ["python", "run.py"]
