# UI Design Handover — AI Knowledge Base

> **Purpose of this document.** You are designing a full UI rework for this product. This
> brief gives you (a) the product and who it's for, (b) the exact data, states, and actions the
> backend exposes so your screens map to real objects, and (c) the flows that must exist.
>
> **Scope: design only.** Produce the visual/UX design — layouts, component system, states,
> flows, responsive behavior, and (if you generate any) reference markup/styling as *illustration*.
> The engineer will do the real implementation and wiring, so you do **not** need to write
> production code, set up data fetching, or match a specific framework's conventions. Optimize for
> a design another human/engineer can build from confidently.
>
> **Creative direction is yours.** Nothing here dictates colors, typography, brand, or visual
> tone. The constraints below are *functional* (what data exists, what states must be handled).
> Everything aesthetic is your call.

---

## 1. The product in one paragraph

An **AI Knowledge Base**: a user uploads documents (PDFs) and links (YouTube URLs) into their
private workspace; the system ingests them in the background (extract text → split into chunks →
generate vector embeddings) and then lets the user **chat with their knowledge base** and get
answers that are grounded in — and cite — the exact source passages. Think "a private, source-cited
ChatGPT over your own documents." It is **multi-tenant**: every account is an isolated workspace;
you only ever see your own sources and answers.

## 2. Who uses it & what they're trying to do

A single knowledge worker / researcher / student per workspace (today exactly one user per
tenant). Their jobs-to-be-done:

1. **Get sources in** quickly (drop a PDF, paste a YouTube link) and trust that they'll be processed.
2. **See processing status** at a glance — what's ready, what's still cooking, what failed (and why).
3. **Ask questions** and get a trustworthy, **cited** answer they can verify against the original.
4. **Manage the library** — rename, retry a failed source, delete, download the original.
5. **Peek under the hood** when something goes wrong (a worker-activity/log view).

The emotional core: *trust*. Answers must feel verifiable (citations), and processing must feel
transparent (clear status, honest failures).

## 3. Core concepts (glossary for the designer)

| Concept | What it is | Why the UI cares |
|---|---|---|
| **Tenant / Workspace** | The isolation boundary, identified by a **domain** (e.g. `admin.test`). | The user's identity is scoped to it; show which workspace they're in. |
| **User** | The person logging in (email + password). One per workspace today. | Login, account menu, logout. |
| **Knowledge Base** | The container all sources live in. Today there's one default KB per workspace, created automatically. | Mostly invisible now — treat the library as "the workspace's sources." Don't over-design KB switching yet. |
| **Asset (Source / Document)** | One ingested source: a PDF or a YouTube video. Has a **status**, a source type, a title, and metadata. | The central object of the library. |
| **Ingestion Job** | The background unit of work that processes an asset (with retry accounting). | Powers status, retry, and the worker-activity view. |
| **Job Event** | One line of a persisted **worker log** for an asset (a timeline of what happened). | A detail/debug timeline. |
| **Chat answer + Citations** | A generated answer plus the source chunks it drew from (filename, position, score, excerpt). | The payoff screen; citations must be first-class. |

## 4. Screens to design

Design these as a cohesive authenticated app. Prioritize in this order: **Chat + Library** (the
daily driver), then **Auth**, then **Asset detail**, then **Worker Activity**.

### 4.1 Auth
- **Login.** Fields: **email + password only** (no workspace field — the workspace is inferred from
  the domain the user is visiting). On success they enter the app. On failure the backend returns a
  single **generic error** ("Invalid credentials or inactive account") on purpose — do not design
  field-specific "wrong password" vs "no such user" messaging; it's one uniform error by design.
- **Register / Create workspace.** Fields: **desired domain** (e.g. `acme.test`), **email**,
  **password** (min 8 chars), optional **name**. Creates the workspace + its user in one step and
  logs them in. Handle a "**that domain is already taken**" conflict state.
- **Logout.** From an account menu.
- **Session expiry.** Sessions are token-based and access tokens are short-lived (~15 min) with
  silent renewal; design a graceful "your session expired, please log in again" state for when
  renewal fails. Assume any screen can bounce to Login if unauthenticated.

### 4.2 App shell
- Persistent navigation between **Chat**, **Library/Sources**, and **Worker Activity**.
- An **account area** showing the current workspace (domain) + user email, with logout.
- Global affordances for **errors/toasts** and **loading**.

