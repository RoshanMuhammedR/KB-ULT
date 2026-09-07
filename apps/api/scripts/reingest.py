"""Re-run ingestion for existing sources, so they gain the chunk hierarchy.

Migration 0009 adds `parent_id`, `embed_text` and `modality` to chunks, and no backfill can
populate them: nothing can invent the section a chunk was split out of after the fact.
Existing rows keep NULLs and behave exactly as they did before — retrievable, citable, just
without parent expansion or contextual embedding. This script is how they catch up.

Re-ingestion is safe to run repeatedly. The pipeline replaces an asset's chunks and
embeddings wholesale rather than appending, so the worst case is time and a few embedding
calls.

    python scripts/reingest.py --tenant <uuid> --user <uuid> --dry-run
    python scripts/reingest.py --tenant <uuid> --user <uuid>
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.event_loop import configure_event_loop  # noqa: E402

configure_event_loop()

from sqlalchemy import select  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.core.tenant_context import reset_tenant_context, set_tenant_context  # noqa: E402
from src.domain.entities import AssetStatus  # noqa: E402
from src.infrastructure.database.models import ChunkModel, KnowledgeAssetModel  # noqa: E402
from src.infrastructure.database.session import engine, session_scope  # noqa: E402


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument(
        "--all",
        action="store_true",
        help="Re-ingest every source, not only the ones with no chunk hierarchy",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    tokens = set_tenant_context(UUID(args.tenant), UUID(args.user))
    try:
        async with session_scope() as db:
            # Current sources only — a superseded version is not worth re-embedding.
            #
            # Not filtered to READY. An asset stranded mid-pipeline (a worker died somewhere
            # its except-block could not recover from, so nothing marked it FAILED) would be
            # invisible here and unreachable everywhere else. `service.reingest` is the one
            # that decides: it queues a stranded asset and refuses one genuinely in flight.
            # FAILED is excluded because `retry` owns it.
            assets = (
                await db.scalars(
                    select(KnowledgeAssetModel)
                    .where(KnowledgeAssetModel.superseded_at.is_(None))
                    .where(KnowledgeAssetModel.status != AssetStatus.FAILED.value)
                    .order_by(KnowledgeAssetModel.created_at)
                )
            ).all()

            stale: list[KnowledgeAssetModel] = []
            for asset in assets:
                if args.all:
                    stale.append(asset)
                    continue
                # "Has no parents" is the marker of a pre-0009 asset: the new chunker always
                # emits at least one parent section per source document.
                parents = (
                    await db.scalars(
                        select(ChunkModel.id)
                        .where(ChunkModel.knowledge_asset_id == asset.id)
                        .where(ChunkModel.parent_id.is_not(None))
                        .limit(1)
                    )
                ).all()
                if not parents:
                    stale.append(asset)

            print(f"{len(assets)} current sources, {len(stale)} to re-ingest")
            for asset in stale:
                print(f"  {asset.id}  {asset.filename}")

            if args.dry_run or not stale:
                return 0

            from src.composition import build_ingestion_service

            service = build_ingestion_service(db, get_settings())
            queued = 0
            for asset in stale:
                # `reingest`, not `retry`. `retry` guards on `status == FAILED` and returns
                # silently for anything else, so calling it here queued nothing at all while
                # this script cheerfully reported success — which is how a broken re-ingest
                # went unnoticed. It is queued rather than run inline because the worker owns
                # the pipeline, the job record and the retry policy.
                if await service.reingest(asset.id):
                    queued += 1
                    print(f"  queued {asset.filename}")
                else:
                    print(f"  SKIPPED {asset.filename} (not ready — already in flight?)")

        # Report what actually happened. Anything else here is how the last bug hid.
        print(f"\nQueued {queued} of {len(stale)} sources. Watch progress with GET /jobs.")
        return 0 if queued == len(stale) else 1
    finally:
        reset_tenant_context(tokens)
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
