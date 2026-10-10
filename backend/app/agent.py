import json
import re
from datetime import datetime

from app.db import get_conn
from app.llm import complete
from app.safety import check_red_flags
from app.tools import TZ, run_tool, tool_schemas

MAX_STEPS = 10   # safety limit: the AI can call tools at most this many rounds

SYSTEM_PROMPT = """You are Fit Me Coach, a friendly personal fitness, sleep and nutrition coach.
Today is {today}.

You have tools to read the user's own health data (sleep, heart rate, HRV, steps, workouts, profile)
and a tool to search trusted health guidelines.

How to work:
1. For any question about the user ("I", "my", "me"), look at their data with tools BEFORE answering.
   Never guess their numbers.
2. For questions about tiredness, energy, recovery or readiness, call get_recovery_summary first.
3. Compare the user's recent numbers with their baseline (normal) values and explain what changed.
   Use their real numbers (for example "5.3 hours vs your usual 7.1").
4. Every health fact, recommendation or piece of advice MUST come from search_guides results.
   Call search_guides before giving advice. Cite each one with its source_id in square brackets, like [S123].
5. Only cite source_ids that appeared in your search_guides results. Never invent sources, numbers or thresholds.
   If the guides don't cover something, say so instead of giving advice from memory.
6. You are not a doctor. Never diagnose. If something looks worrying, suggest seeing a doctor.
7. Format: a 1-2 sentence summary of what the user's data shows (no citation needed),
   then up to 3 bullet points of advice. Every advice bullet must end with a citation like [S123]."""

FIX_PROMPT = ("Some advice has no citation, or cites a source_id that search_guides did not return. "
              "Every advice bullet must end with a citation like [S123] from your search_guides results. "
              "Search for support, or remove the unsupported points.")

CITATION = re.compile(r"\[(S\d+)\]")


def _clean(text):
    # The model sometimes writes citations as 【S123】: turn those into [S123].
    # Then remove marks it invents, like 【3†L1-L4】 and bare [2] (valid ones are [S123])
    text = re.sub(r"【(S\d+)[^】]*】", r"[\1]", text or "")
    text = re.sub(r"\s*【[^】]*】", "", text)
    return re.sub(r"\s*\[\d+\]", "", text).strip()


def _unsupported(answer, retrieved):
    """True if the answer cites a source we never retrieved, or has an advice bullet with no citation."""
    bullets = [line for line in answer.splitlines() if line.strip().startswith(("-", "*", "•"))]
    return (not set(CITATION.findall(answer)) <= retrieved.keys()
            or any(not CITATION.search(b) for b in bullets))


def _finalize(answer, retrieved):
    """Swap [S123] ids for numbered citations [1], [2] and build the source list.
    Ids that search_guides never returned are dropped."""
    numbering, sources = {}, []

    def renumber(match):
        sid = match.group(1)
        if sid not in retrieved:
            return ""
        if sid not in numbering:
            numbering[sid] = len(numbering) + 1
            sources.append({"n": numbering[sid], **retrieved[sid]})
        return match.group(0).replace(sid, str(numbering[sid]))

    return re.sub(r"\s*" + CITATION.pattern, renumber, answer), sources


def run_agent(question, user_id):
    # 1. Safety first: emergencies never reach the AI
    red_flag = check_red_flags(question)
    if red_flag:
        return {"answer": red_flag, "sources": [], "safety": "red_flag", "tool_calls": []}

    today = datetime.now(TZ).strftime("%A, %d %B %Y")
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(today=today)},
        {"role": "user", "content": question},
    ]
    trace, retrieved = [], {}
    retried = False   # we ask the AI to fix unsupported advice at most once

    with get_conn() as conn:
        for _ in range(MAX_STEPS):
            # 2. Ask the AI: answer now, or call tools?
            msg = complete(messages, tools=tool_schemas())

            messages.append(msg)

            # 3. No tool calls: the AI wants to answer. Send it back ONCE if the advice is not supported.
            if not msg.tool_calls:
                answer = _clean(msg.content)
                if not retried and _unsupported(answer, retrieved):
                    retried = True
                    messages.append({"role": "user", "content": FIX_PROMPT})
                    continue
                answer, sources = _finalize(answer, retrieved)
                return {"answer": answer, "sources": sources, "safety": "ok", "tool_calls": trace}

            # 4. Run every tool the AI asked for, and give it the results
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = run_tool(conn, user_id, tc.function.name, args)
                trace.append({"tool": tc.function.name, "args": args})
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

                # Remember every guideline chunk search_guides returned, so citations can be checked
                if tc.function.name == "search_guides":
                    for r in json.loads(result).get("results", []):
                        retrieved[r["source_id"]] = {"title": r["title"], "page": r["page"], "url": r["url"]}

    # 5. Too many steps: stop safely instead of looping forever
    return {"answer": "Sorry, I couldn't finish that. Could you ask in a simpler way?",
            "sources": [], "safety": "ok", "tool_calls": trace}
