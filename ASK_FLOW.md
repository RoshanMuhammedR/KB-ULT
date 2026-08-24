# How a question becomes an answer

A complete walkthrough of one request: from the moment someone types into the composer to the
moment the last word of the answer lands on screen, with the real code at every step.

Read it top to bottom and you will have followed a single question through **11 stages**, four
processes (browser → FastAPI → Postgres → LLM gateway), and back.

---

## The 30-second version

```
Browser                          FastAPI                     Postgres              AI gateway
   │
   │ 1. POST /conversations/new/messages  {question}
   │─────────────────────────────────────►
   │                                 2. open own DB session
   │                                 3. resolve/create thread ──────►
   │ ◄── event: conversation {id,title}
   │                                 4. read last 4 messages ───────►
   │                                 5. embed the question ─────────────────────────►
   │                                 6a. dense search (vector) ─────►
   │                                 6b. lexical search (tsquery) ──►
   │                                 7. fuse both rankings (RRF)
   │                                 8. build the prompt
   │                                 9. stream the completion ──────────────────────►
   │ ◄── event: delta "The"  ◄───────────────────────────────────────────────────────
   │ ◄── event: delta " report"
   │ ◄── event: delta " says…"
   │ ◄── event: citations [...]
   │                                10. persist question + answer ──►
   │ ◄── event: done {ids}
```

Everything after stage 1 happens inside **one HTTP response that stays open**. That is the
whole trick: the answer is written to the socket as the model produces it, so the user reads
along instead of watching a spinner.

---

## Stage 1 — The composer hands off

`apps/web/src/components/saga/chat.tsx` — a plain form. The only notable thing is
`disabled={busy}`, which stops a second question being sent while one is still streaming.

```tsx
<Composer onSend={(question) => void ask(question)} disabled={busy} />
```

## Stage 2 — Optimistic UI: both bubbles appear instantly

`apps/web/src/lib/use-ask.ts`. Before any network call, **two** messages are pushed into local
state — the user's question and an *empty* assistant bubble. The empty one is the thing the
streaming tokens will be poured into.

```ts
const userId = localId("user");            // temporary client-side ids…
const assistantId = localId("assistant");  // …swapped for real ones when the server replies

setConversation((current) => ({
  ...current,
  messages: [...current.messages, userMessage, assistantMessage]
}));
setStreamingId(assistantId);               // drives the "…" cursor

const controller = new AbortController();  // so navigating away cancels the request
abort.current = controller;
```

## Stage 3 — The SSE request

`apps/web/src/lib/api.ts`. Note this is **not** `EventSource` — that only does GET, and we need
to POST a body. So it is a normal `fetch` whose response body is read as a stream.

```ts
const response = await fetch(`${API_URL}/conversations/${target}/messages`, {
  method: "POST",
  headers,                       // Authorization: Bearer …, Accept: text/event-stream
  body: JSON.stringify({ question }),
  cache: "no-store",
  signal
});

const reader = response.body.getReader();
const decoder = new TextDecoder();
let buffer = "";

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");

  const frames = buffer.split("\n\n");   // SSE frames are separated by a blank line
  buffer = frames.pop() ?? "";           // the last piece is probably incomplete — keep it
  for (const frame of frames) dispatchFrame(frame, handlers);
}
```

Three details that are easy to get wrong:

- **`{ stream: true }`** — a UTF-8 character can be split across two TCP packets. Without this
  flag, non-ASCII answers get a `�` at random chunk boundaries.
- **`frames.pop()`** — TCP gives you byte boundaries, not message boundaries. The tail is put
  back in the buffer and completed by the next read.
- **`\r\n` normalisation** — SSE permits CRLF; if a proxy rewrote line endings, splitting on
  `"\n\n"` would never match and the answer would silently arrive empty.

## Stage 4 — The endpoint returns a generator, not a response body

`apps/api/src/http/routes/conversations.py`. The handler is a plain `def`, so FastAPI runs it in
its threadpool (all the DB and HTTP work below is blocking).

