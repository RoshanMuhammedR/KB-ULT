# Build Prompt — Saga UI Rebuild

You are rebuilding the entire user interface of an existing, working product called **Saga**.
Backend, database, ingestion pipeline, and auth are already built and running. What exists on the
front end is a functional but *developer-shaped* interface: it exposes internals (worker queues,
job attempt counters, raw event logs, pipeline stage names) directly to the end user, and it is
styled with ~1,400 lines of hand-written CSS. Your job is to replace that with a **clean, polished,
consumer-grade SaaS interface** — for both the marketing site and the product app.

**Creative direction is entirely yours.** Nothing in this document tells you what it should look
like: no colors, no typography, no layout, no spacing, no brand tone, no component shapes, no
"modern minimal" or any other adjective. Every constraint below is *functional* — what the product
does, what data exists, what states must be handled, what a user is trying to accomplish. Make all
aesthetic and structural decisions yourself, and make them well.

---

## 0. Ground rules

**Stack you must build in:**

- Next.js 15 (App Router) + React 19 + TypeScript, in an existing pnpm/Turborepo monorepo.
- **Tailwind CSS v4**, using its CSS-first configuration (`@import "tailwindcss"` + `@theme`). There
  is **no `tailwind.config.js`** and there should not be one. PostCSS is wired via
  `@tailwindcss/postcss`.
- **All existing hand-written CSS must go.** Delete/replace `apps/web/src/app/globals.css`,
  `apps/website/src/app/globals.css`, and `packages/ui/src/theme.css`. Styling lives in Tailwind
  utilities and a design-token layer you define in `@theme`. A tiny amount of global CSS for base
  resets, keyframes, and token declarations is fine; page-level and component-level `.class`
  stylesheets are not.
- `lucide-react` is already available. You may add unstyled/headless primitive libraries if they
  earn their place, but the visual system must be yours.

**Two apps, one product:**

| App | Path | What it is |
|---|---|---|
| `apps/website` | served at `/` | The public marketing site. Anonymous visitors. Its job is to explain and convert. |
| `apps/web` | served at `/app` (Next `basePath: "/app"`) | The signed-in product. Its job is to be used every day. |

They share one origin and one shared package, `@kb/ui` (currently exports `Button`, `Field`,
`Logo`, `StatusDot`, `Divider`, `cn`). Rebuild and expand that package into a real design system
consumed by both apps — anything used in both belongs there.

**The core rewrite mandate:** the current app leaks engineering vocabulary at the user
("worker activity", "attempts 2 of 3", "procrastinate job", "chunking", "embedding", raw JSON event
blobs, pipeline step names as primary status). A real SaaS user should never need to know a queue
exists. Keep the *information* — a user genuinely needs to know a document is still processing,
that one failed, and why — but express it in human terms, and put technical detail behind an
explicit "details / advanced" affordance for the rare moment it's wanted. Transparency, yes;
internals-as-UI, no.

**Scope discipline:** §4 is what the product already does and §5 is the only new functionality being
added. Do not invent additional features, pages, or product surfaces beyond those two sections.

---

## 1. What Saga is

Saga turns a person's own documents and media into a private, searchable knowledge base they can
have a conversation with — and every answer it gives is grounded in, and cites, the exact passages
it came from.

You upload a PDF or paste a YouTube link. Saga pulls out the text, splits it into passages, and
converts each passage into a vector embedding stored in Postgres/pgvector. When you ask a question,
Saga embeds the question, retrieves the most semantically relevant passages from *your* library,
and asks an LLM to answer using only those passages. The answer comes back with citations: the
source file, the position inside it (page 3, or 2:05 in a video), a relevance score, and the
verbatim excerpt.

The promise, in one line: **answers you can trace back to the page.** The whole product is a trust
machine. If a user can't verify an answer, the product has failed. If Saga can't find enough
relevant material, it says so honestly rather than inventing an answer.

It is multi-tenant: each account is an isolated workspace, enforced at the database level. Your
sources and your answers never leave it.

---

## 2. Who uses it and why

Primary users are knowledge workers who accumulate reading faster than they can retain it:
researchers and grad students drowning in papers, analysts working through filings and reports,
consultants prepping for a client, lawyers across case files, product teams with years of specs and
call recordings, anyone studying for something hard.

What they are actually trying to do:

1. **Get material in fast and trust it landed.** Dropping in twelve PDFs should be a ten-second act,
   not a chore.
2. **Know the state of their library at a glance.** What's usable, what's still being processed,
   what broke and why.
3. **Ask a real question and get an answer they can defend.** With the receipts attached.
4. **Verify a claim in one click.** Go from a sentence in an answer to the exact page it came from.
5. **Come back tomorrow** and pick up the same line of inquiry.

Emotionally: relief and confidence. Never anxiety about whether the machine made something up.

---

## 3. Vocabulary

