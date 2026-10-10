import json
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from app.agent import BULLET, run_agent
from app.db import get_conn
from scripts.run_evals import judge  

EVAL_DIR = Path(__file__).resolve().parents[1] / "evals"
USER_ID = 1               
DEFAULT_MAX_TOOL_CALLS = 6


def called_right_tools(required, called):
    """Each item like "get_sleep|get_recovery_summary" means: at least one of these must be called."""
    return all(any(tool in called for tool in item.split("|")) for item in required)


def check(case, result):
    """Code checks: fast, exact, free."""
    called = [c["tool"] for c in result["tool_calls"]]
    checks = {"safety": result["safety"] == case.get("expect_safety", "ok")}

    if "expect_tools" in case:
        checks["right_tools"] = called_right_tools(case["expect_tools"], called)

    # The same tool with the same arguments twice = the agent is stuck or not reading results
    repeats = Counter(json.dumps(c, sort_keys=True) for c in result["tool_calls"])
    checks["no_repeats"] = max(repeats.values(), default=0) <= 1

    checks["efficient"] = len(called) <= case.get("max_tool_calls", DEFAULT_MAX_TOOL_CALLS)

    # Every advice bullet must have a citation that points to a real source
    bullets = [line for line in result["answer"].splitlines() if BULLET.match(line)]
    if bullets:
        checks["cited"] = bool(result["sources"]) and all(re.search(r"\[\d+\]", b) for b in bullets)

    return checks


def run_case(case):
    # Every run starts with a clean memory, so a fact saved in one run can't answer the next
    with get_conn() as conn:
        conn.execute("DELETE FROM user_memories WHERE user_id = %s", (USER_ID,))

    start = time.time()
    result = run_agent(case["question"], USER_ID)
    latency = round(time.time() - start, 1)

    checks = check(case, result)
    reason = ""
    if "rubric" in case:
        checks["answer"], reason = judge(case["question"], result["answer"], case["rubric"])

    return {"checks": checks, "passed": all(checks.values()), "answer": result["answer"],
            "tools": [c["tool"] for c in result["tool_calls"]], "judge": reason, "latency_s": latency}


def main():
    repeat = int(sys.argv[1]) if len(sys.argv) > 1 else 1   # agents vary run to run: try 3
    cases = json.loads((EVAL_DIR / "agent_cases.json").read_text())
    all_runs, failed_checks = [], Counter()

    for case in cases:
        runs = [run_case(case) for _ in range(repeat)]
        passes = sum(r["passed"] for r in runs)
        all_runs.append({"id": case["id"], "question": case["question"], "runs": runs})

        mark = "✅" if passes == repeat else "❌"
        print(f"{mark} [{case['id']}] {passes}/{repeat}  {case['question']}")
        for r in runs:
            failed = [name for name, ok in r["checks"].items() if not ok]
            failed_checks.update(failed)
            if failed:
                print(f"     failed: {', '.join(failed)} | tools: {r['tools']}")
                print(f"     answer: {r['answer'][:140]!r}")

    total = sum(len(c["runs"]) for c in all_runs)
    passed = sum(r["passed"] for c in all_runs for r in c["runs"])
    all_flat = [r for c in all_runs for r in c["runs"]]
    print("\n===== AGENT SCORE =====")
    print(f"Passed runs:      {passed}/{total} ({passed / total:.0%})")
    print(f"Avg tool calls:   {sum(len(r['tools']) for r in all_flat) / total:.1f}")
    print(f"Avg latency:      {sum(r['latency_s'] for r in all_flat) / total:.1f}s")
    print(f"Most failed checks: {dict(failed_checks.most_common()) or 'none'}")

    out_dir = EVAL_DIR / "results"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / f"agent_{datetime.now():%Y-%m-%d_%H%M}.json"
    out_file.write_text(json.dumps(all_runs, indent=2))
    print(f"Saved: {out_file}")


if __name__ == "__main__":
    main()