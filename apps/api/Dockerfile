# Shared image for both the api and the worker (see docker-compose.yml `command:` override).
FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/app/.venv
COPY pyproject.toml uv.lock ./
# The committed uv.lock predates the [tool.uv.sources]/[[tool.uv.index]] overrides below (pin
# torch/torchvision to the CPU wheel index, swap opencv-python for the headless build) - `uv
# sync` alone treats that lock as still fresh since the dependency *specifiers* didn't change,
# only the resolution source, and happily reuses it. That shipped a CUDA-bundled torch (~18GB
# image, killed the VPS's disk on pull) instead of the CPU one. Force a real re-resolution.
RUN uv lock
RUN uv sync --no-dev --no-install-project
COPY src src
COPY alembic alembic
COPY alembic.ini .
RUN uv sync --no-dev

FROM python:3.12-slim
RUN groupadd -r app && useradd -r -g app app
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY --from=build /app/src /app/src
COPY --from=build /app/alembic /app/alembic
COPY --from=build /app/alembic.ini /app/alembic.ini
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh && mkdir -p /models && chown -R app:app /app /models
ENV PATH="/app/.venv/bin:$PATH" \
    OMP_NUM_THREADS=2 \
    MKL_NUM_THREADS=2
USER app
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