### 4.3 Library / Sources (list of assets)
- A list of the workspace's current sources. Each row/card should be able to show: **title**
  (editable — rename), **filename**, **source type** (PDF vs YouTube — different icon/affordance),
  **status** (see §5), **version**, and — for failed ones — the **error message**.
- Row actions: **Retry** (only when `failed`), **Delete**, **Download original** (a
  `download_url` is provided when available), **Rename** (inline).
- **Add sources** entry points:
  - **Upload PDF** (file picker / drag-drop).
  - **Add from URL** (paste a YouTube link).
  - Both are async: the new source appears immediately as **`queued`** and then progresses through
    stages live (§5). Design that "just added, now processing" moment well.
- **Empty state** (no sources yet) is important — it's the first thing a new user sees.

### 4.4 Asset detail
- Everything from the row, plus:
  - The **latest job**: status, **attempts / max_attempts** (e.g. "attempt 2 of 3"), last error.
  - A **worker-log timeline** (Job Events): ordered oldest→newest, each with an event name, a
    **level** (info/warning/error), an optional message, a timestamp, and a freeform `data` blob.
    Design this as a readable activity timeline, not a raw log dump.
  - **Metadata**: a freeform key/value bag that varies by source (e.g. page count for a PDF, video
    title/duration for YouTube). Design an expandable "details" area that can render arbitrary keys.
  - Actions: retry / delete / download / rename.

### 4.5 Chat (the payoff)
- A conversation: user questions and assistant answers.
- Each **assistant answer** carries **citations**. A citation has: source **filename**, source
  **type**, a **locator** (a source-neutral position — for a PDF `page 3`, for YouTube a timestamp
  `at 2:05`), a **chunk index**, a **relevance score** (0–1), and an **excerpt** of the cited text.
  Citations are the trust anchor — make them scannable and clearly tied to the answer.
- **Insufficient-context state:** answers include an `insufficient_context` boolean. When true, the
  system is telling the user "I couldn't answer this from your sources." Design a distinct, honest
  state for this (not a normal answer, not an error).
- Consider the **cold-start** case: chatting with an empty (or still-processing) library — nudge the
  user to add/finish sources.

### 4.6 Worker Activity / Jobs
- A dashboard of recent ingestion jobs across the workspace: filename, status, **attempts**, and
  timing (**scheduled / started / finished / created**), plus last error.
- Drill-in reveals the same per-asset event timeline as §4.4.
- This is a "monitoring / observability" surface — it can look more utilitarian than Chat/Library.

## 5. The ingestion lifecycle (the most important UX detail)

Adding a source is **asynchronous**. The upload/URL request returns instantly with a `queued`
asset, then the background worker moves it through pipeline stages. The UI **polls** for progress
until a terminal state. Your design must make this progression feel alive and trustworthy.

**Asset status** (the pipeline stage shown to the user):

```
queued → extracting → chunking → embedding → ready
                                           ↘ failed  (from any stage)
```

| Status | Meaning | Design intent |
|---|---|---|
| `queued` | Accepted, waiting for a worker. | "Received, in line." |
| `extracting` | Pulling text from the source. | Progress / working. |
| `chunking` | Splitting text into passages. | Progress / working. |
| `embedding` | Generating vectors. | Progress / working. |
| `ready` | Done — usable in chat. | Success; this source now answers questions. |
| `failed` | Stopped with an error (after retries). | Clear failure + **Retry** + the error message. |
| `pending` | Rare/transient initial state before `queued`. | Treat like `queued`. |

Terminal states are **`ready`** and **`failed`** (polling stops there). Design distinct visual
treatments for: in-progress (the 4 working stages — could be one animated "processing" treatment
with a sub-label, or a 4-step stepper), success, and failure. A source may also have a **version**
(re-ingesting supersedes an old version) — minor, but the field exists.

**Job status** is coarser than asset status (`queued / running / succeeded / failed`) and is what
the Worker Activity view shows, alongside **attempts / max_attempts** (retries; default max 3).

## 6. Data contract reference

These are the actual object shapes the screens bind to. Fields are what you have available to
display; you don't need to show all of them.

**Asset** (library rows & detail): `id`, `title` (nullable — fall back to `filename`), `filename`,
`source_type` (`"pdf"` | `"youtube"`), `status` (§5), `version`, `failed_step` (nullable),
`error_message` (nullable), `download_url` (nullable), `metadata` (freeform object), `job` (present
on detail reads: `{ status, attempts, max_attempts, last_error }`), `created_at`, `updated_at`,
`superseded_at` (nullable).

