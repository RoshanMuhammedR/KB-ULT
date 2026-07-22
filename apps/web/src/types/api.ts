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
  source_type: string;
  storage_key: string;
  download_url: string | null;
  // Pipeline stage: queued | extracting | chunking | embedding | ready | failed.
  status: string;
  failed_step: string | null;
  error_message: string | null;
  metadata: Record<string, unknown>;
  job: IngestionJob | null;
  superseded_at: string | null;
  created_at: string | null;
  updated_at: string | null;
};

// Statuses that mean ingestion has stopped — used to end polling.
export const TERMINAL_STATUSES = ["ready", "failed"] as const;

// Source-neutral citation position. For PDF: { type: "page", value: 3 }. A future
// YouTube source would use { type: "timestamp", value: 125 }, rendered accordingly.
export type Locator = {
  type: string;
  value: number | string | null;
};

export type Citation = {
  asset_id: string;
  chunk_id: string;
  filename: string;
  source_type: string;
  locator: Locator | null;
  chunk_index: number;
  score: number;
  excerpt: string;
};

export type ChatResponse = {
  answer: string;
  insufficient_context: boolean;
  citations: Citation[];
};

// One ingestion job in the /jobs dashboard.
export type JobSummary = {
  id: string;
  asset_id: string;
  filename: string;
  status: string;
  attempts: number;
  max_attempts: number;
  last_error: string | null;
  scheduled_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string | null;
};

// One line of the persisted worker log for an asset.
export type JobEvent = {
  id: string;
  event: string;
  level: string;
  message: string | null;
  data: Record<string, unknown>;
  ts: string | null;
};

// ---- Auth ----------------------------------------------------------------
export type TokenResponse = {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
};

export type LoginRequest = {
  domain: string;
  email: string;
  password: string;
};

// The current identity, resolved from /auth/me for the account area.
export type MeResponse = {
  user_id: string;
  email: string;
  tenant_id: string;
  domain: string;
  name: string;
};

// What we persist client-side (in a host-scoped cookie). The access JWT only carries
// tid/sub, so email/domain/name come from /auth/me. `remember` drives cookie lifetime:
// a persistent cookie when true, a session cookie (cleared on browser close) when false.
export type Session = {
  accessToken: string;
  refreshToken: string;
  email: string;
  domain: string;
  name: string;
  expiresAt: number; // epoch ms
  remember: boolean;
};
