"""Transaction control shared by every repository.

By default each repository owns its own transaction: one call, one `COMMIT`. That keeps
single-write use cases simple, but it means a use case making several writes has no way to
make them one unit — which is how `enqueue_ingestion` ended up committing the asset, then
the job, then deferring the queue row on a *separate* connection. A crash in either gap
left an asset stuck in `queued` with no job to run it: the classic dual-write problem.

`unit_of_work(db)` closes that. Inside it, every `commit_or_flush` becomes a `flush` — the
writes are visible to the rest of the transaction but not yet durable — and the single
`COMMIT` happens on clean exit. Because Procrastinate's queue table lives in the *same*
Postgres database, the queue row can join that transaction too, so "asset exists" and "job
is queued" become one atomic fact. That is the headline advantage of a Postgres-backed
queue over Redis/RabbitMQ, where the same guarantee needs a Transactional Outbox.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.orm import Session

# Stored on `Session.info` rather than a contextvar: the scope we mean is exactly "this
# Session", and a session is already the thing being passed around. A contextvar would also
# leak across the anyio threadpool hops that sync routes and streaming generators make.
_FLAG = "kb_in_unit_of_work"


def in_unit_of_work(db: Session) -> bool:
    return bool(db.info.get(_FLAG))


def commit_or_flush(db: Session) -> None:
    """Commit, unless a `unit_of_work` is in charge — then just flush.

    Every repository's `_commit()` delegates here, so wrapping a use case in
    `unit_of_work` is enough to make its writes atomic without touching the repositories.
    """
    if in_unit_of_work(db):
        # Send the SQL so later statements in the same transaction see the rows (and so
        # constraint violations surface here, at the offending write), but leave durability
        # to the enclosing unit of work.
        db.flush()
        return
    try:
        db.commit()
    except Exception:
        # A failed flush leaves the Session transaction unusable until it is rolled back.
        db.rollback()
        raise


@contextmanager
def unit_of_work(db: Session) -> Iterator[None]:
    """Run a block of repository writes as ONE transaction.

    Re-entrant: a nested call joins the outer unit rather than committing early, so a
    use case can call another without either having to know.
    """
    if in_unit_of_work(db):
        yield
        return

    db.info[_FLAG] = True
    try:
        yield
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.info.pop(_FLAG, None)


class SessionAtomicScope:
    """`IAtomicScope` implementation over a SQLAlchemy `Session`.

    Exists so the application layer can say "these writes are one transaction" without
    importing SQLAlchemy — the same reason `IUnitOfWork` exists for the auth service.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def atomic(self):
        return unit_of_work(self.db)
