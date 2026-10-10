CREATE TABLE IF NOT EXISTS documents (
    id          bigserial PRIMARY KEY,
    title       text NOT NULL,
    filename    text UNIQUE NOT NULL,
    source_url  text,
    file_hash   text NOT NULL,
    created_at  timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks (
    id           bigserial PRIMARY KEY,
    document_id  bigint NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page         int,
    content      text NOT NULL,
    embedding    vector(1024),
    tsv          tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
);

-- Fast meaning search
CREATE INDEX IF NOT EXISTS chunks_embedding_idx ON chunks USING hnsw (embedding vector_cosine_ops);
-- Fast keyword search
CREATE INDEX IF NOT EXISTS chunks_tsv_idx ON chunks USING gin (tsv);