```python
@router.post("/{conversation_id}/messages")
def ask_in_conversation(conversation_id, request, identity, settings) -> StreamingResponse:
    def events():
        with session_scope() as db:                       # its OWN session — see note below
            chat_service = build_chat_service(db, settings)
            try:
                for event, payload in chat_service.ask_stream(target, question):
                    yield _frame(event, payload)
            except Exception as exc:
                logger.exception("chat_stream_failed", error=str(exc))
                yield _frame("error", {"message": "The answer stopped partway through. …"})

    return StreamingResponse(events(), media_type="text/event-stream", headers=_SSE_HEADERS)


def _frame(event: str, payload: object) -> str:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"
```

**Why its own `session_scope()` and not the usual `Depends(get_db)`?** Since FastAPI 0.106, a
yield-dependency's cleanup runs *before* the response body is sent. A streaming generator using
that session would find it already closed halfway through the answer.

**Why no tenant-context binding here?** Starlette drives a *sync* generator through
`iterate_in_threadpool`, which runs every frame in a fresh `contextvars` copy. Binding at the
top and resetting in a `finally` therefore crosses a context boundary and raises — which used
to kill the connection after every successful answer. The middleware has already bound the
tenant, and each frame's context copy inherits it.

The headers matter too — without them a proxy will happily buffer the whole answer and hand it
over in one lump, defeating the point:

```python
_SSE_HEADERS = {"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}
```

## Stage 5 — Resolve the thread, and send its id back immediately

`apps/api/src/application/chat/service.py` — `ask_stream` is a generator, so each `yield` is a
frame on the wire.

```python
knowledge_base = self.kb_repo.ensure_default()
conversation = self._resolve_conversation(conversation_id, knowledge_base.id, question)
yield ("conversation", {"id": str(conversation.id), "title": conversation.title})
```

A new thread is titled from the question itself — no extra LLM call just to name it:

```python
return self.conversation_repo.create(
    Conversation(knowledge_base_id=knowledge_base_id, title=title_from_question(question))
)
```

The browser uses this first frame to swap the URL to `/app/c/<id>` **without a navigation**, so
the stream is not interrupted:

```ts
onConversation: (created) => {
  setConversation((c) => (c.id ? c : { ...c, id: created.id, title: created.title }));
  if (!conversationId) onCreated?.(created);   // → window.history.replaceState(...)
}
```

## Stage 6 — Read recent history

```python
history = self.conversation_repo.recent_messages(conversation.id, _HISTORY_TURNS)  # 4
```

Four messages is two exchanges — enough for "what about the second one?" without paying to
replay the whole thread on every question.

> **Nothing has been written to the database yet.** The question is *not* saved here. It is
> saved together with the answer at stage 10, so a failure anywhere in between leaves the
> thread untouched — which is what lets the error message honestly say "nothing was saved".

## Stage 7 — Embed the question

```python
query = question
previous = self._previous_question(history or [])
if previous:
    query = f"{previous}\n{question}"        # give an elliptical follow-up something to match

query_embedding = self.embedding_provider.embed_query(query)
```

A bare "what about the second one?" embeds to almost nothing on its own. Prepending the previous
question is a deliberately cheap stand-in for a proper LLM query-rewrite.

## Stage 8 — Search twice, in different ways

`apps/api/src/retrieval/retriever.py`. Two arms run over the same chunks:

```python
limit = top_k * self.candidate_multiplier          # over-fetch on purpose

dense   = self.vector_store.search_dense(query_embedding, kb_id, limit, threshold)
lexical = self.vector_store.search_lexical(query_embedding, query_text, kb_id, limit)
```

**Dense arm** — meaning. Cosine distance over pgvector; finds "revenue fell" when you asked
about "declining income":

```python
distance = EmbeddingModel.vector.cosine_distance(query_embedding)
rows = self.db.execute(
    self._ready_chunks_base(knowledge_base_id, distance).order_by(distance).limit(top_k)
).all()
```

**Lexical arm** — literal words. Postgres full-text search; finds the exact error code or
product name that embeddings blur away:

```python
tsquery = func.websearch_to_tsquery("english", query_text)
rows = self.db.execute(
    self._ready_chunks_base(knowledge_base_id, distance)
    .where(ChunkModel.fts.op("@@")(tsquery))
    .order_by(func.ts_rank_cd(ChunkModel.fts, tsquery).desc())
    .limit(top_k)
).all()
```

