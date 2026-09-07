from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(slots=True)
class ChunkSignal:
    """What one passage has done for this workspace, accumulated across every answer.

    Five counters, only four of which influence anything. `cited` is recorded and never fed
    into the relevance prior: being retrieved and cited is precisely what the prior
    influences, so letting it feed back would make the loop self-reinforcing with no signal
    from outside it — the passage that got picked would get picked harder, forever, whether
    or not it was any good. It survives as the denominator that makes the others readable
    ("supported 3 times out of 40 citations" is a very different passage from "3 out of 3").

    `supported` and `unsupported` come from the grounding checker; `upvoted` and `downvoted`
    come from a human. The human numbers are weighted higher because they are the only
    evidence in the system that does not originate from a model judging its own work.
    """

    chunk_id: UUID
    cited: int = 0
    supported: int = 0
    unsupported: int = 0
    upvoted: int = 0
    downvoted: int = 0
    last_cited_at: datetime | None = None


@dataclass(slots=True)
class ChunkSignalEvent:
    """One passage's outcome in one answer, ready to be folded into its counters.

    Deltas rather than absolute values, so recording is an increment the database can apply
    under `ON CONFLICT` without reading the current row first.
    """

    chunk_id: UUID
    cited: int = 0
    supported: int = 0
    unsupported: int = 0
