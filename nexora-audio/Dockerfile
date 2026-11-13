# nexora-audio WebSocket bridge (Linux x86_64).
# Debian bookworm has glibc 2.36, which the bundled DeepFilterNet3 library needs (>= 2.35).
# Build:  docker build -t nexora-bridge .
# Run:    docker run -p 8765:8765 nexora-bridge --agent ws://your-agent:9000/agent
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY examples/websocket_bridge.py ./bridge.py
RUN pip install --no-cache-dir ".[server]"

EXPOSE 8765
ENTRYPOINT ["python", "bridge.py", "--host", "0.0.0.0", "--port", "8765"]
