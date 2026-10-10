HISTORY_MESSAGES = 6   # last 6 messages = last 3 question/answer pairs
MAX_MEMORIES = 30


def get_or_start_conversation(conn, user_id, conversation_id=None):
    """Continue the user's own conversation, or start a new one."""
    if conversation_id:
        owned = conn.execute(
            "SELECT 1 FROM conversations WHERE id = %s AND user_id = %s", (conversation_id, user_id)
        ).fetchone()
        if owned:
            return conversation_id
    return conn.execute(
        "INSERT INTO conversations (user_id) VALUES (%s) RETURNING id", (user_id,)
    ).fetchone()[0]


def load_history(conn, conversation_id):
    rows = conn.execute(
        "SELECT role, content FROM chat_messages WHERE conversation_id = %s ORDER BY id DESC LIMIT %s",
        (conversation_id, HISTORY_MESSAGES),
    ).fetchall()
    return [{"role": role, "content": content} for role, content in reversed(rows)]


def save_turn(conn, conversation_id, question, answer):
    conn.execute(
        "INSERT INTO chat_messages (conversation_id, role, content) VALUES (%s, 'user', %s), (%s, 'assistant', %s)",
        (conversation_id, question, conversation_id, answer),
    )


def load_memories(conn, user_id):
    rows = conn.execute(
        "SELECT fact FROM user_memories WHERE user_id = %s ORDER BY created_at DESC LIMIT %s",
        (user_id, MAX_MEMORIES),
    ).fetchall()
    return [fact for (fact,) in rows]


def save_memory(conn, user_id, fact):
    conn.execute(
        "INSERT INTO user_memories (user_id, fact) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (user_id, fact),
    )