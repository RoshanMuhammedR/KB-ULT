# DOCUMENT_PIPELINE.md

> How each source type moves through the pipeline: acquire → parse → chunk → embed →
> store → retrieve. Companion to [PROJECT_EXPLANATION.md](PROJECT_EXPLANATION.md); this
> note stays narrow and just follows the data.

---

## 0. The shape every source is forced into

Five very different inputs (PDF, Markdown, PPTX, audio, YouTube) all get funneled through
one pipeline because every handler (`ISourceHandler`) normalizes its source into the same
intermediate shape before anything downstream sees it:

```
KnowledgeAsset.documents: list[langchain_core.documents.Document]
```

Each `Document` is `{page_content: str, metadata: {"locator": {"type": ..., "value": ...}}}`.
The **locator** is the load-bearing concept in this whole system — it's what lets a chunk
answer "where did this come from, and how do I jump to it in the viewer." Every handler
emits one of four locator types:

| Source    | Locator type          | Example              |
|-----------|------------------------|-----------------------|
| PDF       | `page`                 | `{"type": "page", "value": 12}` |
| Markdown  | `section`               | `{"type": "section", "value": "Installation"}` |
| PPTX      | `slide`                 | `{"type": "slide", "value": 7}` |
| Audio     | `timestamp` (or `section` if untimed) | `{"type": "timestamp", "value": 184}` |
| YouTube   | `timestamp`             | `{"type": "timestamp", "value": 184}` |

Chunking, embedding, storage, and retrieval never branch on source type — they only ever
see `Document`s with a locator. Adding a new source type means writing a new handler, not
touching the rest of the pipeline. This dispatch is by `SourceType`, not file extension
([registry.py](apps/api/src/ingestion/registry.py)), so URL-based sources fit the same
lookup as uploaded files.