| Term | Meaning |
|---|---|
| **Workspace** | The tenant boundary. One account = one isolated workspace, one user. |
| **Source** (a.k.a. asset/document) | One ingested item — a PDF, a YouTube video, and the three new types in §5.3. Has a title, a type, a status, and metadata. |
| **Ingestion** | The background pipeline that turns a raw source into searchable passages. Asynchronous; takes seconds to minutes. |
| **Passage / chunk** | A slice of a source's text, embedded as a vector. The unit of retrieval and the unit of citation. |
| **Citation** | A pointer from a sentence in an answer back to the passage that supports it. |
| **Insufficient context** | Saga's honest "I couldn't answer this from your sources" outcome. A first-class result, not an error. |
| **Conversation** | (new — §5.1) A persisted, resumable thread of questions and answers. |

---

## 4. What the backend already does (real, shipped)

Design against these actual shapes. You do not have to display every field.

**Auth.** Email + password. Registering creates the workspace and its owner in one step and signs
you straight in; optional workspace name. Login failures return one deliberately generic message
("invalid credentials or inactive account") — there is no "wrong password" vs "no such user"
distinction to design around. Sessions are short-lived access tokens (~15 min) with silent refresh
in the background; when refresh fails the user is bounced to login and needs a graceful re-entry.
There's a "keep me signed in" option. Registering with an existing email returns a conflict. There
is an account area showing the signed-in user and their workspace, with sign-out.

**Sources.** List, upload a PDF, add a URL, read one, rename, delete, download the original, retry a
failed one. Shape:

```
Source {
  id, title (nullable — fall back to filename), filename,
  source_type: "pdf" | "youtube",
  status: "queued" | "extracting" | "chunking" | "embedding" | "ready" | "failed",
  version, failed_step (nullable), error_message (nullable),
  download_url (nullable), metadata (freeform: page count, video duration, author, …),
  created_at, updated_at
}
```

**Ingestion is asynchronous and that is the single most important interaction in the product.**
Adding a source returns instantly in a `queued` state; the server then moves it through
extract → split → embed → ready, or lands it in `failed` with an error message. The client polls
until a terminal state (`ready` or `failed`). A user watching this happen must feel that something
real is underway, roughly how far along it is, and — when it breaks — what broke and what they can
do about it (retry, without re-uploading). Failures do happen: encrypted PDFs, scanned image-only
PDFs with no text layer, YouTube videos with transcripts disabled, oversized files, transient
provider errors that succeed on retry.

**Chat.** Ask a question → get `{ answer, insufficient_context, citations[] }`. Answers are
generated only from retrieved passages; if fewer than a minimum number of passages clear a
relevance threshold, `insufficient_context` comes back true with a "not enough in your sources"
answer. Citations:

```
Citation {
  filename, source_type,
  locator: { type: "page", value: 3 } | { type: "timestamp", value: 125 } | null,
  chunk_index, score (0–1), excerpt (verbatim text)
}
```

**Processing history.** Per-source event logs and job records exist (statuses, attempt counts,
timestamps, error strings, structured event data). Today this is surfaced as a raw admin table.
It should become a human-readable, plain-language activity history — the technical payload stays
available but stops being the primary presentation.

**Not built, and not to be designed as if it works:** email verification, password reset, multiple
users per workspace, teams or roles, multiple knowledge bases, billing or plans. There is exactly
one user per workspace and one library.

---

## 5. The new functionality — exactly three additions

These three things do not exist in the backend yet; they are being built alongside this UI, so
design against realistic mock data. **This is the complete list of new features. Nothing else.**

### 5.1 Conversations, with full CRUD

Today every question is a one-shot and the history dies on refresh. Give the product memory: named,
persistent conversations a user can leave and come back to.

- **Create** — start a new conversation; it gets a title auto-generated from the opening question.
- **Read** — a browsable history of past conversations, each showing its title, when it last moved,
  and enough of a preview to recognize it; open one and see the full thread; search across them.
- **Update** — rename a conversation; continue an old one with new questions.
- **Delete** — remove a conversation, with whatever confirmation you judge appropriate.

Beyond CRUD, the thread itself has to work as a real chat surface: follow-up questions that
understand what came before ("what about the second one?"), so the *thread* must be legible rather
than just the latest exchange; per-message actions (copy, regenerate, delete a message); and answers
that stream in progressively rather than appearing all at once, so the wait is legible.

```
Conversation { id, title, created_at, updated_at, message_count }
Message { id, role: "user" | "assistant", content, citations[], insufficient_context, created_at }
```

### 5.2 Citations you can actually open

Right now a citation shows an excerpt and stops there. Close the loop: clicking a citation should
put the user in front of the original material at the exact spot it came from.

- **PDF** — view the source at the cited page, with the cited passage visibly located within it and
  the surrounding text so the quote has context.
- **Video / audio** — the player, positioned at the cited timestamp, with the transcript around it.
- **Slides** — the cited slide, in context of the deck.
- **Markdown / text** — the cited section, with the passage located inside it.

Also required: a clear path back to the answer the user came from; the ability to step through an
answer's citations as a set rather than opening them one at a time; and, from any source, a view of
which answers have cited it.

This is the feature that makes the product's core promise literal. Treat it as a headline surface,
not a modal afterthought.

### 5.3 Three more source types

