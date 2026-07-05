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
  status: string;
  failed_step: string | null;
  error_message: string | null;
  metadata: Record<string, unknown>;
  superseded_at: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type Citation = {
  asset_id: string;
  chunk_id: string;
  filename: string;
  page_number: number | null;
  chunk_index: number;
  score: number;
  excerpt: string;
};

export type ChatResponse = {
  answer: string;
  insufficient_context: boolean;
  citations: Citation[];
};
