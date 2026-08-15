"""hybrid retrieval — a working vector index, plus a lexical one

Revision ID: 0004_hybrid_retrieval
Revises: 0003_google_identity
Create Date: 2026-08-15

Two independent fixes to retrieval quality.

**1. The vector index was never trained.** `ix_embeddings_vector` was created as IVFFlat in
0001, during the very first migration, on an empty `embeddings` table. IVFFlat derives its
100 centroids by k-means over existing rows — with zero rows there is nothing to cluster, so
the centroids were meaningless and stayed that way. It never errored; it just silently
returned worse neighbours.

HNSW is preferred because it builds its graph incrementally as rows arrive, so this failure
mode cannot happen again by construction: there is no training step to get wrong.

HNSW needs pgvector >= 0.5.0, and this app's production database is a *shared* Postgres that
this repo does not control. Rather than hard-fail a deploy on an environment difference, the
upgrade tries HNSW and falls back to rebuilding IVFFlat. The fallback is still a real fix:
the rebuild now runs against a populated table, so the centroids are finally derived from
actual data.

**2. Nothing lexical was searched.** Error codes, config keys and rare proper nouns are
exactly the tokens embeddings handle worst, so a chunk could contain the literal string a
user searched for and never be retrieved. `chunks.fts` plus a GIN index gives the retriever a
second, keyword-based way in.

The column is GENERATED ALWAYS ... STORED, so Postgres maintains it on every insert and
update. The ingestion pipeline needs no change at all, and this migration backfills every
existing row as part of the ALTER.
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_hybrid_retrieval"
down_revision = "0003_google_identity"
branch_labels = None
depends_on = None

# Graph-build parameters. m=16 / ef_construction=64 are pgvector's own defaults: good recall
# without a build time that would make this migration feel hung on a populated table.
_HNSW_M = 16
_HNSW_EF_CONSTRUCTION = 64

# 'english' (not 'simple') so search matches across word forms — "retrieving" finds
# "retrieval". The two-argument form also matters technically: to_tsvector is only IMMUTABLE
# when the config is given explicitly, and a generated column requires an immutable
# expression.
_FTS_EXPRESSION = "to_tsvector('english', text)"


def upgrade() -> None:
    # --- 1. Replace the untrained IVFFlat index ---------------------------------------
    op.drop_index("ix_embeddings_vector", table_name="embeddings")

    connection = op.get_bind()
    try:
        # SAVEPOINT: if `hnsw` is unavailable the CREATE aborts the surrounding
        # transaction, and without a nested one the whole migration would be unrecoverable.
        with connection.begin_nested():
            connection.execute(
                sa.text(
                    "CREATE INDEX ix_embeddings_vector ON embeddings "
                    "USING hnsw (vector vector_cosine_ops) "
                    f"WITH (m = {_HNSW_M}, ef_construction = {_HNSW_EF_CONSTRUCTION})"
                )
            )
        print("0004: created HNSW index on embeddings.vector")
    except Exception as exc:  # noqa: BLE001 - pgvector < 0.5 has no hnsw access method
        print(f"0004: HNSW unavailable ({exc.__class__.__name__}); rebuilding IVFFlat instead")
        # Still an improvement over the 0001 state: built against real rows, so the
        # centroids mean something, and enough probes to actually search them.
        connection.execute(
            sa.text(
                "CREATE INDEX ix_embeddings_vector ON embeddings "
                "USING ivfflat (vector vector_cosine_ops) WITH (lists = 100)"
            )
        )

    # --- 2. Lexical search column + index ----------------------------------------------
    # Rewrites the table to backfill, which is seconds at this scale.
    op.execute(
        f"ALTER TABLE chunks ADD COLUMN fts tsvector "
        f"GENERATED ALWAYS AS ({_FTS_EXPRESSION}) STORED"
    )
    op.execute("CREATE INDEX ix_chunks_fts ON chunks USING GIN (fts)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunks_fts")
    op.drop_column("chunks", "fts")

    # Back to exactly what 0001 created — including its flaw, since that is what "downgrade"
    # means here.
    op.drop_index("ix_embeddings_vector", table_name="embeddings")
    op.create_index(
        "ix_embeddings_vector",
        "embeddings",
        ["vector"],
        postgresql_using="ivfflat",
        postgresql_with={"lists": 100},
        postgresql_ops={"vector": "vector_cosine_ops"},
    )
