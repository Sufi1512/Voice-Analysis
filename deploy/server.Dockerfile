# Nexora Voice Cloud server image (Linux x86_64).
# Build from the repository root:
#   docker build -f deploy/server.Dockerfile -t nexora-server .
# Debian bookworm (glibc 2.36) satisfies the bundled DeepFilterNet3 library (needs >= 2.35).
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 PIP_NO_CACHE_DIR=1
RUN useradd --create-home --uid 10001 nexora
WORKDIR /opt/nexora

COPY nexora-audio /opt/nexora/nexora-audio
COPY nexora-server /opt/nexora/nexora-server
RUN pip install ./nexora-audio "./nexora-server[postgres,redis]" \
 && rm -rf /opt/nexora/nexora-audio/tests /opt/nexora/nexora-server/tests

USER nexora
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=60s CMD \
  python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz').status==200 else 1)"
ENTRYPOINT ["nexora-server", "--host", "0.0.0.0", "--port", "8080"]
