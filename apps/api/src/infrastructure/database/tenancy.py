"""Query-level tenant isolation — the SQLAlchemy equivalent of a Prisma client
extension.

Every table that carries `tenant_id`/`user_id` mixes in :class:`TenantScoped`. Two
session-level listeners then do the work automatically, so no repository ever has to
remember to pass a tenant:

  * ``do_orm_execute`` appends a ``with_loader_criteria`` filter to every SELECT/UPDATE/
    DELETE that touches a ``TenantScoped`` entity — including relationship and eager
    loads — so reads and bulk writes only ever see the current tenant's rows.
  * ``before_flush`` stamps ``tenant_id``/``user_id`` onto newly-added ``TenantScoped``
    objects, so INSERTs are attributed to the current tenant without callers setting it.

**Fail-closed:** the filter/stamp reads the current tenant from the contextvar in
``core.tenant_context``; if none is set, :class:`MissingTenantContextError` is raised
rather than running unscoped. Work that legitimately spans tenants or precedes auth wraps
itself in ``system_scope``, which suspends both listeners.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, event
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, with_loader_criteria

from src.core.tenant_context import (
    current_tenant_id,
    current_user_id,
    in_system_scope,
    try_current_tenant_id,
)


class TenantScoped:
    """Adds `tenant_id` + `user_id` to a model and opts it into auto-filtering.

    Both are stored on **every** domain table (not derived through a join) so the
    per-table filter and the RLS policy can each key on the row's own `tenant_id`.
    `user_id` is stored independently of `tenant_id` now (one user per tenant today)
    so growing to multiple users per tenant needs no migration on domain tables.
    """

    @declared_attr
    def tenant_id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(
            PGUUID(as_uuid=True),
            ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )

    @declared_attr
    def user_id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(
            PGUUID(as_uuid=True),
            ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )


def _touches_tenant_scoped(state) -> bool:
    # True only when a TenantScoped entity is referenced by the statement, so plain
    # queries on non-scoped tables (tenants, users, refresh_tokens, health) are left alone
    # and never trip the fail-closed check.
    return any(issubclass(mapper.class_, TenantScoped) for mapper in state.all_mappers)


def _on_do_orm_execute(state) -> None:
    # Skip internal column/relationship refreshes (they re-load already-scoped rows) and
    # anything that isn't a SELECT/UPDATE/DELETE. In system scope we add nothing.
    if state.is_column_load or state.is_relationship_load:
        return
    if not (state.is_select or state.is_update or state.is_delete):
        return
    if in_system_scope() or not _touches_tenant_scoped(state):
        return
    # Resolve the tenant OUTSIDE the lambda (fail closed if unset) and close over the value
    # — the SQLAlchemy lambda cache extracts it as a bound parameter but forbids calling
    # functions inside the lambda itself.
    tenant_id = current_tenant_id()
    state.statement = state.statement.options(
        with_loader_criteria(
            TenantScoped, lambda cls: cls.tenant_id == tenant_id, include_aliases=True
        )
    )


def _on_before_flush(session, _flush_context, _instances) -> None:
    if in_system_scope():
        return
    for obj in session.new:
        if not isinstance(obj, TenantScoped):
            continue
        if getattr(obj, "tenant_id", None) is None:
            obj.tenant_id = current_tenant_id()
        if getattr(obj, "user_id", None) is None:
            obj.user_id = current_user_id()


def _on_after_begin(session, transaction, connection) -> None:
    # Set the transaction-local GUCs the Postgres RLS policies read (the DB backstop that
    # composes with the ORM filter above — same source of truth, the tenant context).
    # System scope -> bypass; a tenant in context -> scope to it; nothing set -> leave the
    # GUC unset so RLS returns zero rows (fail closed at the database).
    #
    # SET does not take bind params, so we use set_config(..., is_local => true), which is
    # transaction-scoped and therefore safe under connection pooling.
    if in_system_scope():
        connection.exec_driver_sql("SELECT set_config('app.tenant_bypass', 'on', true)")
        return
    tenant_id = try_current_tenant_id()
    if tenant_id is not None:
        connection.exec_driver_sql(
            "SELECT set_config('app.current_tenant', %s, true)", (str(tenant_id),)
        )


def register_tenant_guards(session_factory) -> None:
    """Attach the filter + stamp + RLS-GUC listeners to a sessionmaker.

    Registered once against the shared ``SessionLocal`` so both the HTTP path and the
    worker path enforce isolation identically. Idempotent.
    """
    if not event.contains(session_factory, "do_orm_execute", _on_do_orm_execute):
        event.listen(session_factory, "do_orm_execute", _on_do_orm_execute)
    if not event.contains(session_factory, "before_flush", _on_before_flush):
        event.listen(session_factory, "before_flush", _on_before_flush)
    if not event.contains(session_factory, "after_begin", _on_after_begin):
        event.listen(session_factory, "after_begin", _on_after_begin)
