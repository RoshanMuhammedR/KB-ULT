from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Protocol


class IAtomicScope(Protocol):
    """Port for grouping several repository writes into one transaction.

    The sibling of `IUnitOfWork` (which exposes commit/rollback directly, as the auth
    service needs). This one hands back an async context manager, so a use case can
    express "all of this, or none of it" without knowing whether the store underneath is
    SQLAlchemy, and without any repository having to change how it writes.
    """

    def atomic(self) -> AbstractAsyncContextManager[None]:
        """Open a transaction that spans every write made inside the block."""
        ...
