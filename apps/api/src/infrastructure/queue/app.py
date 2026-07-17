from __future__ import annotations

from procrastinate import App, PsycopgConnector

from src.core.config import get_settings


def _libpq_dsn(sqlalchemy_url: str) -> str:
    # SQLAlchemy uses a driver-qualified URL ("postgresql+psycopg://..."), but the
    # Procrastinate psycopg connector wants a plain libpq DSN ("postgresql://...").
    # Strip the "+psycopg" driver suffix so the same DATABASE_URL feeds both.
    return sqlalchemy_url.replace("+psycopg", "", 1)


# The Procrastinate application: its broker IS our existing Postgres, so there is no
# extra infrastructure to run. `import_paths` tells the `procrastinate worker` CLI
# which module to import so the @app.task definitions register themselves. It is
# imported lazily at worker startup, which avoids an import cycle with the tasks
# module (tasks -> composition -> queue adapter -> tasks).
app = App(
    connector=PsycopgConnector(conninfo=_libpq_dsn(get_settings().database_url)),
    import_paths=["src.infrastructure.queue.tasks"],
)
