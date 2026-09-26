# botc-automod in a container. Build: docker build -t botc-automod .
FROM python:3.12-slim

# libgomp1: needed by the llama.cpp CPU build if the packaged Artist model is used.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.12.7 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --extra cloud --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev --extra cloud

# Games, karma, settings and downloaded models all live in /data.
ENV BOTC_DATA=/data XDG_CONFIG_HOME=/data/config PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1
VOLUME /data
EXPOSE 8000
CMD ["botc-automod", "--host", "0.0.0.0", "--port", "8000"]
