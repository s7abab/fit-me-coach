import json
import re
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from app.coach import answer
from app.llm import chat

EVAL_DIR = Path(__file__).resolve().parents[1] / "evals"

JUDGE_PROMPT = """You are grading answers from a fitness coach chatbot.

Question: {question}

Chatbot answer: {answer}

Rubric (what a good answer must do): {rubric}

Does the answer satisfy the rubric? Reply with PASS or FAIL on the first line,
then one short sentence explaining why."""


def judge(question, reply, rubric):
    # A second AI call grades the answer against the rubric
    out = chat(
        [{"role": "user", "content": JUDGE_PROMPT.format(question=question, answer=reply, rubric=rubric)}],
        temperature=0,
    ).strip()
    first_line = out.splitlines()[0].upper() if out else ""
    return "PASS" in first_line, out


def run_case(case):
    start = time.time()
    result = answer(case["question"])
    latency = round(time.time() - start, 2)

    checks, judge_reason = {}, ""

    # Code check 1: did the safety layer do the right thing?
    if "expect_safety" in case:
        checks["safety"] = result["safety"] == case["expect_safety"]

    # Code check 2: did search find the right document?
    if "expect_doc" in case:
        checks["retrieval"] = any(case["expect_doc"].lower() in s["title"].lower() for s in result["sources"])

    # Code check 3: knowledge answers must cite a source returned for this answer.
    if case["category"] == "knowledge":
        cited = {int(n) for n in re.findall(r"\[(\d+)\]", result["answer"])}
        checks["citation"] = bool(cited) and cited <= {
            source["n"] for source in result["sources"]
        }

    # AI judge: is the answer actually right?
    if "rubric" in case:
        checks["answer"], judge_reason = judge(case["question"], result["answer"], case["rubric"])

    return {
        "id": case["id"],
        "category": case["category"],
        "question": case["question"],
        "answer": result["answer"],
        "checks": checks,
        "passed": all(checks.values()),
        "judge": judge_reason,
        "latency_s": latency,
    }


def main():
    cases = json.loads((EVAL_DIR / "dataset.json").read_text())
    results = []

    for case in cases:
        r = run_case(case)
        results.append(r)
        mark = "✅" if r["passed"] else "❌"
        failed = [name for name, ok in r["checks"].items() if not ok]
        print(f"{mark} [{r['id']}] {r['question'][:60]}  {'FAILED: ' + ', '.join(failed) if failed else ''}")
        if not r["passed"]:
            print(f"     answer: {r['answer'][:150]}")
            if r["judge"]:
                print(f"     judge:  {r['judge'][:150]}")

    # Score per category
    by_cat = defaultdict(lambda: [0, 0])
    for r in results:
        by_cat[r["category"]][0] += r["passed"]
        by_cat[r["category"]][1] += 1

    print("\n===== SCORES =====")
    for cat, (ok, total) in by_cat.items():
        print(f"{cat:15} {ok}/{total}")
    total_ok = sum(r["passed"] for r in results)
    print(f"{'TOTAL':15} {total_ok}/{len(results)}")
    print(f"Avg latency: {sum(r['latency_s'] for r in results) / len(results):.1f}s")

    # Save every run, so you can compare before/after
    out_dir = EVAL_DIR / "results"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / f"{datetime.now():%Y-%m-%d_%H%M}.json"
    out_file.write_text(json.dumps(results, indent=2))
    print(f"Saved: {out_file}")


if __name__ == "__main__":
    main()
