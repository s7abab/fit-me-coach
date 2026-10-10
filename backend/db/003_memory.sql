-- A chat session
CREATE TABLE IF NOT EXISTS conversations (
    id          bigserial PRIMARY KEY,
    user_id     bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  timestamptz DEFAULT now()
);

-- Every question and answer
CREATE TABLE IF NOT EXISTS chat_messages (
    id               bigserial PRIMARY KEY,
    conversation_id  bigint NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role             text NOT NULL CHECK (role IN ('user', 'assistant')),
    content          text NOT NULL,
    created_at       timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS chat_messages_conv_idx ON chat_messages (conversation_id, id);

-- Lasting facts the user told the coach
CREATE TABLE IF NOT EXISTS user_memories (
    id          bigserial PRIMARY KEY,
    user_id     bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    fact        text NOT NULL,
    created_at  timestamptz DEFAULT now(),
    UNIQUE (user_id, fact)
);