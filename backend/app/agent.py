import json
import re
import time
from datetime import datetime

from app.db import get_conn
from app.llm import complete
from app.safety import check_red_flags
from app.tools import TZ, run_tool, tool_schemas

MAX_STEPS = 6   # safety limit: the AI can call tools at most this many rounds

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

CITATION = re.compile(r"\[S(\d+)\]")


def _clean(text):
    # Remove model-specific marks like 【3†L1-L4】 and bare [2] the model invents (valid ones are [S123])
    text = re.sub(r"\s*【[^】]*】", "", text or "")
    return re.sub(r"\s*\[\d+\]", "", text).strip()


def _grounding_problems(answer, retrieved):
    """Find citations that were never retrieved, and advice bullets with no citation."""
    problems = []
    fake = sorted({f"S{n}" for n in CITATION.findall(answer)} - retrieved.keys())
    if fake:
        problems.append(f"You cited {', '.join(fake)}, which did not come from search_guides.")
    uncited = [line.strip() for line in answer.splitlines()
               if line.strip().startswith(("-", "*", "•")) and not CITATION.search(line)]
    if uncited:
        problems.append("These advice points have no citation: " + " | ".join(u[:80] for u in uncited[:3]))
    return problems


def _assistant_message(msg):
    """Turn the model's reply into a dict we can send back in the next request."""
    out = {"role": "assistant", "content": msg.content or ""}
    if msg.tool_calls:
        out["tool_calls"] = [{
            "id": tc.id,
            "type": "function",
            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
        } for tc in msg.tool_calls]
    return out


def _collect_sources(result_json, retrieved):
    """Remember every guideline chunk search_guides returned, by source_id."""
    try:
        for r in json.loads(result_json).get("results", []):
            retrieved[r["source_id"]] = {"title": r["title"], "page": r["page"], "url": r["url"]}
    except (json.JSONDecodeError, KeyError, AttributeError):
        pass


def _finalize(answer, retrieved):
    """Swap [S123] ids for numbered citations [1], [2] and build the source list."""
    numbering, sources = {}, []

    def renumber(match):
        sid = f"S{match.group(1)}"
        if sid not in numbering:
            numbering[sid] = len(numbering) + 1
            sources.append({"n": numbering[sid], **retrieved[sid]})
        return f"[{numbering[sid]}]"

    return CITATION.sub(renumber, answer), sources


def run_agent(question, user_id, verbose=False):
    # 1. Safety first: emergencies never reach the AI
    red_flag = check_red_flags(question)
    if red_flag:
        return {"answer": red_flag, "sources": [], "safety": "red_flag", "tool_calls": [], "steps": 0,
                "grounded": True, "grounding_issues": []}

    today = datetime.now(TZ).strftime("%A, %d %B %Y")
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(today=today)},
        {"role": "user", "content": question},
    ]
    trace, retrieved = [], {}
    guard_used = False   # we ask the AI to fix unsupported claims at most once

    with get_conn() as conn:
        for step in range(1, MAX_STEPS + 1):
            # 2. Ask the AI: answer now, or call tools?
            msg = complete(messages, tools=tool_schemas())
            messages.append(_assistant_message(msg))

            # 3. No tool calls: the AI wants to answer. Check its grounding first.
            if not msg.tool_calls:
                answer = _clean(msg.content)
                problems = _grounding_problems(answer, retrieved)
                if problems and not guard_used and step < MAX_STEPS:
                    guard_used = True
                    # Grounding guard: send the AI back ONCE to fix unsupported claims
                    if verbose:
                        print(f"  [step {step}] guard: {problems}")
                    messages.append({"role": "user", "content": (
                        " ".join(problems) + " Every piece of advice must be supported by search_guides "
                        "and cited like [S123]. Search for support, or remove the unsupported points.")})
                    continue
                # Still invented after the fix attempt? Drop those citation marks.
                answer = re.sub(r"\s*\[S(\d+)\]", lambda m: m.group(0) if f"S{m.group(1)}" in retrieved else "", answer)
                remaining = _grounding_problems(answer, retrieved)
                answer, sources = _finalize(answer, retrieved)
                return {"answer": answer, "sources": sources, "safety": "ok", "tool_calls": trace,
                        "steps": step, "grounded": not remaining, "grounding_issues": remaining}

            # 4. Run every tool the AI asked for, and give it the results
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                start = time.perf_counter()
                result = run_tool(conn, user_id, tc.function.name, args)
                ms = int((time.perf_counter() - start) * 1000)

                if tc.function.name == "search_guides":
                    _collect_sources(result, retrieved)

                trace.append({"step": step, "tool": tc.function.name, "args": args, "ms": ms})
                if verbose:
                    print(f"  [step {step}] {tc.function.name}({args}) -> {len(result)} chars, {ms} ms")

                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    # 5. Too many steps: stop safely instead of looping forever
    return {
        "answer": "Sorry, I couldn't finish that. Could you ask in a simpler way?",
        "sources": [], "safety": "ok", "tool_calls": trace, "steps": MAX_STEPS,
        "grounded": False, "grounding_issues": ["step limit reached"],
    }