import sys
from app.agent import run_agent

USER_ID = 1   # demo user

question = sys.argv[1]
print(f"Q: {question}\n")
result = run_agent(question, USER_ID)
for call in result["tool_calls"]:
    print(f"  {call['tool']}({call['args']})")
print(f"\n{result['answer']}\n")
print(f"(safety: {result['safety']}, tool calls: {len(result['tool_calls'])})")
for s in result["sources"]:
    print(f"[{s['n']}] {s['title']}, page {s['page']}")