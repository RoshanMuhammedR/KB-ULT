# Production image for the API and the ingestion worker — one image, two commands.
#
# Two stages: the builder compiles wheels (docling and friends need a C toolchain), the
# runtime carries only the installed packages, so the shipped layer has no compilers in it.
FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
  && apt-get install -y --no-install-recommends build-essential \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /build
# Dependencies resolve from pyproject alone, so this layer is cached until it changes.
COPY pyproject.toml ./
RUN mkdir -p src && touch src/__init__.py \
  && pip install --prefix=/install .


FROM python:3.12-slim AS runtime

# /app MUST come before site-packages. The builder installs the project itself, which
# includes a stub `src` package; a console script like `procrastinate` puts its own bin
# directory on sys.path rather than the cwd, so without /app first that empty stub shadows
# the real source and the worker dies with ModuleNotFoundError on src.infrastructure.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/install/bin:$PATH" \
    PYTHONPATH=/app:/install/lib/python3.12/site-packages

# curl is used by the container healthcheck below.
RUN apt-get update \
  && apt-get install -y --no-install-recommends curl \
  && rm -rf /var/lib/apt/lists/* \
  && useradd --create-home --uid 10001 app

COPY --from=builder /install /install

WORKDIR /app
COPY --chown=app:app . .
# Committed from Windows, the exec bit does not survive; set it here rather than relying on
# git's index (belt and braces with .gitattributes).
RUN chmod +x /app/docker-entrypoint.sh

# Docling and tiktoken cache models under $HOME; give them a writable one.
ENV HOME=/home/app
USER app

EXPOSE 8000

# 127.0.0.1, never localhost: inside a container localhost can resolve to ::1 first, and a
# server bound to IPv4 only then fails every probe while serving traffic perfectly.
HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=5 \
  CMD curl -fsS http://127.0.0.1:8000/health || exit 1

# Invoked through `sh` so it works even when /app is bind-mounted from a host that does not
# carry a Unix exec bit (Windows dev machines).
ENTRYPOINT ["sh", "/app/docker-entrypoint.sh"]
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
