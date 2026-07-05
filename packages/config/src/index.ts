export const configDefaults = {
  aicreditsBaseUrl: "https://api.aicredits.in/v1",
  chatModel: "openai/gpt-4o-mini",
  embeddingModel: "text-embedding-3-small",
  embeddingDimensions: 1536,
  chunkSizeTokens: 800,
  chunkOverlapTokens: 120,
  retrievalTopK: 5,
  retrievalScoreThreshold: 0.25,
  retrievalMinContextChunks: 2
} as const;
