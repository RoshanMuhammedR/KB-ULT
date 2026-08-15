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
};

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
