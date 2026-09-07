# The next two bets

Design sketches, not plans. Neither should be started until the eval harness has a real corpus
and a recorded baseline — that is the whole point of having built it, and both of these are
expensive enough that "it feels better" is not an acceptable justification.

Written after the flywheel work (grounding persistence, the RRF-ordering fix, feedback, the
relevance prior, workspace memory). Everything below assumes that is in place.

---

## Bet 1 — Deep research mode

**What it is.** A second answering mode that runs for minutes rather than seconds. Plan the
question, decompose it into sub-questions, run the existing bounded `RetrievalLoop` once per
sub-question, then synthesise a cited report with a section each.

**Why it fits here specifically.** Every part already exists and is owned:

| Need | What already does it |
|---|---|
| Durable background execution | Procrastinate, in the same Postgres |
| Progress streaming | The SSE frame vocabulary (`status`, `citations`, `delta`, `done`) |
| The unit of work | `RetrievalLoop.stream` — already bounded, already traced |
| The citation contract | `ContextAssembler`'s ordinal numbering |
| Answer verification | `GroundingChecker`, unchanged |

This is a supervisor over parts we already run in production, not new infrastructure. That is
what makes it a sketch rather than a research project.

### Shape

Two tables. `research_reports` holds the question, the plan as JSONB, a status, the markdown
body and its citations. `research_steps` holds each sub-question with its own trace and
citations.

The steps table exists for one reason worth stating: **a half-finished report has to be
readable.** A ten-minute job that shows nothing until it completes is one the user kills at
minute three. Storing per-step results means the report page renders progressively and a
crashed run still leaves something worth reading.

A `run_research` Procrastinate task with a long retry budget. `POST /research` returns an id
immediately; `GET /research/{id}` streams progress over SSE reusing the existing frames. UI is
a mode toggle in the composer, and a report page rendering the plan as a live checklist with
each section streaming in as it lands.

### The open questions, in the order they need answering

1. **Cost ceiling per report.** N sub-questions × up to 2 hops × the rerank, grade and verify
   calls each. At N=6 this is plausibly 40+ model calls for one question. There must be a
   configured ceiling and a visible estimate before a user starts one — not a bill they
   discover afterwards.
2. **Parallel or sequential fan-out.** Parallel is faster; sequential lets each sub-question
   use what the last one found, which is most of what makes research feel like research. This
   is the decision that most shapes the feature, and it should be made against real questions
   from the golden dataset, not in the abstract.
3. **Grounding granularity.** Per section, or over the whole report? Per section is more
   useful and N times more expensive.
4. **Is a report a conversation, or its own object?** Reusing conversations gets history and
   the existing UI for free but makes `messages` mean two different things. Leaning towards
   its own object.

**Gate:** plan this against Phase 2's real eval numbers. If single-hop recall is already
weak, running the same loop six times just produces six weak answers and an expensive
report — the compounding works in both directions.

---

## Bet 2 — Visual-first retrieval (ColPali / ColQwen)

**What it is.** Render each PDF page and slide to an image, embed the image with a vision
retrieval model, and score with late-interaction MaxSim over multi-vectors. Tables, charts,
diagrams, layout and scanned pages become retrievable — everything PyMuPDF4LLM currently
flattens into prose or drops entirely.

**Why it fits.** The locator model is already page- and slide-based, so a page-image hit
cites correctly with **zero change to the citation UI**. It slots in as a third retrieval arm
behind the RRF fusion that already exists — and the fusion is now honest, since the reranker
no longer re-sorts the pool by raw cosine and discards it.

### Shape

A `page_images` table plus a multi-vector store. Retrieval is necessarily two-stage: a pooled
single-vector ANN in pgvector `halfvec` to get candidates, then MaxSim over just those.
MaxSim across the whole corpus is not viable at any corpus size worth having. Rendering
happens as a new step in the existing `parse` phase of each source handler. In the UI,
citation cards gain a page thumbnail and `/view/{sourceId}` shows the page image with the
matched region highlighted.

### The hard gate, which is not a technical one

**The AICredits gateway is OpenAI-compatible and serves chat, embeddings and transcription
only. There is no vision-embedding endpoint.** So this requires either a new vendor or
self-hosting ColQwen on a GPU. That is a standing cost and an operational commitment, not a
library choice.

Storage is 100–1000 vectors per page, which is two to three orders of magnitude more than the
current one-vector-per-chunk and changes the shape of the database rather than just its size.

**Settle the hosting question before writing any code, and do not start until the eval can
prove the gain.** The honest version of this bet is: we currently cannot measure how much
retrieval is losing to flattened tables and diagrams. Phase 2's dataset should include cases
that specifically target them — a question only answerable from a chart, one only answerable
from a table's layout. If those cases score well without ColPali, this bet is not worth
making. If they score at zero, the size of the prize is known before anything is spent.

---

## Why both are gated on the same thing

The flywheel that just shipped is measurable by construction: `--holdout` says whether the
prior generalises, `citation_concentration` says whether it is entrenching, `grounded_rate`
says whether answers follow from their sources. Neither bet above has an equivalent, and both
cost real money per query.

The golden dataset is what turns them from opinions into decisions. Thirty questions against a
real corpus is a day of work and it is the highest-leverage day available right now.