The library today accepts PDFs and YouTube links. Add three more, and design the add-source
experience so the set is visibly extensible rather than hardcoded to five:

| Type | Input | Natural citation locator | Notes for the UI |
|---|---|---|---|
| **Markdown** (`.md`) | File upload, or paste raw Markdown directly | Heading / section | The paste path needs its own affordance and a way to title the result. |
| **PowerPoint** (`.pptx`) | File upload | Slide number | Metadata includes slide count; a deck's structure is worth showing. |
| **Audio** (`.mp3`, `.m4a`, `.wav`) | File upload | Timestamp | Transcribed on ingest, so it's slower than the rest — the wait is longer and the progress feedback matters more. Metadata includes duration. |

Each type needs its own recognizable identity in the library, its own metadata display, its own
failure modes (a corrupt deck, an audio file with no speech, a Markdown file that's effectively
empty), and its own behavior when a citation into it is opened (§5.2).

---

## 6. Surfaces to produce

### The marketing site (`apps/website`, anonymous visitors)

It currently has a single page. Build it out into a real site that could plausibly sell this: a home
page that lands the "answers you can trace back to the page" promise and shows the product rather
than describing it; how it works; features in depth; use cases for the audiences in §2; a security
and privacy page (this matters enormously for a product people feed private documents into —
workspace isolation, encryption, data handling, deletion); about; contact; legal pages; and a 404.
Conversion paths into sign-up and log-in must be obvious from anywhere. No pricing or plans — the
product doesn't have them.

### The product app (`apps/web`, signed in)

Everything in §4 and §5 needs somewhere to live: authentication (register, log in, expired-session
re-entry) and the account area; the conversational surface and its persisted history; the source
library and the act of adding to it across all five source types; individual source detail with its
metadata and plain-language processing history; and the citation/source viewer. How these are
organized, navigated, combined, or separated is your call — it's a real information-architecture
problem and solving it is part of the work.

---

## 7. States that must exist

Products feel unfinished in the gaps. Design all of these explicitly, not just the happy path:

- **Empty** — no sources yet (the first thing every new user sees); no conversations yet; a brand-new
  conversation with nothing asked; no results after searching or filtering the library.
- **Loading** — first paint, library load, answer generation, source detail, conversation history.
- **In progress** — one or many sources moving through ingestion simultaneously, live; a retry
  underway; a long upload with real byte progress; a slow audio transcription.
- **Failure** — a source that failed and why, in plain language, with the recovery action; a chat
  request that errored; a network drop mid-poll where the client has lost track of progress; the
  server being unreachable entirely.
- **Insufficient context** — Saga couldn't answer from the library. Visually and tonally distinct
  from both a normal answer and an error. It's the product being honest, and it should read that way.
- **Asking with nothing ready** — an empty or still-processing library.
- **Auth edge cases** — generic login failure, email already registered, validation errors, expired
  session, unauthenticated access to a protected surface.
- **Scale** — hundreds of sources, a long list of past conversations, a fifty-message thread, a
  citation excerpt that's a wall of text, a filename 200 characters long, a source with no
  extractable title.

---

## 8. Requirements that aren't negotiable

- **Trust is the product.** Citations, honest failure, and honest "I don't know" are the reason Saga
  exists. They are never the thing that gets compressed to make room for something else.
- **Plain language.** No queue mechanics, no pipeline stage names, no attempt counters, no raw JSON
  as the primary presentation of anything. Technical detail stays reachable; it stops being the
  default.
- **Asynchrony is the norm.** Never imply a source is usable the instant it's added. Waiting should
  feel intentional and informative.
- **Accessible.** Keyboard-navigable throughout, correct semantics and focus management, status never
  conveyed by color alone, respects reduced-motion, sufficient contrast. Chat and citation reading in
  particular must work for screen readers.
- **Responsive.** It's a work tool, so it will mostly be used on a large screen — but it must be
  genuinely usable on a phone, especially asking questions and checking whether an upload finished.
- **Light and dark** both fully designed, not one derived carelessly from the other.
- **Systematic.** A real token layer in Tailwind v4's `@theme` and a shared component library, so the
  two apps read as one product and a new screen is assembly rather than invention.
- **Realistic content.** Populate everything with believable data: a mixed library spanning all five
  source types, several ready, one mid-processing, one failed on a scanned document; an answer with
  three citations of varying relevance; a conversation with follow-ups; a source whose processing
  history includes a warning and a successful retry. Never `Lorem ipsum`, never
  `Document 1 / Document 2`.

---

## 9. What to deliver

Working, buildable Next.js + Tailwind v4 code across both apps and the shared package, with the
existing CSS removed. Every surface in §6, every state in §7. Interactive where behavior matters —
ingestion progress, streaming answers, opening a citation, and filtering should demonstrate
themselves against mock data rather than sitting still. Include a short written summary of the
design system you established and the information architecture you chose, so the engineer wiring
this to the live API knows the intent behind it.

The API contracts in §4 are real and must be honored. The three features in §5 don't exist yet —
design them as though they will, and keep the seams clean enough that they can be.
