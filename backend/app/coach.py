from app.db import get_conn
from app.llm import chat
from app.retrieval import search
from app.safety import check_red_flags

SYSTEM_PROMPT = """You are Fit Me Coach, a friendly fitness, sleep and nutrition coach.

Rules:
1. Answer ONLY using the numbered sources in the context. Cite them like [1] or [2].
2. If the sources don't contain the answer, say you don't have that information in your guides. Never guess.
3. You are not a doctor. Never diagnose conditions. Never recommend medicines or doses.
4. If the user mentions a medical condition, injury, pregnancy or medication, give only general guidance
   from the sources and advise them to check with a doctor before changing their routine.
5. Never give extreme diets, very low calorie plans or rapid weight-loss plans. Suggest seeing a professional instead.
6. Keep answers short and practical: 2-5 sentences or a short list."""


def build_context(chunks):
    # Number each chunk and label it with its source, so the AI can cite [1], [2]...
    return "\n\n".join(
        f"[{i}] ({c['title']}, page {c['page']})\n{c['content']}"
        for i, c in enumerate(chunks, start=1)
    )


def answer(question):
    # 1. Safety first: emergencies never reach the AI
    red_flag = check_red_flags(question)
    if red_flag:
        return {"answer": red_flag, "sources": [], "safety": "red_flag"}

    # 2. Find the best chunks
    with get_conn() as conn:
        chunks = search(conn, question)

    if not chunks:
        return {"answer": "I don't have information about that in my guides.", "sources": [], "safety": "ok"}

    # 3. Ask the AI, using only those chunks
    reply = chat([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Context:\n{build_context(chunks)}\n\nQuestion: {question}"},
    ])

    sources = [
        {"n": i, "title": c["title"], "page": c["page"], "url": c["url"]}
        for i, c in enumerate(chunks, start=1)
    ]
    return {"answer": reply, "sources": sources, "safety": "ok"}