**Citation** (in chat answers): `filename`, `source_type`, `locator` (`{ type, value }` — e.g.
`{type:"page", value:3}` or `{type:"timestamp", value:125}`, nullable), `chunk_index`, `score`
(float 0–1), `excerpt` (text).

**Chat answer:** `answer` (text), `insufficient_context` (bool), `citations` (list).

**Job** (Worker Activity): `filename`, `status` (`queued/running/succeeded/failed`), `attempts`,
`max_attempts`, `last_error` (nullable), `scheduled_at`, `started_at`, `finished_at`, `created_at`.

**Job Event** (timeline): `event` (name), `level` (`info`/`warning`/`error`), `message` (nullable),
`data` (freeform object), `ts` (timestamp).

### Capabilities (what the backend can do — for grounding, not for you to wire)

| Action | Result / notes | Auth |
|---|---|---|
| Register | Create workspace + user, returns a session. `409` if domain taken, `422` on invalid input. | public |
| Login | Email + password (workspace = current domain). `401` generic on any failure. | public |
| Logout | Ends the session. | public |
| List sources | Current sources in the workspace. | required |
| Upload PDF | Returns a `queued` source immediately (async). | required |
| Add URL (YouTube) | Returns a `queued` source immediately (async). | required |
| Get one source | Includes latest job — used for live status polling. | required |
| Source event log | The per-source worker timeline. | required |
| Retry source | Re-processes a `failed` source (no re-upload). | required |
| Rename source | Sets the title. | required |
| Delete source | Removes it. | required |
| List jobs | Recent ingestion jobs (Worker Activity). | required |
| Ask a question | Returns answer + `insufficient_context` + citations. | required |

## 7. States & edge cases to cover in the design

Please design explicit treatments for each — these are where products feel finished:

- **Empty library** (brand-new workspace) — the onboarding moment; guide toward adding a first source.
- **Loading** — list load, chat "thinking," source-detail load.
- **Live progress** — a source moving `queued → … → ready` while the user watches.
- **Failed ingestion** — status `failed` + `error_message` + Retry; and the "retry in progress" state.
- **Insufficient context** — chat couldn't answer from sources.
- **Chatting with nothing ready** — empty or still-processing library.
- **Auth errors** — generic login failure; domain-taken on register; validation errors.
- **Session expired** — bounce to login gracefully.
- **Unauthorized** — any protected action when logged out.
- **Long lists** — many sources / many jobs (no pagination today; assume scroll).

## 8. Design priorities & guardrails

- **Trust first.** Citations and honest status are the product's soul. Don't bury them.
- **Two modes of use:** a *creation/management* surface (Library + adding sources) and a
  *consumption* surface (Chat). They can feel distinct but must share one shell.
- **Async is the norm.** Never imply a source is instantly usable; the design should make waiting
  feel intentional and informative.
- **Multi-tenant, single-user (today).** Show the workspace identity, but don't design team/roles/
  member management yet (see §9).
- **Responsive.** Assume desktop-first (it's a work tool) but keep it usable on smaller screens —
  Chat especially.
- **Accessibility.** Status must not rely on color alone (use label/shape too); citations and
  timelines must be readable.
- **Content realism.** Use realistic sample data: mixed PDF + YouTube sources, some `ready`, one
  `extracting`, one `failed`; an answer with 2–3 citations of varying scores; a source with a
  multi-step event timeline including a warning.

## 9. Out of scope (do not design these yet)

- Teams / multiple users per workspace / roles & permissions (the backend is built to allow it
  later, but there's exactly one user per workspace today).
- Billing, plans, usage metering.
- Multiple/switchable knowledge bases (one default KB per workspace for now).
- Additional source types beyond PDF + YouTube (websites etc. come later — but designing source
  rows to be *type-extensible* is welcome).
- Admin / cross-workspace tooling.

## 10. What to hand back

- The screens in §4 with their key **states** from §7 (not just the happy path).
- A lightweight **component inventory** (buttons, status badges, source row, citation card, timeline
  item, empty states, toasts/errors) so the build is systematic.
- Responsive behavior for at least Chat and Library.
- Any tokens/system you establish (spacing, type scale, color roles) — but this is your creative
  call; the engineer will adapt it during implementation.
```