Two deliberate asymmetries:

- The lexical arm is **not** similarity-thresholded. A chunk holding the exact error code you
  searched for may score poorly on cosine and still be the right answer.
- `websearch_to_tsquery` **ANDs** the terms, so a long conversational question often matches
  nothing lexically. That is intended — this arm exists to catch exact identifiers, and when it
  has nothing to say it stays silent and the dense arm carries the query alone.

Both are plain ORM `select()`s, never raw SQL, because the tenant filter is injected by a
`do_orm_execute` listener that only fires for ORM statements. Raw SQL would silently escape it.

## Stage 9 — Fuse the two rankings

Two ranked lists, one answer. Reciprocal Rank Fusion combines them using only *positions*, which
sidesteps the fact that a cosine distance and a `ts_rank_cd` score are not comparable numbers:

```python
scores[item] = scores.get(item, 0.0) + weight / (k + rank)      # k = 60
```

A chunk ranked 12th by one arm and 3rd by the other is still visible to be promoted — which is
why both arms over-fetch rather than returning exactly `top_k`.

```python
fused_ids = reciprocal_rank_fusion(
    [[str(r.chunk.id) for r in dense], [str(r.chunk.id) for r in lexical]],
    k=self.rrf_k, weights=[_DENSE_WEIGHT, _LEXICAL_WEIGHT],
)
results = [by_id[chunk_id] for chunk_id in fused_ids[:top_k]]
```

**The escape hatch.** If too little was found, stop here and say so rather than letting the model
improvise:

```python
if len(results) < self.min_context_chunks:
    answer = self.prompt_builder.insufficient_context_answer()
    yield ("delta", answer)
    yield ("citations", citations)
    ...
    return
```

## Stage 10 — Build the prompt

`apps/api/src/application/chat/prompt_builder.py`. Each retrieved chunk becomes a numbered block
the model can cite by index:

```python
context_blocks.append(
    f"[{index}] source={source} at={position} score={result.score:.3f}\n{result.chunk.text}"
)

system_prompt = (
    "You answer questions only from the retrieved context. "
    "If the context does not contain the answer, say that the knowledge base "
    "does not contain enough information. Include concise citations using [n]. …"
)
```

History is passed as **prior turns**, not folded into the question, so the model can tell what
was asked before from what is being asked now.

## Stage 11 — Stream the completion

```python
pieces = []
for delta in self.llm_provider.stream(messages):
    pieces.append(delta)
    yield ("delta", delta)                 # ← straight out to the browser

answer = "".join(pieces).strip()
if not answer:
    raise RuntimeError("The model returned an empty answer")   # persist nothing
```

Underneath, LangChain's `ChatOpenAI` pointed at the gateway:

```python
self.client = ChatOpenAI(api_key=..., base_url=..., model=..., temperature=0,
                         timeout=90.0, max_retries=1)

for chunk in self.client.stream(self._convert(messages)):
    ...
    yield str(text)
```

The 90-second timeout is not cosmetic: a streaming answer holds a threadpool worker *and* an
open database session for its whole duration, and the library default is **600 seconds**.

### Then persist — question and answer together

```python
yield ("citations", citations)
user_message, assistant = self._persist_turn(conversation.id, question, answer, citations, ...)
yield ("done", self._done(user_message, assistant, insufficient=False))
```

```python
def _persist_turn(self, conversation_id, question, answer, citations, insufficient):
    user_message = self.conversation_repo.append_message(
        Message(conversation_id=conversation_id, role=MessageRole.USER, content=question)
    )
    assistant = self.conversation_repo.append_message(
        Message(conversation_id=conversation_id, role=MessageRole.ASSISTANT,
                content=answer, citations=citations, insufficient_context=insufficient)
    )
    return user_message, assistant
```

Writing both at the end is what makes the failure story honest. Saving the question up front
(the earlier design) meant every failed attempt left an orphan question that `recent_messages`
then fed into the *next* prompt — so pressing "Try again" made the prompt worse each time.