Everything below runs as one state machine per asset in
[`IngestionService._run_pipeline`](apps/api/src/application/ingestion/service.py#L261):
`extracting → chunking → embedding → persisting`, with per-step status written to the DB
so a crash mid-pipeline resumes from the failed step on retry rather than redoing
everything (e.g. a retry never re-transcribes audio if it already got past extraction).

---

## 1. Acquire + Parse (per source type)

Each handler implements `acquire()` (fetch raw bytes/content) and `parse()` (turn that
into `Document`s + a `text_content` blob used for full-text display).

### PDF — [pdf_handler.py](apps/api/src/ingestion/handlers/pdf_handler.py)
- `acquire`: re-downloads the original bytes from object storage (never passed through the
  queue payload — only the asset id is).
- `parse`: runs [`PyMuPDF4LLMAdapter`](apps/api/src/infrastructure/document_parsing/pymupdf_pdf.py),
  which uses PyMuPDF4LLM with `page_chunks=True` to get one dict per page and layout-aware
  markdown extraction — no OCR, no ML models, pure Python. One `Document` per **page**,
  locator `{"type": "page", "value": N}`. Title comes from PDF metadata, with a denylist for
  junk placeholder titles ("untitled", "document", etc.) falling back to the filename.

### Markdown — [markdown_handler.py](apps/api/src/ingestion/handlers/markdown_handler.py)
- `acquire`: re-reads the raw bytes; no parsing library needed.
- `parse`: regex-splits on ATX headings (`^#{1,6} ...`) only — Setext underlines are
  treated as plain text since they're rare and ambiguous to split on. One `Document` per
  **section**, heading line kept inside the body so a citation reads as a complete
  passage. Text before the first heading becomes an "Introduction" section. This is also
  the code path the app's "paste Markdown" UI uses — it just builds a `.md` File client-side
  and posts it through the normal upload endpoint.

### PPTX — [pptx_handler.py](apps/api/src/ingestion/handlers/pptx_handler.py)
- `acquire`: re-downloads the raw `.pptx` bytes.
- `parse`: `python-pptx` walks each slide's shapes for text-frame text, plus speaker notes
  (appended as `"Speaker notes: ..."` — decks often carry their real argument there). One
  `Document` per **slide**, locator `{"type": "slide", "value": N}`. Slide titles are also
  collected into `metadata["slides"]` so the UI can show deck structure without re-parsing.

### Audio — [audio_handler.py](apps/api/src/ingestion/handlers/audio_handler.py)
- `acquire`: downloads the file, sends it to a hosted transcription model
  ([`ITranscriber`](apps/api/src/infrastructure/ai_providers/transcription.py)). Slowest
  step in the whole pipeline by a wide margin (minutes, not seconds).
- `parse`: if the provider returns per-line timings, lines are coalesced into ~500-char
  windows via the shared [`coalesce_timed_lines`](apps/api/src/ingestion/handlers/_documents.py)
  helper, each window keeping its **first line's start time** as a `timestamp` locator. If
  only flat text comes back, it degrades honestly to `section` "Part N" locators plus
  `metadata["timestamps"] = "unavailable"` — the player then starts from 0:00 instead of
  seeking to a second it can't justify. A readable `transcript.md` is also written back to
  object storage next to the original (best-effort; failure to write it never fails
  ingestion, since the searchable text already lives in `documents`).

### YouTube — [youtube_handler.py](apps/api/src/ingestion/handlers/youtube_handler.py)
- `acquire`: no uploaded file — fetches the transcript live via `youtube-transcript-api`,
  preferring English but falling back to whatever language the video actually has (raw
  `.fetch()` defaults to English-only and would otherwise report "no transcript" for a
  Hindi-captioned video). One retry on `RequestBlocked`/`IpBlocked` (YouTube's bot-blocking
  is partly probabilistic); a title is best-effort fetched via oEmbed.
- `parse`: same `coalesce_timed_lines` helper as audio → `timestamp` locators. This is why
  the audio and YouTube handlers can't drift apart: they share one windowing function.

All four text-bearing handlers run output through
[`sanitize_text_for_storage`](apps/api/src/core/text.py) before it ever reaches a chunk,
embedding, or Postgres row.

---

## 2. Chunk — [chunker.py](apps/api/src/processing/chunking/chunker.py)

Source-agnostic by construction: `RecursiveKnowledgeAssetChunker.chunk()` never looks at
`source_type`, only at the `Document`s handlers already produced.

- Splitting is done by [`RecursiveSplitterAdapter`](apps/api/src/infrastructure/langchain_adapters/text_splitter.py),
  a thin wrapper over LangChain's `RecursiveCharacterTextSplitter.from_tiktoken_encoder`
  (`cl100k_base` encoding — i.e. chunk sizes are measured in **tokens**, not characters).
- Config ([config.py](apps/api/src/core/config.py)): `chunk_size_tokens = 800`,
  `chunk_overlap_tokens = 120`.
- Splitting **never crosses a `Document` boundary** — a PDF page's text is split within
  that page, never merged with the next page's. That's what guarantees a citation can
  never straddle two locators.
- Each split's parent `Document.metadata` (the locator) is copied onto every piece the
  splitter produces. Whitespace-only pieces are dropped so they don't burn an embedding
  call for nothing.
- Output is a flat `list[Chunk]`, each stamped with `chunk_index`, `filename`, `title`,
  `locator`, `source_type`, `knowledge_base_id`, `knowledge_asset_id` — everything the
  retrieval/citation path needs without a join back to the asset.

---

## 3. Embed

[`OpenAICompatibleEmbeddingsAdapter`](apps/api/src/infrastructure/langchain_adapters/embeddings.py)
wraps `langchain_openai.OpenAIEmbeddings` against an OpenAI-compatible gateway
(AICredits). `embed_texts()` batches all of an asset's chunk texts in one call at
ingestion time; `embed_query()` embeds a single query string at chat time. Same model both
sides, which is what makes cosine distance between them meaningful.

---

## 4. Store — [pgvector.py](apps/api/src/infrastructure/vector_store/pgvector.py)

`PgVectorStore.upsert_embeddings()` replaces all embedding rows for the asset's chunks in
one shot (`replace_for_chunks`) — a re-ingest (new version) doesn't leave orphaned vectors
from the previous version around; superseded-version rows are excluded from search
entirely (see the `superseded_at IS NULL` filter below), not just deprioritized.

Two indexes exist on the same `chunks`/`embeddings` tables and back the two retrieval
arms:
- an **HNSW** index over the embedding vector column (dense/cosine search)
- a **GIN** index over `chunks.fts`, a generated `tsvector` column (lexical search)

---

## 5. Retrieve — [retriever.py](apps/api/src/retrieval/retriever.py)

Triggered from chat ([`chat/service.py`](apps/api/src/application/chat/service.py#L123)):
the user's question (with the *previous* question prepended for elliptical follow-ups
like "what about the second one?") is embedded once, then handed to `Retriever.retrieve()`.

Two arms run over the same candidate pool, both scoped to `knowledge_base_id` and to
`status == READY` / `superseded_at IS NULL` chunks only:

1. **Dense** — cosine distance between the query embedding and every chunk's embedding
   (`EmbeddingModel.vector.cosine_distance`), ordered nearest-first, filtered by
   `retrieval_score_threshold = 0.25` (applied to the *candidate pool*, not the final
   top-k — a marginal match just loses its slot to the next candidate rather than
   truncating the list early).
2. **Lexical** — Postgres full-text search: `websearch_to_tsquery('english', query)` against
   `chunks.fts`, ranked by `ts_rank_cd`. This is the arm that catches an exact error code,
   config key, or proper noun that embeddings tend to blur. `websearch_to_tsquery` ANDs
   terms and understands quoted phrases, so a long conversational question often matches
   nothing here — that's intentional; when it has nothing to say, the dense arm carries
   the query alone. This query also carries the *same* score column (`1 - cosine_distance`)
   as the dense arm even though it isn't used for ordering, so a lexical-only hit still has
   a comparable relevance score downstream (e.g. for the citation UI).

Both arms **over-fetch**: `limit = top_k * retrieval_candidate_multiplier` (6), so the
threshold has a real pool to filter and a chunk ranked 12th by one arm but 3rd by the
other still has a chance to be promoted by fusion.

The two rankings are combined with **Reciprocal Rank Fusion**
([fusion.py](apps/api/src/retrieval/fusion.py)):

```
score(chunk) = Σ_arms  weight_arm / (k + rank_in_arm)     k = 60, weights = [1.0, 1.0]
```

RRF is used specifically because dense and lexical scores live on incomparable scales
(cosine similarity vs. `ts_rank_cd`) — averaging them would need an arbitrary
normalization step. RRF discards the scores and fuses by rank instead, so a chunk found by
*both* arms outranks one found brilliantly by only one. Ties break deterministically (best
single-arm rank, then first-seen order), which matters for debugging why a passage was or
wasn't retrieved. If the lexical arm returns nothing (empty query text, or no term match),
fusion is skipped entirely and the dense ordering is returned as-is.

Final output: `top_k = 5` `RetrievalResult`s (chunk + parent asset + score), which
`chat/service.py` hands to the prompt builder to build the LLM's context, each result's
`locator` carrying straight through to the citation the UI renders and can jump to
(page/slide/timestamp/section).

---

## 6. End-to-end example (PDF)

```
upload .pdf
  → PdfSourceHandler.acquire()      raw bytes from object storage
  → PdfSourceHandler.parse()        PyMuPDF4LLM → 1 Document/page, locator={"page": N}
  → RecursiveKnowledgeAssetChunker  ~800-token chunks, 120-token overlap, locator copied down
  → OpenAICompatibleEmbeddingsAdapter.embed_texts()   1 vector per chunk
  → PgVectorStore.upsert_embeddings()                 rows in embeddings + chunks.fts (generated)
  ...later, at chat time...
  → embed_query(question)
  → Retriever.retrieve(): dense (HNSW/cosine) + lexical (GIN/ts_rank_cd) → RRF fuse → top 5
  → prompt_builder.build(question, results) → LLM stream → citations back to page N
```

Swap the handler and locator type and the same six steps describe every other source.
