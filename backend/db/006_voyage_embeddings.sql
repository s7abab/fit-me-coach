-- Embeddings now come from Voyage AI (1024 numbers per text, was 384).
-- Old vectors can't be compared with new ones, so the knowledge base is emptied: run scripts/ingest.py after this.
TRUNCATE documents CASCADE;

DROP INDEX IF EXISTS chunks_embedding_idx;
ALTER TABLE chunks ALTER COLUMN embedding TYPE vector(1024);
CREATE INDEX IF NOT EXISTS chunks_embedding_idx ON chunks USING hnsw (embedding vector_cosine_ops);