---

## Back on the client — frames become pixels

`dispatchFrame` parses each frame and calls a handler:

```ts
function dispatchFrame(frame, handlers) {
  let event = "message";
  const dataLines = [];
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  let payload;
  try { payload = JSON.parse(dataLines.join("\n")); }
  catch { return; }                    // a malformed frame is skipped, not fatal

  switch (event) {
    case "conversation": ...
    case "delta":     handlers.onDelta(payload); break;
    case "citations": handlers.onCitations(payload); break;
    case "done":      handlers.onDone(payload); break;
    case "error":     throw new ApiError(500, payload.message);
  }
}
```

Each `delta` is appended to a running string and patched into the assistant bubble:

```ts
onDelta: (delta) => { streamed += delta; patchAssistant({ content: streamed }); },
onCitations: (citations) => patchAssistant({ citations }),
onDone: (done) => patchAssistant({ id: done.message_id, insufficient_context: done.insufficient_context })
```

`onDone` swaps the temporary local id for the server's real one, so a later "delete this message"
addresses the right row.

**If anything throws**, both optimistic bubbles are removed — which is correct precisely because
the server now saves nothing on failure:

```ts
} catch (err) {
  if (controller.signal.aborted) return;      // navigated away; not an error worth showing
  setConversation((current) => ({
    ...current,
    messages: current.messages.filter((m) => m.id !== userId && m.id !== assistantId)
  }));
  setError(err instanceof Error ? err.message : "That question didn't get through.");
}
```

---

## The event contract, in one table

| Event | Payload | When | What the UI does |
| --- | --- | --- | --- |
| `conversation` | `{id, title}` | Immediately | Adopts the id; rewrites the URL without navigating |
| `delta` | `"…text…"` | Per model chunk | Appends to the assistant bubble |
| `citations` | `[{asset_id, chunk_id, locator, score, excerpt}, …]` | After generation | Renders citation cards |
| `done` | `{user_message_id, message_id, insufficient_context, created_at}` | Last | Swaps temp ids for real ones; clears the cursor |
| `error` | `{message}` | Instead of `done` | Removes both bubbles, shows the error card |

`conversation` is deliberately first: it means time-to-first-byte is a database insert, not an
LLM round-trip, so the UI commits to a thread long before the answer starts.

---

## What is slow, and what is fast

| Stage | Typical | Notes |
| --- | --- | --- |
| Resolve/create thread | ~5 ms | One insert |
| Recent messages | ~5 ms | Indexed, limit 4 |
| **Embed the question** | **~100–300 ms** | Network call to the gateway |
| Dense + lexical search | ~10–50 ms | Two indexed queries |
| RRF fusion | <1 ms | Pure Python over ~60 ids |
| **LLM time-to-first-token** | **~300–800 ms** | The wait the user actually feels |
| Streaming the rest | 1–10 s | But visibly progressing |
| Persist the turn | ~10 ms | Two inserts |

The only silent gap is between the `conversation` frame and the first `delta` — embedding plus
retrieval plus time-to-first-token. There is currently no heartbeat during that window, which is
the one thing an aggressive idle proxy could cut.

---

## Where each piece lives

| Concern | File |
| --- | --- |
| Composer / thread rendering | `apps/web/src/components/saga/chat.tsx` |
| Optimistic UI + streaming state | `apps/web/src/lib/use-ask.ts` |
| SSE reader, frame parsing | `apps/web/src/lib/api.ts` |
| HTTP endpoint, SSE framing | `apps/api/src/http/routes/conversations.py` |
| Orchestration (the generator) | `apps/api/src/application/chat/service.py` |
| Two-arm search | `apps/api/src/retrieval/retriever.py` |
| SQL for both arms | `apps/api/src/infrastructure/repositories/postgres_chunk_repository.py` |
| Rank fusion | `apps/api/src/retrieval/fusion.py` |
| Prompt assembly | `apps/api/src/application/chat/prompt_builder.py` |
| LLM client | `apps/api/src/infrastructure/langchain_adapters/chat_model.py` |
| Citation shaping | `apps/api/src/application/chat/citations.py` |
