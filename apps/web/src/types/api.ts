import type { Locator, SourceStatus, SourceType } from "@kb/shared";

export type { Locator, SourceStatus, SourceType };

// Latest ingestion job for an asset. Present on single-asset reads (GET
// /documents/{id}); null in the list view.
export type IngestionJob = {
  status: string;
  attempts: number;
  max_attempts: number;
  last_error: string | null;
};

export type KnowledgeAsset = {
  id: string;
  knowledge_base_id: string;
  lineage_id: string;
  version: number;
  filename: string;
  title: string | null;
  source_type: SourceType;
  storage_key: string;
  download_url: string | null;
  // Audio only: the readable transcript.md written beside the original at ingest time.
  transcript_url: string | null;
  // Pipeline stage: pending | queued | extracting | chunking | embedding | ready | failed.
  status: SourceStatus;
  failed_step: string | null;
  error_message: string | null;
  metadata: Record<string, unknown>;
  // How many indexed passages this source contributes — i.e. how much of it is usable.
  passage_count: number;
  job: IngestionJob | null;
  superseded_at: string | null;
  created_at: string | null;
  updated_at: string | null;
};

// Statuses that mean ingestion has stopped — used to end polling.
export const TERMINAL_STATUSES = ["ready", "failed"] as const;

export type Citation = {
  asset_id: string;
  chunk_id: string;
  filename: string;
  source_type: SourceType;
  locator: Locator;
  chunk_index: number;
  score: number;
  excerpt: string;
};

export type ChatResponse = {
  answer: string;
  insufficient_context: boolean;
  citations: Citation[];
};

// One line of the persisted worker log for an asset, shown as the plain-language
// activity timeline on source detail.
export type JobEvent = {
  id: string;
  event: string;
  level: string;
  message: string | null;
  data: Record<string, unknown>;
  ts: string | null;
};

// ---- Conversations -------------------------------------------------------
export type MessageRole = "user" | "assistant";

export type Message = {
  id: string;
  role: MessageRole;
  content: string;
  citations: Citation[];
  insufficient_context: boolean;
  created_at: string | null;
  /** Set only while streaming, so the UI can say what it is doing before tokens arrive. */
  status?: AnswerStatus | null;
  /** Set once the post-answer grounding check reports back. */
  grounding?: GroundingReport | null;
  /** How this answer was reached. Absent on answers written before the trace existed. */
  trace?: AnswerTrace | null;
  /** This reader's own thumb. Per-user, so it is never shared across a workspace. */
  feedback?: Rating | null;
};

/** A reader's verdict. Signed because the server sums it, not because it is a scale. */
export type Rating = 1 | -1;

// List view — enough to recognise a thread without loading it.
export type ConversationSummary = {
  id: string;
  title: string;
  message_count: number;
  preview: string;
  created_at: string | null;
  updated_at: string | null;
};

export type Conversation = {
  id: string;
  title: string;
  messages: Message[];
  created_at: string | null;
  updated_at: string | null;
};

// One indexed passage — the unit of retrieval and of citation. The viewer shows the cited
// one with its neighbours either side.
export type Passage = {
  chunk_index: number;
  text: string;
  locator: Locator;
};

// An answer that cited a given source, for the "answers that cited this" panel.
export type AssetCitation = {
  conversation_id: string;
  conversation_title: string;
  locator: Locator;
  chunk_index: number | null;
  score: number | null;
  excerpt: string | null;
};

// ---- Auth ----------------------------------------------------------------
export type TokenResponse = {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
};

export type LoginRequest = {
  email: string;
  password: string;
};

export type RegisterRequest = {
  email: string;
  password: string;
};

// The current identity, resolved from /auth/me for the account area. The server also
// returns a tenant label, which the UI deliberately never shows.
export type MeResponse = {
  user_id: string;
  email: string;
  name: string;
  tenant_id: string;
};

// What we persist client-side (in a host-scoped cookie). The access JWT only carries
// tid/sub, so email/name come from /auth/me. `remember` drives cookie lifetime: a
// persistent cookie when true, a session cookie (cleared on browser close) when false.
export type Session = {
  accessToken: string;
  refreshToken: string;
  email: string;
  name: string;
  expiresAt: number; // epoch ms
  remember: boolean;
};

export type UploadUrlResponse = {
  asset_id: string;
  upload_url: string;
  storage_key: string;
  expires_in_seconds: number;
  content_type: string;
};
/** What the pipeline is doing during the seconds before the first token. */
export type AnswerStage =
  | "resolving"
  | "searching"
  | "ranking"
  | "grading"
  | "rewriting"
  | "reading"
  | "generating";

export type AnswerStatus = {
  stage: AnswerStage;
  /** Present on "reading": how many passages the answer is being written from. */
  sources?: number;
  /** Which retrieval hop this is, and the cap it is counting towards. */
  hop?: number;
  of?: number;
  /** How the query for this hop was produced: "initial", "broaden", "decompose", "hyde". */
  strategy?: string;
  /** Present on "ranking": how many candidates came back from retrieval. */
  candidates?: number;
  /** Present on "grading": how many passages have accumulated across hops so far. */
  kept?: number;
};

/** One retrieval hop, as the loop recorded it. */
export type TraceHop = {
  hop: number;
  query: string;
  strategy: string;
  candidates: number;
  kept: number;
  rerank_degraded: boolean;
  sufficient: boolean;
  missing: string;
};

/**
 * How an answer was reached. Arrives on `done` and is stored with the message, so the panel
 * survives a reload rather than existing only for the tab that watched it stream.
 */
export type AnswerTrace = {
  resolved_query: string;
  hops: TraceHop[];
  /** "sufficient" | "max_hops" | "nothing_found" */
  exit_reason: string;
  /** True when reranking could not be reached and fusion order was used instead. */
  degraded: boolean;
  /**
   * How many remembered facts were put in front of this question. A count, never the facts:
   * memory is explicitly not citable, so the trace says it happened without dressing it up
   * as a source. Absent on answers written before memory existed.
   */
  memories_used?: number;
};

/**
 * The result of checking each cited claim against the passage it cites. Arrives after the
 * answer has finished streaming, so the badge resolves in place rather than delaying a word
 * of the response.
 */
export type GroundingReport = {
  /**
   * Three states, not two. `null` means nothing was checkable — the answer cited nothing, or
   * the judge could not be reached. Previously this was a bare boolean and an unchecked
   * answer reported `true`, which the badge only avoided showing because of a separate
   * `checked === 0` guard.
   */
  verified: boolean | null;
  checked: number;
  supported: number;
  /** Ordinals whose passage did not support the claim. */
  unsupported: number[];
  /** Ordinals the answer cited that were never offered to it. */
  invalid: number[];
  /** Sentences that asserted something and cited nothing. Not verified either way. */
  uncited_sentences?: number;
  /** Claims the judge could not be reached for. Absent on answers written before this. */
  unchecked?: number;
};

// ---- Workspace memory ----------------------------------------------------
/** Whether stored memories actually reach an answer. They did not, for the whole life of the
 * feature so far, while every other memory endpoint behaved normally — so the page asks. */
export type MemoryStatus = { enabled: boolean };

/** A fact the workspace has stated about itself, injected as background into future answers. */
export type WorkspaceMemory = {
  id: string;
  content: string;
  kind: "fact" | "preference";
  /** Where it was learned. Null when added by hand, or when the source thread was deleted. */
  source_conversation_id: string | null;
  /** Set once corrected. The old memory is kept so "why did it think that?" has an answer. */
  superseded_at: string | null;
  last_used_at: string | null;
  created_at: string | null;
};
